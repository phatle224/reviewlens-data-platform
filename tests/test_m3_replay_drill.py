from __future__ import annotations

import hashlib
import json
from decimal import Decimal

import pytest

from reviewlens.ingestion.bronze import BRONZE_TABLE_BY_DATASET
from reviewlens.ingestion.contracts import load_olist_contract
from reviewlens.ingestion.preflight import load_approved_olist_snapshot
from reviewlens.warehouse.equivalence import (
    CandidateBuildMode,
    WarehouseEquivalenceError,
    compare_full_refresh_to_deterministic_replay,
)
from reviewlens.warehouse.gold_candidate import GOLD_CANDIDATE_SELECTOR
from reviewlens.warehouse.releases import SILVER_RELEASE_LOGICAL_NAMES
from reviewlens.warehouse.replay_drill import (
    M3_FINGERPRINT_METHOD,
    M3_SILVER_CANDIDATE_SELECTOR,
    M3ReplayDrillError,
    build_approved_m3_replay_drill_plan,
    build_approved_m3_rollback_proof_plan,
    main,
    parse_fingerprint_rows,
    snapshot_from_fingerprint_rows,
)


def _fingerprint_rows() -> tuple[tuple[object, ...], ...]:
    plan = build_approved_m3_replay_drill_plan()
    rows: list[tuple[object, ...]] = []
    for layer, logical_names in (
        ("SILVER", sorted(SILVER_RELEASE_LOGICAL_NAMES)),
        ("GOLD", plan.gold_target_output_names),
    ):
        for logical_name in logical_names:
            rows.append(
                (
                    layer,
                    logical_name,
                    Decimal(len(logical_name)),
                    hashlib.sha256(f"{layer}:{logical_name}".encode()).hexdigest(),
                )
            )
    return tuple(rows)


def test_approved_drill_plan_is_deterministic_and_binds_all_nine_bronze_inputs() -> None:
    first = build_approved_m3_replay_drill_plan()
    second = build_approved_m3_replay_drill_plan()

    assert first == second
    assert first.candidate_pair.silver_candidate_id != first.candidate_pair.gold_candidate_id
    assert len(first.silver_run.inputs) == 9
    assert {item.input.logical_name for item in first.silver_run.inputs} == {
        dataset_name.upper() for dataset_name in BRONZE_TABLE_BY_DATASET
    }
    assert {item.input.physical_ref.object_name for item in first.silver_run.inputs} == set(
        BRONZE_TABLE_BY_DATASET.values()
    )
    assert {item.input.content_sha256 for item in first.silver_run.inputs} == {
        item.sha256 for item in load_approved_olist_snapshot().files
    }
    assert all(item.input.version_id.startswith("dsrun_") for item in first.silver_run.inputs)


def test_rollback_proof_plan_is_distinct_without_changing_source_or_semantics() -> None:
    primary = build_approved_m3_replay_drill_plan()
    rollback_proof = build_approved_m3_rollback_proof_plan()

    assert rollback_proof.release_variant == "rollback-proof"
    assert primary.release_variant == "primary"
    assert rollback_proof.candidate_pair != primary.candidate_pair
    assert rollback_proof.source_release_id == primary.source_release_id
    assert rollback_proof.ingestion_batch_id == primary.ingestion_batch_id
    assert rollback_proof.silver_build.selector == primary.silver_build.selector
    assert rollback_proof.gold_build.selector == primary.gold_build.selector
    assert rollback_proof.safe_summary["fingerprint_relation_count"] == 28


