"""Typed audit boundary with an in-memory deterministic fake."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Protocol
from uuid import UUID, uuid4

from reviewlens.clock import Clock, SystemClock

type AuditScalar = str | int | float | bool | None
type AuditValue = AuditScalar | tuple[AuditScalar, ...]


class AuditOutcome(StrEnum):
    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DENIED = "denied"


@dataclass(frozen=True, slots=True)
class AuditEvent:
    event_id: str
    occurred_at: str
    trace_id: str
    component: str
    action: str
    outcome: AuditOutcome
    metadata: Mapping[str, AuditValue]


class AuditSink(Protocol):
    """Storage boundary implemented by the M1 fake and later Snowflake ledger."""

    def append(self, event: AuditEvent) -> None: ...


class InMemoryAuditSink:
    """Append-only audit fake; exposed records are immutable snapshots."""

    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    @property
    def events(self) -> tuple[AuditEvent, ...]:
        return tuple(self._events)

    def append(self, event: AuditEvent) -> None:
        self._events.append(event)


_SAFE_NAME = re.compile(r"^[a-z][a-z0-9_.-]{1,63}$")
_SENSITIVE_KEY = re.compile(
    r"(?:authorization|credential|password|passphrase|(?:api|access|private)[_-]?key|secret|token)",
    re.IGNORECASE,
)


class AuditRecorder:
    """Creates sanitized structured events without coupling callers to storage."""

    def __init__(
        self,
        sink: AuditSink,
        *,
        clock: Clock | None = None,
        id_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self._sink = sink
        self._clock = clock or SystemClock()
        self._id_factory = id_factory

    def record(
        self,
        *,
        trace_id: str,
        component: str,
        action: str,
        outcome: AuditOutcome,
        metadata: Mapping[str, AuditValue] | None = None,
    ) -> AuditEvent:
        for label, value in (("component", component), ("action", action)):
            if not _SAFE_NAME.fullmatch(value):
                raise ValueError(f"audit {label} must be a safe stable name")
        if not trace_id or len(trace_id) > 128:
            raise ValueError("audit trace_id must contain 1 to 128 characters")
        safe_metadata = dict(metadata or {})
        sensitive_key = next(
            (key for key in safe_metadata if _SENSITIVE_KEY.search(key)),
            None,
        )
        if sensitive_key is not None:
            raise ValueError("audit metadata contains a sensitive key")
        event = AuditEvent(
            event_id=str(self._id_factory()),
            occurred_at=self._clock.now().isoformat().replace("+00:00", "Z"),
            trace_id=trace_id,
            component=component,
            action=action,
            outcome=outcome,
            metadata=MappingProxyType(safe_metadata),
        )
        self._sink.append(event)
        return event
