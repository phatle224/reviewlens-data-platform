from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from reviewlens.warehouse.candidates import (
    CandidateLayer,
    CandidateState,
    InMemoryCandidateRegistry,
    PhysicalRelationRef,
    ProcessingInput,
    ProcessingInputKind,
    ProcessingRunDefinition,
    build_candidate_definition,
    build_processing_run,
)
from reviewlens.warehouse.gold_candidate import (
    GOLD_CANDIDATE_BUILD_VERSION,
    GOLD_CANDIDATE_MODEL_NAMES,
    GOLD_CANDIDATE_OUTPUT_LOGICAL_NAMES,
    GOLD_CANDIDATE_SELECTOR,
    SILVER_GOLD_INPUT_LOGICAL_NAMES,
    GoldCandidateBuildEvidence,
    GoldCandidateBuildTarget,
    GoldCandidateTargetError,
    finish_gold_candidate_target,
    plan_gold_candidate_target,
)

SOURCE_RELEASE_ID = f"olist_{'a' * 64}"
BATCH_ID = f"batch_{'b' * 64}"
NOW = datetime(2026, 8, 16, 2, 0, tzinfo=UTC)
DBT_DIR = Path("dbt")
GOLD_DIR = DBT_DIR / "models" / "gold"

_GOLD_MODELS_READING_SILVER = {
    "bridge_review_item_attribution",
    "dim_customer",
    "dim_date",
    "dim_geography",
    "dim_product",
    "dim_seller",
    "fact_order",
    "fact_order_item",
    "fact_payment",
    "fact_review_base",
}


def _silver_run(contract_version: str = "silver-contract-v1") -> ProcessingRunDefinition:
    return build_processing_run(
        contract_version=contract_version,
        phase=CandidateLayer.SILVER,
        source_release_id=SOURCE_RELEASE_ID,
        ingestion_batch_id=BATCH_ID,
        inputs=(
            ProcessingInput(
                kind=ProcessingInputKind.BRONZE_RELATION,
                logical_name="CUSTOMERS",
                physical_ref=PhysicalRelationRef("REVIEWLENS", "BRONZE", "BRZ_OLIST_CUSTOMERS_RAW"),
                version_id=f"dsrun_{'c' * 64}",
                content_sha256="d" * 64,
            ),
            ProcessingInput(
                kind=ProcessingInputKind.BRONZE_RELATION,
                logical_name="ORDERS",
                physical_ref=PhysicalRelationRef("REVIEWLENS", "BRONZE", "BRZ_OLIST_ORDERS_RAW"),
                version_id=f"dsrun_{'e' * 64}",
                content_sha256="f" * 64,
            ),
        ),
    )


def _target() -> GoldCandidateBuildTarget:
    silver_run = _silver_run()
    silver_candidate = build_candidate_definition(silver_run)
    return plan_gold_candidate_target(
        silver_run=silver_run,
        silver_candidate=silver_candidate,
    )


def test_gold_target_is_deterministic_and_separates_input_from_output() -> None:
    target = _target()
    repeated = _target()

    assert target == repeated
    assert target.gold_run.phase is CandidateLayer.GOLD
    assert target.gold_candidate.layer is CandidateLayer.GOLD
    assert target.gold_candidate.strategy_version == GOLD_CANDIDATE_BUILD_VERSION
    assert target.gold_candidate.candidate_id != target.silver_candidate.candidate_id
    assert target.gold_candidate.physical_namespace != target.silver_candidate.physical_namespace
    assert target.dbt_vars == {
        "candidate_namespace": target.gold_candidate.physical_namespace,
        "ingestion_batch_id": BATCH_ID,
        "silver_candidate_namespace": target.silver_candidate.physical_namespace,
        "source_release_id": SOURCE_RELEASE_ID,
    }
    assert json.loads(target.dbt_vars_json) == target.dbt_vars
    assert {item.input.logical_name for item in target.gold_run.inputs} == set(
        SILVER_GOLD_INPUT_LOGICAL_NAMES
    )
    assert all(
        item.input.kind is ProcessingInputKind.CANDIDATE_RELATION for item in target.gold_run.inputs
    )
    assert all(item.input.physical_ref.schema == "SILVER" for item in target.gold_run.inputs)
    assert [item.schema for item in target.output_relations] == ["GOLD"] * len(
        GOLD_CANDIDATE_OUTPUT_LOGICAL_NAMES
    )
    assert [
        item.object_name.rsplit("__", maxsplit=1)[1] for item in target.output_relations
    ] == list(GOLD_CANDIDATE_OUTPUT_LOGICAL_NAMES)


def test_gold_target_requires_the_registered_silver_run_and_candidate_pair() -> None:
    silver_run = _silver_run()
    wrong_candidate = build_candidate_definition(_silver_run("silver-contract-v2"))

    with pytest.raises(GoldCandidateTargetError) as error:
        plan_gold_candidate_target(silver_run=silver_run, silver_candidate=wrong_candidate)

    assert str(error.value) == GoldCandidateTargetError.code


