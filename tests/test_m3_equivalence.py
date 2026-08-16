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
    compare_full_refresh_to_deterministic_replay,
)
from reviewlens.warehouse.gold_candidate import GOLD_CANDIDATE_OUTPUT_LOGICAL_NAMES
from reviewlens.warehouse.releases import SILVER_RELEASE_LOGICAL_NAMES
from reviewlens.warehouse.semantic import SEMANTIC_CATALOG_VERSION

SOURCE_RELEASE_ID = f"olist_{'a' * 64}"
BATCH_ID = f"batch_{'b' * 64}"
OTHER_BATCH_ID = f"batch_{'f' * 64}"
FULL_CANDIDATE_ID = "c" * 64
OTHER_CANDIDATE_ID = "d" * 64
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


def test_equivalence_is_deterministic_for_same_candidate_replay_relation_sets() -> None:
    full = _snapshot(CandidateBuildMode.FULL_REFRESH, FULL_CANDIDATE_ID)
    replay = _snapshot(CandidateBuildMode.DETERMINISTIC_REPLAY, FULL_CANDIDATE_ID)

    first = compare_full_refresh_to_deterministic_replay(full_refresh=full, replay=replay)
    second = compare_full_refresh_to_deterministic_replay(full_refresh=full, replay=replay)

    assert first == second
    assert first.equivalent is True
    assert first.mismatches == ()
    assert first.candidate_id == FULL_CANDIDATE_ID


def test_equivalence_reports_only_logical_relation_and_mismatch_kind() -> None:
    full = _snapshot(CandidateBuildMode.FULL_REFRESH, FULL_CANDIDATE_ID)
    replay = _snapshot(CandidateBuildMode.DETERMINISTIC_REPLAY, FULL_CANDIDATE_ID)
    target = next(
        item
        for item in replay.relation_fingerprints
        if item.layer is CandidateLayer.GOLD and item.logical_name == "FACT_ORDER"
    )
    changed = replace(target, row_count=target.row_count + 1, content_sha256="e" * 64)
    replay = replace(
        replay,
        relation_fingerprints=tuple(
            sorted(changed if item == target else item for item in replay.relation_fingerprints)
        ),
    )

    report = compare_full_refresh_to_deterministic_replay(full_refresh=full, replay=replay)

    assert report.equivalent is False
    assert [(item.layer, item.logical_name, item.kind) for item in report.mismatches] == [
        (CandidateLayer.GOLD, "FACT_ORDER", EquivalenceMismatchKind.CONTENT_HASH),
        (CandidateLayer.GOLD, "FACT_ORDER", EquivalenceMismatchKind.ROW_COUNT),
    ]


def test_equivalence_denies_different_candidate_metadata_drift_or_wrong_build_modes() -> None:
    full = _snapshot(CandidateBuildMode.FULL_REFRESH, FULL_CANDIDATE_ID)
    replay = _snapshot(CandidateBuildMode.DETERMINISTIC_REPLAY, FULL_CANDIDATE_ID)
    invalid_pairs = (
        (full, replace(replay, candidate_id=OTHER_CANDIDATE_ID)),
        (full, replace(replay, source_release_id=f"olist_{'e' * 64}")),
        (full, replace(replay, ingestion_batch_id=OTHER_BATCH_ID)),
        (full, replace(replay, build_mode=CandidateBuildMode.FULL_REFRESH)),
        (replace(full, build_mode=CandidateBuildMode.DETERMINISTIC_REPLAY), replay),
    )

    for invalid_full, invalid_replay in invalid_pairs:
        with pytest.raises(WarehouseEquivalenceError) as error:
            compare_full_refresh_to_deterministic_replay(
                full_refresh=invalid_full,
                replay=invalid_replay,
            )
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


def test_equivalence_runbook_requires_same_candidate_replay_and_private_evidence() -> None:
    source = RUNBOOK.read_text(encoding="utf-8")
    normalized = " ".join(source.split())

    assert "`IMP-M3-020` vẫn **partial**" in source
    assert "không được gọi replay là incremental" in normalized
    assert "cùng candidate ID" in normalized
    assert "10 Silver và 18 Gold" in normalized
    assert "không chứa physical relation, key kinh doanh hay source row" in normalized
    assert "warehouse được suspend" in normalized
