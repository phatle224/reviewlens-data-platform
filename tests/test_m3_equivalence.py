from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

from reviewlens.warehouse.candidates import CandidateLayer
from reviewlens.warehouse.equivalence import (
    CandidateBuildMode,
    CandidateEquivalenceSnapshot,
    EquivalenceMismatchKind,
    RelationFingerprint,
    WarehouseEquivalenceError,
    compare_full_refresh_to_incremental,
)
from reviewlens.warehouse.gold_candidate import GOLD_CANDIDATE_OUTPUT_LOGICAL_NAMES
from reviewlens.warehouse.releases import SILVER_RELEASE_LOGICAL_NAMES
from reviewlens.warehouse.semantic import SEMANTIC_CATALOG_VERSION

SOURCE_RELEASE_ID = f"olist_{'a' * 64}"
BATCH_ID = f"batch_{'b' * 64}"
FULL_CANDIDATE_ID = "c" * 64
INCREMENTAL_CANDIDATE_ID = "d" * 64
RUNBOOK = Path("docs/runbooks/M3_RELEASE_OPERATIONS.md")


def _fingerprint(
    layer: CandidateLayer, logical_name: str, *, marker: str = "same"
) -> RelationFingerprint:
    digest = hashlib.sha256(f"{layer.value}:{logical_name}:{marker}".encode()).hexdigest()
    return RelationFingerprint(
        layer=layer,
        logical_name=logical_name,
        row_count=len(logical_name),
        content_sha256=digest,
    )


def _snapshot(mode: CandidateBuildMode, candidate_id: str) -> CandidateEquivalenceSnapshot:
    relations = tuple(
        sorted(
            [
                *(
                    _fingerprint(CandidateLayer.SILVER, logical_name)
                    for logical_name in SILVER_RELEASE_LOGICAL_NAMES
                ),
                *(
                    _fingerprint(CandidateLayer.GOLD, logical_name)
                    for logical_name in GOLD_CANDIDATE_OUTPUT_LOGICAL_NAMES
                ),
            ]
        )
    )
    return CandidateEquivalenceSnapshot(
        candidate_id=candidate_id,
        build_mode=mode,
        source_release_id=SOURCE_RELEASE_ID,
        ingestion_batch_id=BATCH_ID,
        semantic_contract_version=SEMANTIC_CATALOG_VERSION,
        relation_fingerprints=relations,
    )


def test_equivalence_is_deterministic_for_complete_aggregate_only_relation_sets() -> None:
    full = _snapshot(CandidateBuildMode.FULL_REFRESH, FULL_CANDIDATE_ID)
    incremental = _snapshot(CandidateBuildMode.INCREMENTAL, INCREMENTAL_CANDIDATE_ID)

    first = compare_full_refresh_to_incremental(full_refresh=full, incremental=incremental)
    second = compare_full_refresh_to_incremental(full_refresh=full, incremental=incremental)

    assert first == second
    assert first.equivalent is True
    assert first.mismatches == ()


def test_equivalence_reports_only_logical_relation_and_mismatch_kind() -> None:
    full = _snapshot(CandidateBuildMode.FULL_REFRESH, FULL_CANDIDATE_ID)
    incremental = _snapshot(CandidateBuildMode.INCREMENTAL, INCREMENTAL_CANDIDATE_ID)
    target = next(
        item
        for item in incremental.relation_fingerprints
        if item.layer is CandidateLayer.GOLD and item.logical_name == "FACT_ORDER"
    )
    changed = replace(target, row_count=target.row_count + 1, content_sha256="e" * 64)
    incremental = replace(
        incremental,
        relation_fingerprints=tuple(
            sorted(
                changed if item == target else item for item in incremental.relation_fingerprints
            )
        ),
    )

    report = compare_full_refresh_to_incremental(full_refresh=full, incremental=incremental)

    assert report.equivalent is False
    assert [(item.layer, item.logical_name, item.kind) for item in report.mismatches] == [
        (CandidateLayer.GOLD, "FACT_ORDER", EquivalenceMismatchKind.CONTENT_HASH),
        (CandidateLayer.GOLD, "FACT_ORDER", EquivalenceMismatchKind.ROW_COUNT),
    ]


def test_equivalence_denies_same_candidate_metadata_drift_or_wrong_build_modes() -> None:
    full = _snapshot(CandidateBuildMode.FULL_REFRESH, FULL_CANDIDATE_ID)
    incremental = _snapshot(CandidateBuildMode.INCREMENTAL, INCREMENTAL_CANDIDATE_ID)
    invalid_snapshots = (
        replace(incremental, candidate_id=FULL_CANDIDATE_ID),
        replace(incremental, source_release_id=f"olist_{'e' * 64}"),
        replace(incremental, build_mode=CandidateBuildMode.FULL_REFRESH),
    )

    for invalid in invalid_snapshots:
        with pytest.raises(WarehouseEquivalenceError) as error:
            compare_full_refresh_to_incremental(full_refresh=full, incremental=invalid)
        assert str(error.value) == WarehouseEquivalenceError.code


def test_snapshot_requires_all_release_relations_and_rejects_physical_like_input() -> None:
    full = _snapshot(CandidateBuildMode.FULL_REFRESH, FULL_CANDIDATE_ID)

    with pytest.raises(WarehouseEquivalenceError):
        replace(full, relation_fingerprints=full.relation_fingerprints[:-1])
    with pytest.raises(WarehouseEquivalenceError):
        RelationFingerprint(
            layer=CandidateLayer.GOLD,
            logical_name="C_" + "A" * 64 + "__FACT_ORDER",
            row_count=1,
            content_sha256="e" * 64,
        )


def test_equivalence_runbook_requires_a_true_incremental_path_and_private_evidence() -> None:
    source = RUNBOOK.read_text(encoding="utf-8")
    normalized = " ".join(source.split())

    assert "`IMP-M3-020` vẫn **partial**" in source
    assert "không được gọi một lần rebuild thứ hai là “incremental”" in normalized
    assert "10 Silver và 18 Gold" in normalized
    assert "không chứa physical relation, key kinh doanh hay source row" in normalized
    assert "warehouse được suspend" in normalized
