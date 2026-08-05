from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from reviewlens.clock import FrozenClock, SystemClock
from reviewlens.providers.audit import AuditOutcome, AuditRecorder, InMemoryAuditSink


def test_audit_recorder_is_deterministic_append_only_and_secret_safe() -> None:
    sink = InMemoryAuditSink()
    recorder = AuditRecorder(
        sink,
        clock=FrozenClock(datetime(2026, 8, 5, 12, 30, tzinfo=UTC)),
        id_factory=lambda: UUID("00000000-0000-0000-0000-000000000001"),
    )

    event = recorder.record(
        trace_id="trace-001",
        component="provider.openrouter",
        action="embedding.request",
        outcome=AuditOutcome.SUCCEEDED,
        metadata={"data_class": "synthetic", "record_count": 2, "cost_usd": 0.0},
    )

    assert event.event_id == "00000000-0000-0000-0000-000000000001"
    assert event.occurred_at == "2026-08-05T12:30:00Z"
    assert event.metadata["record_count"] == 2
    assert sink.events == (event,)
    with pytest.raises(TypeError):
        event.metadata["record_count"] = 3  # type: ignore[index]


@pytest.mark.parametrize(
    "key",
    [
        "api_token",
        "api_key",
        "access_key_id",
        "password",
        "private-key",
        "authorization",
        "client_secret",
    ],
)
def test_audit_metadata_rejects_sensitive_keys(key: str) -> None:
    recorder = AuditRecorder(InMemoryAuditSink())
    with pytest.raises(ValueError, match="sensitive key") as captured:
        recorder.record(
            trace_id="trace-001",
            component="provider.r2",
            action="object.read",
            outcome=AuditOutcome.DENIED,
            metadata={key: "seeded-secret-value"},
        )
    assert "seeded-secret-value" not in str(captured.value)


def test_audit_rejects_unstable_names_and_empty_trace() -> None:
    recorder = AuditRecorder(InMemoryAuditSink())
    with pytest.raises(ValueError, match="safe stable name"):
        recorder.record(
            trace_id="trace",
            component="Bad Component",
            action="read",
            outcome=AuditOutcome.FAILED,
        )
    with pytest.raises(ValueError, match="trace_id"):
        recorder.record(
            trace_id="",
            component="provider.r2",
            action="object.read",
            outcome=AuditOutcome.FAILED,
        )


def test_clock_boundaries_always_return_aware_utc() -> None:
    local_instant = datetime.fromisoformat("2026-08-05T19:30:00+07:00")
    frozen = FrozenClock(local_instant)
    assert frozen.now() == datetime(2026, 8, 5, 12, 30, tzinfo=UTC)
    assert SystemClock().now().tzinfo is UTC

    with pytest.raises(ValueError, match="timezone-aware"):
        FrozenClock(datetime(2026, 8, 5, 12, 30))
