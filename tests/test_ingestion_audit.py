from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from reviewlens.ingestion.audit import (
    IngestionAuditConflict,
    IngestionLease,
    IngestionLeaseUnavailable,
    IngestionState,
    IngestionTransitionDenied,
    InMemoryIngestionAuditRepository,
    SourceFileAuditEvent,
)

SOURCE_RELEASE_ID = f"olist_{'0' * 64}"
BATCH_ID = f"batch_{'1' * 64}"
DATASET_RUN_ID = f"dsrun_{'2' * 64}"


@dataclass
class MutableClock:
    instant: datetime

    def now(self) -> datetime:
        return self.instant

    def advance(self, seconds: int) -> None:
        self.instant += timedelta(seconds=seconds)


def _claim(
    repository: InMemoryIngestionAuditRepository, *, owner: str = "worker.one"
) -> IngestionLease:
    return repository.claim(
        source_release_id=SOURCE_RELEASE_ID,
        ingestion_batch_id=BATCH_ID,
        dataset_run_id=DATASET_RUN_ID,
        owner=owner,
        trace_id="trace-1",
        lease_seconds=60,
    )


def _record_source_file(
    repository: InMemoryIngestionAuditRepository,
    lease: IngestionLease,
    *,
    accepted: int = 7,
    rejected: int = 2,
) -> SourceFileAuditEvent:
    return repository.record_source_file(
        lease,
        idempotency_key="olist_orders_dataset.csv",
        source_release_id=SOURCE_RELEASE_ID,
        ingestion_batch_id=BATCH_ID,
        source_file_name="olist_orders_dataset.csv",
        source_object_sha256="a" * 64,
        source_size_bytes=100,
        physical_row_count=10,
        accepted_row_count=accepted,
        rejected_row_count=rejected,
        parse_failed_row_count=1,
        status="QUARANTINED",
        trace_id="trace-1",
    )


def test_audit_legal_transitions_are_append_only_and_idempotent() -> None:
    clock = MutableClock(datetime(2026, 8, 13, tzinfo=UTC))
    repository = InMemoryIngestionAuditRepository(clock=clock)
    lease = _claim(repository)

    assert _claim(repository) == lease
    assert len(repository.state_events) == 1
    for state in (
        IngestionState.VALIDATED,
        IngestionState.UPLOADED,
        IngestionState.BRONZE_LOADED,
        IngestionState.RECONCILED,
    ):
        event = repository.transition(
            lease,
            source_release_id=SOURCE_RELEASE_ID,
            ingestion_batch_id=BATCH_ID,
            target=state,
            trace_id="trace-1",
            record_count=10,
        )
        repeated = repository.transition(
            lease,
            source_release_id=SOURCE_RELEASE_ID,
            ingestion_batch_id=BATCH_ID,
            target=state,
            trace_id="trace-1",
            record_count=10,
        )
        assert repeated is event

    assert repository.current_state(DATASET_RUN_ID) is IngestionState.RECONCILED
    assert [event.state for event in repository.state_events] == [
        IngestionState.DISCOVERED,
        IngestionState.VALIDATED,
        IngestionState.UPLOADED,
        IngestionState.BRONZE_LOADED,
        IngestionState.RECONCILED,
    ]


def test_audit_denies_skipped_conflicting_and_post_terminal_transitions() -> None:
    repository = InMemoryIngestionAuditRepository(
        clock=MutableClock(datetime(2026, 8, 13, tzinfo=UTC))
    )
    lease = _claim(repository)

    with pytest.raises(IngestionTransitionDenied, match="INGESTION_TRANSITION_DENIED"):
        repository.transition(
            lease,
            source_release_id=SOURCE_RELEASE_ID,
            ingestion_batch_id=BATCH_ID,
            target=IngestionState.UPLOADED,
            trace_id="trace-1",
        )

    repository.transition(
        lease,
        source_release_id=SOURCE_RELEASE_ID,
        ingestion_batch_id=BATCH_ID,
        target=IngestionState.VALIDATED,
        trace_id="trace-1",
        record_count=10,
    )
    with pytest.raises(IngestionAuditConflict, match="INGESTION_AUDIT_CONFLICT"):
        repository.transition(
            lease,
            source_release_id=SOURCE_RELEASE_ID,
            ingestion_batch_id=BATCH_ID,
            target=IngestionState.VALIDATED,
            trace_id="trace-1",
            record_count=11,
        )

    repository.transition(
        lease,
        source_release_id=SOURCE_RELEASE_ID,
        ingestion_batch_id=BATCH_ID,
        target=IngestionState.FAILED,
        trace_id="trace-1",
        reason_code="TEST_FAILURE",
    )
    with pytest.raises(IngestionTransitionDenied):
        repository.transition(
            lease,
            source_release_id=SOURCE_RELEASE_ID,
            ingestion_batch_id=BATCH_ID,
            target=IngestionState.UPLOADED,
            trace_id="trace-1",
        )


def test_expired_lease_creates_new_attempt_and_blocks_stale_owner() -> None:
    clock = MutableClock(datetime(2026, 8, 13, tzinfo=UTC))
    repository = InMemoryIngestionAuditRepository(clock=clock)
    first = _claim(repository)

    with pytest.raises(IngestionLeaseUnavailable, match="INGESTION_LEASE_UNAVAILABLE"):
        _claim(repository, owner="worker.two")

    clock.advance(61)
    second = _claim(repository, owner="worker.two")

    assert second.attempt_number == 2
    assert second.attempt_id != first.attempt_id
    assert [event.state for event in repository.state_events] == [
        IngestionState.DISCOVERED,
        IngestionState.FAILED,
        IngestionState.DISCOVERED,
    ]
    assert repository.state_events[1].reason_code == "LEASE_EXPIRED"
    with pytest.raises(IngestionLeaseUnavailable):
        repository.transition(
            first,
            source_release_id=SOURCE_RELEASE_ID,
            ingestion_batch_id=BATCH_ID,
            target=IngestionState.VALIDATED,
            trace_id="trace-1",
        )


def test_source_file_audit_reconciles_and_rejects_same_key_drift() -> None:
    repository = InMemoryIngestionAuditRepository(
        clock=MutableClock(datetime(2026, 8, 13, tzinfo=UTC))
    )
    lease = _claim(repository)
    first = _record_source_file(repository, lease)
    assert _record_source_file(repository, lease) is first
    assert len(repository.file_events) == 1

    with pytest.raises(IngestionAuditConflict, match="INGESTION_AUDIT_CONFLICT"):
        _record_source_file(repository, lease, accepted=8, rejected=1)
