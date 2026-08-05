"""Injectable UTC clocks for deterministic runtime behavior and tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    """Small time boundary used by audit and future orchestration code."""

    def now(self) -> datetime: ...


class SystemClock:
    """Production clock that always returns an aware UTC timestamp."""

    def now(self) -> datetime:
        return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class FrozenClock:
    """Deterministic clock fake for unit and contract tests."""

    instant: datetime

    def __post_init__(self) -> None:
        if self.instant.tzinfo is None or self.instant.utcoffset() is None:
            raise ValueError("frozen clock requires a timezone-aware instant")
        object.__setattr__(self, "instant", self.instant.astimezone(UTC))

    def now(self) -> datetime:
        return self.instant