def test_dbt_commands_are_exact_and_fingerprint_query_is_aggregate_only() -> None:
    plan = build_approved_m3_replay_drill_plan()

    assert plan.silver_build.selector == M3_SILVER_CANDIDATE_SELECTOR
    assert plan.gold_build.selector == GOLD_CANDIDATE_SELECTOR
    assert plan.silver_build.argv()[0] == "dbt"
    assert "candidate_namespace" in plan.silver_build.vars_json
    assert "silver_candidate_namespace" in plan.gold_build.vars_json
    assert len(plan.gold_read_grants) == 10
    assert all(
        statement.startswith("GRANT SELECT ON TABLE REVIEWLENS.SILVER.C_")
        for statement in plan.gold_read_grants
    )
    assert all(
        "FUTURE" not in statement and " ON SCHEMA " not in statement
        for statement in plan.gold_read_grants
    )

    query = plan.fingerprint_sql
    assert query.count("UNION ALL") == 27
    assert query.count("HASH_AGG(*)") == 28
    assert query.count("SHA2(TO_VARCHAR(HASH_AGG(*)), 256)") == 28
    assert "RAW_PAYLOAD" not in query
    assert "REVIEW_COMMENT" not in query


def test_aggregate_rows_form_same_candidate_pair_full_and_replay_snapshots() -> None:
    plan = build_approved_m3_replay_drill_plan()
    rows = _fingerprint_rows()

    full = snapshot_from_fingerprint_rows(
        plan=plan,
        mode=CandidateBuildMode.FULL_REFRESH,
        rows=rows,
    )
    replay = snapshot_from_fingerprint_rows(
        plan=plan,
        mode=CandidateBuildMode.DETERMINISTIC_REPLAY,
        rows=tuple(reversed(rows)),
    )

    report = compare_full_refresh_to_deterministic_replay(full_refresh=full, replay=replay)

    assert report.equivalent is True
    assert report.candidate_pair == plan.candidate_pair
    assert len(full.relation_fingerprints) == 28


@pytest.mark.parametrize(
    "rows",
    [
        (),
        (("SILVER", "SIL_ORDER", True, "a" * 64),),
        (("SILVER", "SIL_ORDER", Decimal("1.5"), "a" * 64),),
        (("SILVER", "C_" + "A" * 64 + "__SIL_ORDER", 1, "a" * 64),),
        (("SILVER", "SIL_ORDER", 1, "not-a-hash"),),
    ],
)
def test_fingerprint_row_parser_rejects_non_aggregate_or_unsafe_values(
    rows: tuple[tuple[object, ...], ...],
) -> None:
    with pytest.raises(M3ReplayDrillError) as error:
        parse_fingerprint_rows(rows)
    assert str(error.value) == M3ReplayDrillError.code


def test_snapshot_builder_rejects_incomplete_expected_relation_set() -> None:
    plan = build_approved_m3_replay_drill_plan()

    with pytest.raises(M3ReplayDrillError) as error:
        snapshot_from_fingerprint_rows(
            plan=plan,
            mode=CandidateBuildMode.FULL_REFRESH,
            rows=_fingerprint_rows()[:-1],
        )

    assert str(error.value) == M3ReplayDrillError.code


def test_cli_prints_safe_summary_without_provider_or_physical_namespace(
    capsys: pytest.CaptureFixture[str],
) -> None:
    main(["--print-plan"])
    output = json.loads(capsys.readouterr().out)

    assert output["fingerprint_method"] == M3_FINGERPRINT_METHOD
    assert output["fingerprint_relation_count"] == 28
    assert output["silver_selector"] == M3_SILVER_CANDIDATE_SELECTOR
    assert output["gold_selector"] == GOLD_CANDIDATE_SELECTOR
    assert all("physical" not in key for key in output)
    assert all(not str(value).startswith("C_") for value in output.values())


def test_snapshot_reference_contract_remains_exact_nine_file_olist() -> None:
    plan = build_approved_m3_replay_drill_plan()
    source_datasets = load_olist_contract().datasets

    assert len(source_datasets) == 9
    assert {item.input.logical_name.lower() for item in plan.silver_run.inputs} == {
        dataset.dataset_name for dataset in source_datasets
    }
    with pytest.raises(WarehouseEquivalenceError):
        plan.candidate_pair.__class__(
            silver_candidate_id=plan.candidate_pair.silver_candidate_id,
            gold_candidate_id=plan.candidate_pair.silver_candidate_id,
        )
