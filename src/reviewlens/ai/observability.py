"""Aggregate-only observability contract for private AI enrichment.

This module deliberately accepts opaque ledger references at its input boundary
and emits only aggregate counters, sanitized error codes, costs and latency.
It must never retain review text, prompts, provider payloads, natural IDs or
row-level enrichment results.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal
from math import ceil

from reviewlens.ai.commit import EnrichmentCoverageProjection
from reviewlens.ai.ledger import EnrichmentInvocationState

_SHA256 = frozenset("0123456789abcdef")
_TERMINAL_STATES = frozenset(
    {
        EnrichmentInvocationState.SUCCEEDED,
        EnrichmentInvocationState.FAILED,
        EnrichmentInvocationState.QUARANTINED,
    }
)
_ERROR_STATES = frozenset({EnrichmentInvocationState.FAILED, EnrichmentInvocationState.QUARANTINED})


class EnrichmentObservabilityError(ValueError):
    """Sanitized observability/reconciliation failure without private payloads."""

    def __init__(self, code: str = "AI_ENRICHMENT_OBSERVABILITY_INVALID") -> None:
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class EnrichmentInvocationTelemetry:
    """Terminal provider-use metadata keyed only by opaque ledger references."""

    invocation_id: str = field(repr=False)
    enrichment_run_id: str = field(repr=False)
    enrichment_version: str
    state: EnrichmentInvocationState
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal
    latency_ms: int
    sanitized_error_code: str | None = None

    def __post_init__(self) -> None:
        if (
            not _is_hash(self.invocation_id)
            or not _is_hash(self.enrichment_run_id)
            or not self.enrichment_version
            or len(self.enrichment_version) > 256
            or self.state not in _TERMINAL_STATES
            or self.input_tokens < 0
            or self.output_tokens < 0
            or self.latency_ms < 0
            or not self.cost_usd.is_finite()
            or self.cost_usd < 0
        ):
            raise EnrichmentObservabilityError()
        if self.state in _ERROR_STATES:
            if not _is_sanitized_error_code(self.sanitized_error_code):
                raise EnrichmentObservabilityError()
        elif self.sanitized_error_code is not None:
            raise EnrichmentObservabilityError()


@dataclass(frozen=True, slots=True)
class EnrichmentErrorAggregate:
    """One sanitized error-code counter, with no invocation or source reference."""

    code: str
    count: int

    def __post_init__(self) -> None:
        if not _is_sanitized_error_code(self.code) or self.count < 1:
            raise EnrichmentObservabilityError()


@dataclass(frozen=True, slots=True)
class EnrichmentObservabilitySnapshot:
    """Reproducible dashboard payload reconciled to budget and coverage ledgers."""

    enrichment_version: str
    invocation_count: int
    succeeded_invocation_count: int
    failed_invocation_count: int
    quarantined_invocation_count: int
    input_token_count: int
    output_token_count: int
    total_cost_usd: Decimal
    total_latency_ms: int
    p95_latency_ms: int
    coverage: EnrichmentCoverageProjection
    errors: tuple[EnrichmentErrorAggregate, ...]
    fingerprint: str

    def __post_init__(self) -> None:
        if (
            not self.enrichment_version
            or len(self.enrichment_version) > 256
            or self.coverage.enrichment_version != self.enrichment_version
            or min(
                self.invocation_count,
                self.succeeded_invocation_count,
                self.failed_invocation_count,
                self.quarantined_invocation_count,
                self.input_token_count,
                self.output_token_count,
                self.total_latency_ms,
                self.p95_latency_ms,
            )
            < 0
            or not self.total_cost_usd.is_finite()
            or self.total_cost_usd < 0
            or self.invocation_count
            != self.succeeded_invocation_count
            + self.failed_invocation_count
            + self.quarantined_invocation_count
            or self.succeeded_invocation_count != self.coverage.valid_enrichment_count
            or tuple(sorted(self.errors, key=lambda item: item.code)) != self.errors
            or len({item.code for item in self.errors}) != len(self.errors)
            or not _is_hash(self.fingerprint)
            or self.fingerprint != _snapshot_fingerprint(self)
        ):
            raise EnrichmentObservabilityError()

    def dashboard_payload(self) -> dict[str, object]:
        """Return the safe, aggregate-only shape that a local dashboard may render."""

        return {
            "enrichment_version": self.enrichment_version,
            "invocation_count": self.invocation_count,
            "succeeded_invocation_count": self.succeeded_invocation_count,
            "failed_invocation_count": self.failed_invocation_count,
            "quarantined_invocation_count": self.quarantined_invocation_count,
            "input_token_count": self.input_token_count,
            "output_token_count": self.output_token_count,
            "total_cost_usd": format(self.total_cost_usd, "f"),
            "total_latency_ms": self.total_latency_ms,
            "p95_latency_ms": self.p95_latency_ms,
            "coverage": {
                "base_review_count": self.coverage.base_review_count,
                "eligible_review_count": self.coverage.eligible_review_count,
                "valid_enrichment_count": self.coverage.valid_enrichment_count,
                "missing_eligible_review_count": self.coverage.missing_eligible_review_count,
                "coverage_ratio": format(self.coverage.coverage_ratio, "f"),
            },
            "errors": tuple({"code": item.code, "count": item.count} for item in self.errors),
            "fingerprint": self.fingerprint,
        }


def build_enrichment_observability_snapshot(
    *,
    telemetry: tuple[EnrichmentInvocationTelemetry, ...],
    coverage: EnrichmentCoverageProjection,
    budget_committed_usd: Decimal,
) -> EnrichmentObservabilitySnapshot:
    """Aggregate terminal telemetry and fail closed when ledgers do not reconcile."""

    if not budget_committed_usd.is_finite() or budget_committed_usd < 0:
        raise EnrichmentObservabilityError()
    if any(item.enrichment_version != coverage.enrichment_version for item in telemetry):
        raise EnrichmentObservabilityError("AI_ENRICHMENT_OBSERVABILITY_VERSION_MISMATCH")
    if len({item.invocation_id for item in telemetry}) != len(telemetry):
        raise EnrichmentObservabilityError("AI_ENRICHMENT_OBSERVABILITY_DUPLICATE_INVOCATION")

    state_counts = Counter(item.state for item in telemetry)
    successful = state_counts[EnrichmentInvocationState.SUCCEEDED]
    if successful != coverage.valid_enrichment_count:
        raise EnrichmentObservabilityError("AI_ENRICHMENT_OBSERVABILITY_COVERAGE_MISMATCH")

    total_cost = sum((item.cost_usd for item in telemetry), Decimal("0"))
    if total_cost != budget_committed_usd:
        raise EnrichmentObservabilityError("AI_ENRICHMENT_OBSERVABILITY_BUDGET_MISMATCH")

    error_counts = Counter(
        item.sanitized_error_code for item in telemetry if item.sanitized_error_code is not None
    )
    errors = tuple(
        EnrichmentErrorAggregate(code=code, count=count)
        for code, count in sorted(error_counts.items())
    )
    latencies = sorted(item.latency_ms for item in telemetry)
    p95 = latencies[ceil(len(latencies) * 0.95) - 1] if latencies else 0
    invocation_count = len(telemetry)
    failed = state_counts[EnrichmentInvocationState.FAILED]
    quarantined = state_counts[EnrichmentInvocationState.QUARANTINED]
    input_tokens = sum(item.input_tokens for item in telemetry)
    output_tokens = sum(item.output_tokens for item in telemetry)
    total_latency = sum(item.latency_ms for item in telemetry)
    snapshot = EnrichmentObservabilitySnapshot(
        enrichment_version=coverage.enrichment_version,
        invocation_count=invocation_count,
        succeeded_invocation_count=successful,
        failed_invocation_count=failed,
        quarantined_invocation_count=quarantined,
        input_token_count=input_tokens,
        output_token_count=output_tokens,
        total_cost_usd=total_cost,
        total_latency_ms=total_latency,
        p95_latency_ms=p95,
        coverage=coverage,
        errors=errors,
        fingerprint=_snapshot_fingerprint_values(
            enrichment_version=coverage.enrichment_version,
            invocation_count=invocation_count,
            succeeded_invocation_count=successful,
            failed_invocation_count=failed,
            quarantined_invocation_count=quarantined,
            input_token_count=input_tokens,
            output_token_count=output_tokens,
            total_cost_usd=total_cost,
            total_latency_ms=total_latency,
            p95_latency_ms=p95,
            coverage=coverage,
            errors=errors,
        ),
    )
    return snapshot


def _snapshot_fingerprint(snapshot: EnrichmentObservabilitySnapshot) -> str:
    return _snapshot_fingerprint_values(
        enrichment_version=snapshot.enrichment_version,
        invocation_count=snapshot.invocation_count,
        succeeded_invocation_count=snapshot.succeeded_invocation_count,
        failed_invocation_count=snapshot.failed_invocation_count,
        quarantined_invocation_count=snapshot.quarantined_invocation_count,
        input_token_count=snapshot.input_token_count,
        output_token_count=snapshot.output_token_count,
        total_cost_usd=snapshot.total_cost_usd,
        total_latency_ms=snapshot.total_latency_ms,
        p95_latency_ms=snapshot.p95_latency_ms,
        coverage=snapshot.coverage,
        errors=snapshot.errors,
    )


def _snapshot_fingerprint_values(
    *,
    enrichment_version: str,
    invocation_count: int,
    succeeded_invocation_count: int,
    failed_invocation_count: int,
    quarantined_invocation_count: int,
    input_token_count: int,
    output_token_count: int,
    total_cost_usd: Decimal,
    total_latency_ms: int,
    p95_latency_ms: int,
    coverage: EnrichmentCoverageProjection,
    errors: tuple[EnrichmentErrorAggregate, ...],
) -> str:
    payload = {
        "coverage": {
            "base_review_count": coverage.base_review_count,
            "coverage_ratio": format(coverage.coverage_ratio, "f"),
            "eligible_review_count": coverage.eligible_review_count,
            "missing_eligible_review_count": coverage.missing_eligible_review_count,
            "valid_enrichment_count": coverage.valid_enrichment_count,
        },
        "enrichment_version": enrichment_version,
        "errors": tuple((item.code, item.count) for item in errors),
        "failed_invocation_count": failed_invocation_count,
        "input_token_count": input_token_count,
        "invocation_count": invocation_count,
        "output_token_count": output_token_count,
        "p95_latency_ms": p95_latency_ms,
        "quarantined_invocation_count": quarantined_invocation_count,
        "succeeded_invocation_count": succeeded_invocation_count,
        "total_cost_usd": format(total_cost_usd, "f"),
        "total_latency_ms": total_latency_ms,
    }
    return hashlib.sha256(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()


def _is_hash(value: str) -> bool:
    return len(value) == 64 and all(character in _SHA256 for character in value)


def _is_sanitized_error_code(value: str | None) -> bool:
    return (
        value is not None
        and bool(value)
        and len(value) <= 128
        and all(
            character.isupper() or character.isdigit() or character == "_" for character in value
        )
    )
