from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]

from reviewlens.warehouse.candidates import (
    CandidateLayer,
    CandidateLease,
    CandidateState,
    InMemoryCandidateRegistry,
    PhysicalRelationRef,
    ProcessingInput,
    ProcessingInputKind,
    build_candidate_definition,
    build_processing_run,
)
from reviewlens.warehouse.quality import (
    DQFinding,
    DQGateStatus,
    DQSeverity,
    WarehouseQualityError,
    evaluate_quality_gate,
)
from reviewlens.warehouse.revisions import (
    DimensionEntity,
    DimensionRevision,
    RevisionDisposition,
    WarehouseRevisionError,
    resolve_dimension_revisions,
    unknown_member,
)

ROOT = Path(__file__).resolve().parents[1]
DBT_DIR = ROOT / "dbt"
SILVER_DIR = DBT_DIR / "models" / "silver"
NOW = datetime(2026, 8, 15, 3, 0, tzinfo=UTC)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def _finding(severity: DQSeverity, suffix: str, count: int = 1) -> DQFinding:
    return DQFinding(
        rule_id=f"ORDER_{suffix}",
        model_name="SIL_ORDER",
        grain_key_hash=_hash(suffix),
        severity=severity,
        failure_count=count,
    )


def _claimed_candidate() -> tuple[InMemoryCandidateRegistry, CandidateLease]:
    run = build_processing_run(
        contract_version="silver-contract-v1",
        phase=CandidateLayer.SILVER,
        source_release_id=f"olist_{'a' * 64}",
        ingestion_batch_id=f"batch_{'b' * 64}",
        inputs=(
            ProcessingInput(
                kind=ProcessingInputKind.BRONZE_RELATION,
                logical_name="ORDERS",
                physical_ref=PhysicalRelationRef("REVIEWLENS", "BRONZE", "BRZ_OLIST_ORDERS_RAW"),
                version_id=f"dsrun_{'c' * 64}",
                content_sha256="d" * 64,
            ),
        ),
    )
    definition = build_candidate_definition(run)
    registry = InMemoryCandidateRegistry()
    registry.append_run(run)
    registry.register_candidate(definition)
    lease = registry.claim(
        definition.candidate_id,
        owner_id="dq-worker",
        now=NOW,
        expires_at=NOW + timedelta(minutes=5),
    )
    return registry, lease


def test_quality_gate_is_order_independent_and_counts_nonblocking_findings() -> None:
    findings = (
        _finding(DQSeverity.WARN, "ZIP_WARNING", 2),
        _finding(DQSeverity.QUARANTINE, "INVALID_AMOUNT", 3),
    )

    first = evaluate_quality_gate(findings)
    second = evaluate_quality_gate(reversed(findings))

    assert first == second
    assert first.status is DQGateStatus.PASS_WITH_FINDINGS
    assert first.can_publish is True
    assert first.warning_failure_count == 2
    assert first.quarantined_failure_count == 3
    assert first.critical_failure_count == 0


def test_critical_quality_finding_fails_candidate_closed() -> None:
    registry, lease = _claimed_candidate()
    result = evaluate_quality_gate((_finding(DQSeverity.CRITICAL, "ORPHAN", 4),))

    completed = registry.finish_quality_gate(lease, result=result, now=NOW + timedelta(minutes=1))

    assert result.status is DQGateStatus.BLOCKED
    assert result.can_publish is False
    assert result.critical_failure_count == 4
    assert completed.state is CandidateState.FAILED


def test_empty_quality_gate_marks_candidate_test_passed() -> None:
    registry, lease = _claimed_candidate()
    result = evaluate_quality_gate(())

    completed = registry.finish_quality_gate(lease, result=result, now=NOW + timedelta(minutes=1))

    assert result.status is DQGateStatus.PASS
    assert completed.state is CandidateState.TEST_PASSED


def test_quality_contract_rejects_duplicate_or_raw_identifiers_without_echo() -> None:
    finding = _finding(DQSeverity.WARN, "DUPLICATE")
    with pytest.raises(WarehouseQualityError):
        evaluate_quality_gate((finding, finding))
    seeded = "raw-order-id"
    with pytest.raises(WarehouseQualityError) as caught:
        DQFinding("INVALID", "SIL_ORDER", seeded, DQSeverity.CRITICAL)

    assert str(caught.value) == WarehouseQualityError.code
    assert seeded not in str(caught.value)