def test_complete_gold_candidate_can_pass_only_with_full_successful_evidence() -> None:
    target = _target()
    registry = InMemoryCandidateRegistry()
    registry.append_run(target.gold_run)
    registry.register_candidate(target.gold_candidate)
    lease = registry.claim(
        target.gold_candidate.candidate_id,
        owner_id="gold-builder",
        now=NOW,
        expires_at=NOW + timedelta(minutes=10),
    )
    evidence = GoldCandidateBuildEvidence(
        candidate_id=target.gold_candidate.candidate_id,
        selected_model_names=GOLD_CANDIDATE_MODEL_NAMES,
        dbt_build_succeeded=True,
        dbt_test_succeeded=True,
        runtime_contract_succeeded=True,
    )

    completed = finish_gold_candidate_target(
        registry,
        target=target,
        lease=lease,
        evidence=evidence,
        now=NOW + timedelta(minutes=1),
    )

    assert completed.state is CandidateState.TEST_PASSED
    assert registry.get(target.gold_candidate.candidate_id).lease is None


def test_incomplete_or_failed_gold_target_is_failed_and_never_test_passed() -> None:
    target = _target()
    registry = InMemoryCandidateRegistry()
    registry.append_run(target.gold_run)
    registry.register_candidate(target.gold_candidate)
    lease = registry.claim(
        target.gold_candidate.candidate_id,
        owner_id="gold-builder",
        now=NOW,
        expires_at=NOW + timedelta(minutes=10),
    )
    incomplete = GoldCandidateBuildEvidence(
        candidate_id=target.gold_candidate.candidate_id,
        selected_model_names=frozenset(set(GOLD_CANDIDATE_MODEL_NAMES) - {"sem_order_delivery"}),
        dbt_build_succeeded=True,
        dbt_test_succeeded=True,
        runtime_contract_succeeded=True,
    )

    completed = finish_gold_candidate_target(
        registry,
        target=target,
        lease=lease,
        evidence=incomplete,
        now=NOW + timedelta(minutes=1),
    )

    assert incomplete.can_advance is False
    assert completed.state is CandidateState.FAILED
    assert registry.cleanup(target.gold_candidate.candidate_id).state is CandidateState.CLEANED


@pytest.mark.parametrize(
    "evidence",
    [
        GoldCandidateBuildEvidence(
            candidate_id="a" * 64,
            selected_model_names=frozenset({"unexpected_model"}),
            dbt_build_succeeded=True,
            dbt_test_succeeded=True,
            runtime_contract_succeeded=True,
        ),
        GoldCandidateBuildEvidence(
            candidate_id="b" * 64,
            selected_model_names=GOLD_CANDIDATE_MODEL_NAMES,
            dbt_build_succeeded=False,
            dbt_test_succeeded=True,
            runtime_contract_succeeded=True,
        ),
    ],
)
def test_gold_evidence_rejects_success_claims_with_wrong_models_or_outcomes(
    evidence: GoldCandidateBuildEvidence,
) -> None:
    assert evidence.can_advance is False


def test_gold_dbt_target_reads_only_explicit_silver_candidate_relations() -> None:
    forbidden_silver_ref = re.compile(r"ref\('sil_")

    for model_name in _GOLD_MODELS_READING_SILVER:
        sql = (GOLD_DIR / f"{model_name}.sql").read_text(encoding="utf-8")
        assert "reviewlens_silver_candidate_relation(" in sql
        assert forbidden_silver_ref.search(sql) is None
    macro = (DBT_DIR / "macros" / "reviewlens_silver_candidate_relation.sql").read_text(
        encoding="utf-8"
    )
    assert "silver_candidate_namespace" in macro
    assert "adapter.quote" in macro
    assert "target.database" in macro


def test_gold_candidate_selector_runtime_gate_and_documented_command_are_exact() -> None:
    selector = (DBT_DIR / "selectors.yml").read_text(encoding="utf-8")
    runtime_gate = (DBT_DIR / "tests" / "m3_gold_candidate_runtime_contract.sql").read_text(
        encoding="utf-8"
    )
    readme = (DBT_DIR / "README.md").read_text(encoding="utf-8")

    assert f"name: {GOLD_CANDIDATE_SELECTOR}" in selector
    for tag in ("m3_gold_base", "m3_review_attribution", "m3_gold_marts", "m3_semantic"):
        assert f"value: {tag}" in selector
    assert "value: m3_gold_candidate" in selector
    for required_variable in (
        "candidate_namespace",
        "silver_candidate_namespace",
        "source_release_id",
        "ingestion_batch_id",
    ):
        assert required_variable in runtime_gate
    assert '= \'{{ var("silver_candidate_namespace"' in runtime_gate
    assert "--selector m3_gold_candidate" in readme
    assert "silver_candidate_namespace" in readme
