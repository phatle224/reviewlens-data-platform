"""Deterministic in-memory M4 ledger contract; Snowflake persistence follows it."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum

_SHA256_LENGTH = 64


class EnrichmentLedgerConflict(ValueError):
    """Raised when an idempotency key is replayed with a different payload."""


class EnrichmentTransitionDenied(ValueError):
    """Raised when an invocation cannot make the requested state transition."""


class EnrichmentRunState(StrEnum):
    PLANNED = "planned"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class EnrichmentInvocationState(StrEnum):
    PLANNED = "planned"
    DISPATCHED = "dispatched"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    QUARANTINED = "quarantined"


@dataclass(frozen=True, slots=True)
class EnrichmentRun:
    enrichment_run_id: str
    source_release_id: str
    enrichment_version: str
    selection_sha256: str
    state: EnrichmentRunState


@dataclass(frozen=True, slots=True)
class EnrichmentInvocation:
    invocation_id: str
    enrichment_run_id: str
    source_record_hash: str
    input_sha256: str
    attempt_number: int
    state: EnrichmentInvocationState
    sanitized_error_code: str | None = None


@dataclass(frozen=True, slots=True)
class EnrichmentResultMap:
    result_map_id: str
    enrichment_run_id: str
    source_record_hash: str
    enrichment_version: str
    invocation_id: str
    result_sha256: str


class InMemoryEnrichmentLedger:
    """Append-only event semantics with deterministic replay-safe identifiers."""

    def __init__(self) -> None:
        self._runs: dict[str, EnrichmentRun] = {}
        self._invocations: dict[str, EnrichmentInvocation] = {}
        self._results: dict[tuple[str, str], EnrichmentResultMap] = {}

    @property
    def runs(self) -> tuple[EnrichmentRun, ...]:
        return tuple(self._runs.values())

    @property
    def invocations(self) -> tuple[EnrichmentInvocation, ...]:
        return tuple(self._invocations.values())

    @property
    def result_maps(self) -> tuple[EnrichmentResultMap, ...]:
        return tuple(self._results.values())

    def register_run(
        self,
        *,
        source_release_id: str,
        enrichment_version: str,
        selection_sha256: str,
    ) -> EnrichmentRun:
        _require_digest(selection_sha256, "selection_sha256")
        run_id = _stable_id("run", source_release_id, enrichment_version, selection_sha256)
        planned = EnrichmentRun(
            enrichment_run_id=run_id,
            source_release_id=source_release_id,
            enrichment_version=enrichment_version,
            selection_sha256=selection_sha256,
            state=EnrichmentRunState.PLANNED,
        )
        return self._put_idempotent(self._runs, run_id, planned)

    def transition_run(self, run_id: str, *, target: EnrichmentRunState) -> EnrichmentRun:
        current = self._runs[run_id]
        if current.state is target:
            return current
        legal = {
            EnrichmentRunState.PLANNED: {EnrichmentRunState.RUNNING, EnrichmentRunState.FAILED},
            EnrichmentRunState.RUNNING: {EnrichmentRunState.SUCCEEDED, EnrichmentRunState.FAILED},
            EnrichmentRunState.SUCCEEDED: set(),
            EnrichmentRunState.FAILED: set(),
        }
        if target not in legal[current.state]:
            raise EnrichmentTransitionDenied("AI_ENRICHMENT_TRANSITION_DENIED")
        updated = EnrichmentRun(
            enrichment_run_id=current.enrichment_run_id,
            source_release_id=current.source_release_id,
            enrichment_version=current.enrichment_version,
            selection_sha256=current.selection_sha256,
            state=target,
        )
        self._runs[run_id] = updated
        return updated

    def register_invocation(
        self,
        *,
        enrichment_run_id: str,
        source_record_hash: str,
        input_sha256: str,
        attempt_number: int,
    ) -> EnrichmentInvocation:
        if enrichment_run_id not in self._runs:
            raise EnrichmentTransitionDenied("AI_ENRICHMENT_RUN_NOT_FOUND")
        _require_digest(source_record_hash, "source_record_hash")
        _require_digest(input_sha256, "input_sha256")
        if attempt_number < 1:
            raise ValueError("attempt_number must be positive")
        invocation_id = _stable_id(
            "invocation", enrichment_run_id, source_record_hash, input_sha256, str(attempt_number)
        )
        planned = EnrichmentInvocation(
            invocation_id=invocation_id,
            enrichment_run_id=enrichment_run_id,
            source_record_hash=source_record_hash,
            input_sha256=input_sha256,
            attempt_number=attempt_number,
            state=EnrichmentInvocationState.PLANNED,
        )
        return self._put_idempotent(self._invocations, invocation_id, planned)

    def transition_invocation(
        self,
        invocation_id: str,
        *,
        target: EnrichmentInvocationState,
        sanitized_error_code: str | None = None,
    ) -> EnrichmentInvocation:
        current = self._invocations[invocation_id]
        if current.state is target and current.sanitized_error_code == sanitized_error_code:
            return current
        legal = {
            EnrichmentInvocationState.PLANNED: {
                EnrichmentInvocationState.DISPATCHED,
                EnrichmentInvocationState.QUARANTINED,
            },
            EnrichmentInvocationState.DISPATCHED: {
                EnrichmentInvocationState.SUCCEEDED,
                EnrichmentInvocationState.FAILED,
                EnrichmentInvocationState.QUARANTINED,
            },
            EnrichmentInvocationState.SUCCEEDED: set(),
            EnrichmentInvocationState.FAILED: set(),
            EnrichmentInvocationState.QUARANTINED: set(),
        }
        if target not in legal[current.state]:
            raise EnrichmentTransitionDenied("AI_ENRICHMENT_TRANSITION_DENIED")
        if target in {EnrichmentInvocationState.FAILED, EnrichmentInvocationState.QUARANTINED}:
            if not sanitized_error_code or len(sanitized_error_code) > 128:
                raise ValueError("terminal failure requires a sanitized error code")
        elif sanitized_error_code is not None:
            raise ValueError("only failure or quarantine may carry an error code")
        updated = EnrichmentInvocation(
            invocation_id=current.invocation_id,
            enrichment_run_id=current.enrichment_run_id,
            source_record_hash=current.source_record_hash,
            input_sha256=current.input_sha256,
            attempt_number=current.attempt_number,
            state=target,
            sanitized_error_code=sanitized_error_code,
        )
        self._invocations[invocation_id] = updated
        return updated

    def record_result_map(
        self,
        *,
        invocation_id: str,
        result_sha256: str,
    ) -> EnrichmentResultMap:
        _require_digest(result_sha256, "result_sha256")
        invocation = self._invocations[invocation_id]
        if invocation.state is not EnrichmentInvocationState.SUCCEEDED:
            raise EnrichmentTransitionDenied("AI_ENRICHMENT_RESULT_NOT_VALIDATED")
        run = self._runs[invocation.enrichment_run_id]
        key = (invocation.source_record_hash, run.enrichment_version)
        result = EnrichmentResultMap(
            result_map_id=_stable_id("result", invocation_id, result_sha256),
            enrichment_run_id=run.enrichment_run_id,
            source_record_hash=invocation.source_record_hash,
            enrichment_version=run.enrichment_version,
            invocation_id=invocation_id,
            result_sha256=result_sha256,
        )
        existing = self._results.get(key)
        if existing is None:
            self._results[key] = result
            return result
        if existing == result:
            return existing
        raise EnrichmentLedgerConflict("AI_ENRICHMENT_IDEMPOTENCY_CONFLICT")

    @staticmethod
    def _put_idempotent[T](store: dict[str, T], key: str, value: T) -> T:
        existing = store.get(key)
        if existing is None:
            store[key] = value
            return value
        if existing == value:
            return existing
        raise EnrichmentLedgerConflict("AI_ENRICHMENT_IDEMPOTENCY_CONFLICT")


def _stable_id(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def _require_digest(value: str, label: str) -> None:
    if len(value) != _SHA256_LENGTH or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{label} must be a lower-case SHA-256 digest")