def test_unknown_members_are_stable_distinct_and_nonsemantic() -> None:
    members = tuple(unknown_member(entity) for entity in DimensionEntity)

    assert members == tuple(unknown_member(entity) for entity in DimensionEntity)
    assert len({member.member_key for member in members}) == len(DimensionEntity)
    assert all(len(member.member_key) == 64 for member in members)
    assert {member.display_label for member in members} == {"UNKNOWN"}


def test_late_and_corrected_dimensions_resolve_independently_of_input_order() -> None:
    entity_key = _hash("customer-1")
    first = DimensionRevision(
        entity_key,
        datetime(2026, 1, 3),
        datetime(2026, 1, 3, 1, tzinfo=UTC),
        1,
        _hash("first"),
    )
    correction = DimensionRevision(
        entity_key,
        datetime(2026, 1, 3),
        datetime(2026, 1, 3, 2, tzinfo=UTC),
        2,
        _hash("correction"),
    )
    late = DimensionRevision(
        entity_key,
        datetime(2026, 1, 2),
        datetime(2026, 1, 4, tzinfo=UTC),
        3,
        _hash("late"),
    )

    result = resolve_dimension_revisions((late, first, correction, first))
    replay = resolve_dimension_revisions((first, correction, late, first))

    assert result == replay
    assert result.current == correction
    assert result.replay_duplicate_count == 1
    assert tuple(decision.disposition for decision in result.decisions) == (
        RevisionDisposition.CURRENT,
        RevisionDisposition.CORRECTION_SUPERSEDED,
        RevisionDisposition.LATE_SUPERSEDED,
    )


def test_revision_contract_rejects_mixed_entities_and_unsafe_time() -> None:
    base = DimensionRevision(_hash("customer-1"), datetime(2026, 1, 1), NOW, 1, _hash("row-1"))
    other = DimensionRevision(_hash("customer-2"), datetime(2026, 1, 1), NOW, 1, _hash("row-2"))

    with pytest.raises(WarehouseRevisionError):
        resolve_dimension_revisions((base, other))
    with pytest.raises(WarehouseRevisionError):
        DimensionRevision(_hash("customer-1"), NOW, NOW, 1, _hash("row-1"))


def test_dbt_quality_outputs_are_metadata_only_and_critical_selector_is_fail_closed() -> None:
    quarantine = (SILVER_DIR / "sil_dq_quarantine.sql").read_text(encoding="utf-8")
    properties: dict[str, Any] = yaml.safe_load(
        (SILVER_DIR / "silver_quality.yml").read_text(encoding="utf-8")
    )
    gate = (DBT_DIR / "tests" / "m3_critical_dq_gate.sql").read_text(encoding="utf-8")
    selectors = (DBT_DIR / "selectors.yml").read_text(encoding="utf-8")

    assert "reviewlens_dq_columns" in quarantine
    assert "review_comment_title" not in quarantine
    assert "review_comment_message" not in quarantine
    dq_macro = (DBT_DIR / "macros" / "reviewlens_dq_columns.sql").read_text(encoding="utf-8")
    assert "grain_key_hash" in dq_macro
    models = {model["name"]: model for model in properties["models"]}
    assert models["sil_dq_quarantine"]["config"]["meta"]["contains_review_text"] is False
    assert "severity = 'CRITICAL'" in gate
    assert "severity='error'" in gate
    assert "name: m3_silver_critical" in selectors
    assert "value: m3_critical" in selectors


def test_dbt_unknown_registry_and_revision_macro_encode_versioned_policy() -> None:
    registry = (SILVER_DIR / "sil_unknown_member_registry.sql").read_text(encoding="utf-8")
    revision_macro = (DBT_DIR / "macros" / "reviewlens_revision_rank.sql").read_text(
        encoding="utf-8"
    )

    for entity in DimensionEntity:
        assert f"('{entity.value}')" in registry
    assert "reviewlens-unknown-member-v1" in registry
    assert "source_row_number desc" in revision_macro
    assert "record_hash desc" in revision_macro
    for model in (
        "sil_customer",
        "sil_order",
        "sil_order_item",
        "sil_order_payment",
        "sil_order_review",
        "sil_product",
        "sil_seller",
        "sil_category_translation",
    ):
        sql = (SILVER_DIR / f"{model}.sql").read_text(encoding="utf-8")
        assert "reviewlens_revision_rank" in sql
