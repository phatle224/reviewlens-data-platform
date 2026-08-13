"""Append-only ingestion audit state machine with deterministic in-memory storage."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Final, Protocol
from uuid import uuid4

from reviewlens.clock import Clock, SystemClock
from reviewlens.ingestion.identity import attempt_id

AUDIT_LEDGER_VERSION = 1
_SAFE_ACTOR = re.compile(r"^[a-z][a-z0-9_.-]{1,63}$")
_SAFE_FILE = re.compile(r"^[a-z0-9_]+\.csv$")
_SAFE_STATUS = re.compile(r"^[A-Z][A-Z0-9_]{1,31}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SOURCE_RELEASE = re.compile(r"^olist_[0-9a-f]{64}$")
_INGESTION_BATCH = re.compile(r"^batch_[0-9a-f]{64}$")


class IngestionState(StrEnum):
    DISCOVERED = "DISCOVERED"
    VALIDATED = "VALIDATED"
    UPLOADED = "UPLOADED"
    BRONZE_LOADED = "BRONZE_LOADED"
    RECONCILED = "RECONCILED"
    FAILED = "FAILED"


_NEXT_STATE: Final = {
    IngestionState.DISCOVERED: IngestionState.VALIDATED,
    IngestionState.VALIDATED: IngestionState.UPLOADED,
    IngestionState.UPLOADED: IngestionState.BRONZE_LOADED,
    IngestionState.BRONZE_LOADED: IngestionState.RECONCILED,
}


class IngestionAuditError(RuntimeError):
    code = "INGESTION_AUDIT_INVALID"

    def __init__(self) -> None:
        super().__init__(self.code)


class IngestionLeaseUnavailable(IngestionAuditError):
    code = "INGESTION_LEASE_UNAVAILABLE"


class IngestionTransitionDenied(IngestionAuditError):
    code = "INGESTION_TRANSITION_DENIED"


class IngestionAuditConflict(IngestionAuditError):
    code = "INGESTION_AUDIT_CONFLICT"


@dataclass(frozen=True, slots=True)
class IngestionLease:
    dataset_run_id: str
    attempt_id: str
    attempt_number: int
    owner: str
    token: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class IngestionStateEvent:
    event_id: str
    ledger_schema_version: int
    source_release_id: str
    ingestion_batch_id: str
    dataset_run_id: str
    attempt_id: str
    state: IngestionState
    event_at: datetime
    trace_id: str
    record_count: int | None
    reason_code: str | None


@dataclass(frozen=True, slots=True)
class SourceFileAuditEvent:
    event_id: str
    ledger_schema_version: int
    source_release_id: str
    ingestion_batch_id: str
    dataset_run_id: str
    attempt_id: str
    source_file_name: str
    source_object_sha256: str
    source_size_bytes: int
    physical_row_count: int
    accepted_row_count: int
    rejected_row_count: int
    parse_failed_row_count: int
    status: str
    event_at: datetime
    trace_id: str


@dataclass(slots=True)
class _AttemptState:
    lease: IngestionLease
    state: IngestionState
    source_release_id: str
    ingestion_batch_id: str


class IngestionAuditRepository(Protocol):
    """Storage port implemented by the deterministic fake and later Snowflake adapter."""

    def record_source_file(
        self,
        lease: IngestionLease,
        *,
        idempotency_key: str,
        source_release_id: str,
        ingestion_batch_id: str,
        source_file_name: str,
        source_object_sha256: str,
        source_size_bytes: int,
        physical_row_count: int,
        accepted_row_count: int,
        rejected_row_count: int,
        parse_failed_row_count: int,
        status: str,
        trace_id: str,
    ) -> SourceFileAuditEvent: ...


class InMemoryIngestionAuditRepository:
    """Deterministic fake matching the future Snowflake append-only repository contract."""

    def __init__(self, *, clock: Clock | None = None) -> None:
        self._clock = clock or SystemClock()
        self._attempts: dict[str, list[_AttemptState]] = {}
        self._state_events: list[IngestionStateEvent] = []
        self._file_events: list[SourceFileAuditEvent] = []
        self._file_event_by_key: dict[tuple[str, str], SourceFileAuditEvent] = {}

    @property
    def state_events(self) -> tuple[IngestionStateEvent, ...]:
        return tuple(self._state_events)

    @property
    def file_events(self) -> tuple[SourceFileAuditEvent, ...]:
        return tuple(self._file_events)

    def claim(
        self,
        *,
        source_release_id: str,
        ingestion_batch_id: str,
        dataset_run_id: str,
        owner: str,
        trace_id: str,
        lease_seconds: int = 300,
    ) -> IngestionLease:
        _validate_common(owner=owner, trace_id=trace_id)
        _validate_source_ids(source_release_id, ingestion_batch_id)
        if not 1 <= lease_seconds <= 3_600:
            raise IngestionAuditError()
        now = self._clock.now()
        attempts = self._attempts.setdefault(dataset_run_id, [])
        if attempts:
            current = attempts[-1]
            if (
                current.source_release_id != source_release_id
                or current.ingestion_batch_id != ingestion_batch_id
            ):
                raise IngestionAuditConflict()
            if current.state not in {IngestionState.RECONCILED, IngestionState.FAILED}:
                if now < current.lease.expires_at:
                    if current.lease.owner == owner:
                        return current.lease
                    raise IngestionLeaseUnavailable()
                self._append_state_event(
                    current,
                    source_release_id=source_release_id,
                    ingestion_batch_id=ingestion_batch_id,
                    dataset_run_id=dataset_run_id,
                    target=IngestionState.FAILED,
                    trace_id=trace_id,
                    record_count=None,
                    reason_code="LEASE_EXPIRED",
                    event_at=now,
                )
                current.state = IngestionState.FAILED

        attempt_number = len(attempts) + 1
        current_attempt_id = attempt_id(
            dataset_run_id=dataset_run_id,
            attempt_number=attempt_number,
        )
        lease = IngestionLease(
            dataset_run_id=dataset_run_id,
            attempt_id=current_attempt_id,
            attempt_number=attempt_number,
            owner=owner,
            token=uuid4().hex,
            expires_at=now + timedelta(seconds=lease_seconds),
        )
        attempt = _AttemptState(
            lease=lease,
            state=IngestionState.DISCOVERED,
            source_release_id=source_release_id,
            ingestion_batch_id=ingestion_batch_id,
        )
        attempts.append(attempt)
        self._append_state_event(
            attempt,
            source_release_id=source_release_id,
            ingestion_batch_id=ingestion_batch_id,
            dataset_run_id=dataset_run_id,
            target=IngestionState.DISCOVERED,
            trace_id=trace_id,
            record_count=None,
            reason_code=None,
            event_at=now,
        )
        return lease

    def transition(
        self,
        lease: IngestionLease,
        *,
        source_release_id: str,
        ingestion_batch_id: str,
        target: IngestionState,
        trace_id: str,
        record_count: int | None = None,
        reason_code: str | None = None,
    ) -> IngestionStateEvent:
        _validate_common(owner=lease.owner, trace_id=trace_id)
        _validate_source_ids(source_release_id, ingestion_batch_id)
        if record_count is not None and record_count < 0:
            raise IngestionAuditError()
        attempt = self._active_attempt(lease)
        if (
            attempt.source_release_id != source_release_id
            or attempt.ingestion_batch_id != ingestion_batch_id
        ):
            raise IngestionAuditConflict()
        if target is attempt.state:
            existing = next(
                event
                for event in reversed(self._state_events)
                if event.attempt_id == lease.attempt_id and event.state is target
            )
            if existing.record_count != record_count or existing.reason_code != reason_code:
                raise IngestionAuditConflict()
            return existing
        legal_next = _NEXT_STATE.get(attempt.state)
        if target is not IngestionState.FAILED and target is not legal_next:
            raise IngestionTransitionDenied()
        if attempt.state in {IngestionState.RECONCILED, IngestionState.FAILED}:
            raise IngestionTransitionDenied()
        event = self._append_state_event(
            attempt,
            source_release_id=source_release_id,
            ingestion_batch_id=ingestion_batch_id,
            dataset_run_id=lease.dataset_run_id,
            target=target,
            trace_id=trace_id,
            record_count=record_count,
            reason_code=reason_code,
            event_at=self._clock.now(),
        )
        attempt.state = target
        return event

    def record_source_file(
        self,
        lease: IngestionLease,
        *,
        idempotency_key: str,
        source_release_id: str,
        ingestion_batch_id: str,
        source_file_name: str,
        source_object_sha256: str,
        source_size_bytes: int,
        physical_row_count: int,
        accepted_row_count: int,
        rejected_row_count: int,
        parse_failed_row_count: int,
        status: str,
        trace_id: str,
    ) -> SourceFileAuditEvent:
        attempt = self._active_attempt(lease)
        _validate_common(owner=lease.owner, trace_id=trace_id)
        _validate_source_ids(source_release_id, ingestion_batch_id)
        if (
            attempt.source_release_id != source_release_id
            or attempt.ingestion_batch_id != ingestion_batch_id
        ):
            raise IngestionAuditConflict()
        counts = (
            source_size_bytes,
            physical_row_count,
            accepted_row_count,
            rejected_row_count,
            parse_failed_row_count,
        )
        if any(value < 0 for value in counts):
            raise IngestionAuditError()
        if accepted_row_count + rejected_row_count + parse_failed_row_count != physical_row_count:
            raise IngestionAuditError()
        if (
            not idempotency_key
            or len(idempotency_key) > 128
            or _SAFE_FILE.fullmatch(source_file_name) is None
            or _SAFE_STATUS.fullmatch(status) is None
        ):
            raise IngestionAuditError()
        if _SHA256.fullmatch(source_object_sha256) is None:
            raise IngestionAuditError()
        event = SourceFileAuditEvent(
            event_id=_event_id("source_file", lease.attempt_id, idempotency_key),
            ledger_schema_version=AUDIT_LEDGER_VERSION,
            source_release_id=source_release_id,
            ingestion_batch_id=ingestion_batch_id,
            dataset_run_id=lease.dataset_run_id,
            attempt_id=lease.attempt_id,
            source_file_name=source_file_name,
            source_object_sha256=source_object_sha256,
            source_size_bytes=source_size_bytes,
            physical_row_count=physical_row_count,
            accepted_row_count=accepted_row_count,
            rejected_row_count=rejected_row_count,
            parse_failed_row_count=parse_failed_row_count,
            status=status,
            event_at=self._clock.now(),
            trace_id=trace_id,
        )
        key = (lease.attempt_id, idempotency_key)
        existing = self._file_event_by_key.get(key)
        if existing is not None:
            if _file_semantics(existing) != _file_semantics(event):
                raise IngestionAuditConflict()
            return existing
        self._file_event_by_key[key] = event
        self._file_events.append(event)
        return event

    def current_state(self, dataset_run_id: str) -> IngestionState | None:
        attempts = self._attempts.get(dataset_run_id)
        return attempts[-1].state if attempts else None

    def _active_attempt(self, lease: IngestionLease) -> _AttemptState:
        attempts = self._attempts.get(lease.dataset_run_id)
        if not attempts or attempts[-1].lease.token != lease.token:
            raise IngestionLeaseUnavailable()
        attempt = attempts[-1]
        if self._clock.now() >= attempt.lease.expires_at:
            raise IngestionLeaseUnavailable()
        return attempt

    def _append_state_event(
        self,
        attempt: _AttemptState,
        *,
        source_release_id: str,
        ingestion_batch_id: str,
        dataset_run_id: str,
        target: IngestionState,
        trace_id: str,
        record_count: int | None,
        reason_code: str | None,
        event_at: datetime,
    ) -> IngestionStateEvent:
        event = IngestionStateEvent(
            event_id=_event_id("ingestion", attempt.lease.attempt_id, target.value),
            ledger_schema_version=AUDIT_LEDGER_VERSION,
            source_release_id=source_release_id,
            ingestion_batch_id=ingestion_batch_id,
            dataset_run_id=dataset_run_id,
            attempt_id=attempt.lease.attempt_id,
            state=target,
            event_at=event_at,
            trace_id=trace_id,
            record_count=record_count,
            reason_code=reason_code,
        )
        self._state_events.append(event)
        return event


def _event_id(*parts: str) -> str:
    encoded = json.dumps(parts, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def _validate_common(*, owner: str, trace_id: str) -> None:
    if _SAFE_ACTOR.fullmatch(owner) is None or not trace_id or len(trace_id) > 128:
        raise IngestionAuditError()


def _validate_source_ids(source_release_id: str, ingestion_batch_id: str) -> None:
    if (
        _SOURCE_RELEASE.fullmatch(source_release_id) is None
        or _INGESTION_BATCH.fullmatch(ingestion_batch_id) is None
    ):
        raise IngestionAuditError()


def _file_semantics(event: SourceFileAuditEvent) -> tuple[object, ...]:
    return (
        event.source_release_id,
        event.ingestion_batch_id,
        event.dataset_run_id,
        event.attempt_id,
        event.source_file_name,
        event.source_object_sha256,
        event.source_size_bytes,
        event.physical_row_count,
        event.accepted_row_count,
        event.rejected_row_count,
        event.parse_failed_row_count,
        event.status,
        event.trace_id,
    )
