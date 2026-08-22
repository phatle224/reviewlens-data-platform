"""Synthetic offline contracts for aggregate AI enrichment observability."""

from __future__ import annotations

from decimal import Decimal

import pytest

from reviewlens.ai.commit import EnrichmentCoverageProjection
from reviewlens.ai.ledger import EnrichmentInvocationState
from reviewlens.ai.observability import (
    EnrichmentInvocationTelemetry,
    EnrichmentObservabilityError,
    build_enrichment_observability_snapshot,
)

VERSION = "a" * 64


def _coverage(*, valid: int = 1) -> EnrichmentCoverageProjection:
    return EnrichmentCoverageProjection(
        enrichment_version=VERSION,
        base_review_count=5,
        eligible_review_count=3,
        valid_enrichment_count=valid,
        missing_eligible_review_count=3 - valid,
        coverage_ratio=Decimal(valid) / Decimal(3),
    )


def _telemetry(
    *,
    invocation_id: str,
    state: EnrichmentInvocationState,
    input_tokens: int,
    output_tokens: int,
    cost_usd: str,
    latency_ms: int,
    error_code: str | None = None,
) -> EnrichmentInvocationTelemetry:
    return EnrichmentInvocationTelemetry(
        invocation_id=invocation_id * 64,
        enrichment_run_id="f" * 64,
        enrichment_version=VERSION,
        state=state,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=Decimal(cost_usd),
        latency_ms=latency_ms,
        sanitized_error_code=error_code,
    )


def test_m4_observability_reconciles_aggregate_ledgers_without_row_level_leakage() -> None:
    telemetry = (
        _telemetry(
            invocation_id="b",
            state=EnrichmentInvocationState.FAILED,
            input_tokens=100,
            output_tokens=0,
            cost_usd="0.001",
            latency_ms=120,
            error_code="AI_PROVIDER_TIMEOUT",
        ),
        _telemetry(
            invocation_id="c",
            state=EnrichmentInvocationState.SUCCEEDED,
            input_tokens=200,
            output_tokens=50,
            cost_usd="0.003",
            latency_ms=240,
        ),
        _telemetry(
            invocation_id="d",
            state=EnrichmentInvocationState.QUARANTINED,
            input_tokens=80,
            output_tokens=0,
            cost_usd="0.002",
            latency_ms=360,
            error_code="AI_SCHEMA_INVALID",
        ),
    )

    snapshot = build_enrichment_observability_snapshot(
        telemetry=telemetry,
        coverage=_coverage(),
        budget_committed_usd=Decimal("0.006"),
    )

    assert snapshot.invocation_count == 3
    assert snapshot.succeeded_invocation_count == 1
    assert snapshot.failed_invocation_count == 1
    assert snapshot.quarantined_invocation_count == 1
    assert snapshot.input_token_count == 380
    assert snapshot.output_token_count == 50
    assert snapshot.total_cost_usd == Decimal("0.006")
    assert snapshot.total_latency_ms == 720
    assert snapshot.p95_latency_ms == 360
    assert snapshot.errors[0].code == "AI_PROVIDER_TIMEOUT"
    assert snapshot.dashboard_payload()["coverage"] == {
        "base_review_count": 5,
        "eligible_review_count": 3,
        "valid_enrichment_count": 1,
        "missing_eligible_review_count": 2,
        "coverage_ratio": "0.3333333333333333333333333333",
    }
    assert "c" * 64 not in repr(snapshot)
    assert "f" * 64 not in repr(snapshot)


def test_m4_observability_is_deterministic_and_rejects_budget_or_coverage_drift() -> None:
    succeeded = _telemetry(
        invocation_id="c",
        state=EnrichmentInvocationState.SUCCEEDED,
        input_tokens=10,
        output_tokens=5,
        cost_usd="0.002",
        latency_ms=50,
    )
    failed = _telemetry(
        invocation_id="b",
        state=EnrichmentInvocationState.FAILED,
        input_tokens=10,
        output_tokens=0,
        cost_usd="0.001",
        latency_ms=10,
        error_code="AI_PROVIDER_TIMEOUT",
    )
    first = build_enrichment_observability_snapshot(
        telemetry=(succeeded, failed),
        coverage=_coverage(),
        budget_committed_usd=Decimal("0.003"),
    )
    replay = build_enrichment_observability_snapshot(
        telemetry=(failed, succeeded),
        coverage=_coverage(),
        budget_committed_usd=Decimal("0.003"),
    )

    assert replay == first
    with pytest.raises(
        EnrichmentObservabilityError, match="AI_ENRICHMENT_OBSERVABILITY_BUDGET_MISMATCH"
    ):
        build_enrichment_observability_snapshot(
            telemetry=(succeeded, failed),
            coverage=_coverage(),
            budget_committed_usd=Decimal("0.004"),
        )
    with pytest.raises(
        EnrichmentObservabilityError, match="AI_ENRICHMENT_OBSERVABILITY_COVERAGE_MISMATCH"
    ):
        build_enrichment_observability_snapshot(
            telemetry=(succeeded, failed),
            coverage=_coverage(valid=2),
            budget_committed_usd=Decimal("0.003"),
        )


def test_m4_observability_rejects_nonterminal_or_unsanitized_telemetry() -> None:
    with pytest.raises(EnrichmentObservabilityError):
        _telemetry(
            invocation_id="a",
            state=EnrichmentInvocationState.DISPATCHED,
            input_tokens=1,
            output_tokens=0,
            cost_usd="0.001",
            latency_ms=1,
        )
    with pytest.raises(EnrichmentObservabilityError):
        _telemetry(
            invocation_id="a",
            state=EnrichmentInvocationState.FAILED,
            input_tokens=1,
            output_tokens=0,
            cost_usd="0.001",
            latency_ms=1,
            error_code="review text must not be here",
        )
