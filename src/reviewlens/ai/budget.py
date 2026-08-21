"""Conservative, durable cost controls for approved AI enrichment dispatches.

The local ledger deliberately stores only aggregate monetary amounts and opaque
reservation IDs.  It must never receive review text, prompts, responses,
natural identifiers, or provider payloads.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path
from uuid import uuid4

from reviewlens.ai.catalog import EnrichmentModelCatalogSnapshot


class EnrichmentBudgetError(RuntimeError):
    """Base class for sanitized cost-control failures."""


class EnrichmentBudgetExceeded(EnrichmentBudgetError):
    """Raised before a provider request would exceed the project cap."""

    def __init__(self) -> None:
        super().__init__("AI_ENRICHMENT_BUDGET_EXHAUSTED")


class EnrichmentBudgetReconciliationError(EnrichmentBudgetError):
    """Raised when actual usage exceeded the pre-dispatch reservation."""

    def __init__(self) -> None:
        super().__init__("AI_ENRICHMENT_ESTIMATE_EXCEEDED")


class EnrichmentBudgetStatus(StrEnum):
    ALLOWED = "allowed"
    WARNING = "warning"


@dataclass(frozen=True, slots=True)
class EnrichmentPricing:
    """Pinned USD token prices from a validated public catalog snapshot."""

    prompt_usd_per_token: Decimal
    completion_usd_per_token: Decimal

    def __post_init__(self) -> None:
        for value in (self.prompt_usd_per_token, self.completion_usd_per_token):
            if not value.is_finite() or value < 0:
                raise ValueError("token prices must be finite and non-negative")

    @classmethod
    def from_catalog(cls, snapshot: EnrichmentModelCatalogSnapshot) -> EnrichmentPricing:
        return cls(
            prompt_usd_per_token=snapshot.prompt_usd_per_token,
            completion_usd_per_token=snapshot.completion_usd_per_token,
        )


@dataclass(frozen=True, slots=True)
class TokenEstimate:
    """Bounded token envelope; values are counts, never text or payloads."""

    prompt_tokens: int
    completion_tokens: int

    def __post_init__(self) -> None:
        if self.prompt_tokens < 0 or self.completion_tokens < 0:
            raise ValueError("token estimates must be non-negative")
        if self.prompt_tokens + self.completion_tokens < 1:
            raise ValueError("token estimate must reserve at least one token")

    def cost_usd(self, pricing: EnrichmentPricing) -> Decimal:
        return (
            Decimal(self.prompt_tokens) * pricing.prompt_usd_per_token
            + Decimal(self.completion_tokens) * pricing.completion_usd_per_token
        )


def estimate_tokens_from_char_count(
    *,
    approved_text_characters: int,
    max_completion_tokens: int,
    control_overhead_tokens: int = 600,
) -> TokenEstimate:
    """Return a conservative request envelope without retaining approved text.

    Four characters per token is intentionally a simple upper-bound heuristic
    for the bounded M4 pilot.  The static controls/schema allowance is explicit
    so callers cannot accidentally budget only the review evidence.
    """

    if approved_text_characters < 0 or max_completion_tokens < 1 or control_overhead_tokens < 0:
        raise ValueError("token-estimation inputs are outside the allowed range")
    evidence_tokens = (approved_text_characters + 3) // 4
    return TokenEstimate(
        prompt_tokens=evidence_tokens + control_overhead_tokens,
        completion_tokens=max_completion_tokens,
    )


@dataclass(frozen=True, slots=True)
class BudgetReservation:
    reservation_id: str
    day: date
    estimated_cost_usd: Decimal
    status: EnrichmentBudgetStatus


class EnrichmentBudget:
    """Fail-closed project cap with optional atomic local persistence.

    A pending reservation counts against the cap.  If the process stops after a
    provider request but before settlement, the conservative reservation remains
    in the ledger rather than allowing an unaccounted follow-up request.
    """

    _SCHEMA_VERSION = 1

    def __init__(
        self,
        *,
        hard_budget_usd: Decimal,
        daily_warning_usd: Decimal,
        ledger_path: Path | None = None,
    ) -> None:
        if (
            not hard_budget_usd.is_finite()
            or not daily_warning_usd.is_finite()
            or hard_budget_usd <= 0
            or daily_warning_usd <= 0
            or daily_warning_usd > hard_budget_usd
        ):
            raise ValueError("budget thresholds must be positive finite USD values")
        self._hard_budget_usd = hard_budget_usd
        self._daily_warning_usd = daily_warning_usd
        self._ledger_path = ledger_path
        self._committed_usd = Decimal("0")
        self._daily_committed_usd: dict[date, Decimal] = {}
        self._reservations: dict[str, tuple[date, Decimal]] = {}
        if ledger_path is not None and ledger_path.exists():
            self._load(ledger_path)

    @property
    def committed_usd(self) -> Decimal:
        return self._committed_usd

    @property
    def reserved_usd(self) -> Decimal:
        return sum((cost for _, cost in self._reservations.values()), Decimal("0"))

    def reserve(
        self,
        *,
        estimate: TokenEstimate,
        pricing: EnrichmentPricing,
        on_day: date,
    ) -> BudgetReservation:
        estimated_cost = estimate.cost_usd(pricing)
        if estimated_cost <= 0:
            raise ValueError("estimated request cost must be positive")
        if self.committed_usd + self.reserved_usd + estimated_cost > self._hard_budget_usd:
            raise EnrichmentBudgetExceeded()
        daily_total = self._daily_total(on_day) + estimated_cost
        status = (
            EnrichmentBudgetStatus.WARNING
            if daily_total >= self._daily_warning_usd
            else EnrichmentBudgetStatus.ALLOWED
        )
        reservation = BudgetReservation(
            reservation_id=uuid4().hex,
            day=on_day,
            estimated_cost_usd=estimated_cost,
            status=status,
        )
        self._reservations[reservation.reservation_id] = (on_day, estimated_cost)
        self._persist()
        return reservation

    def commit(
        self,
        reservation: BudgetReservation,
        *,
        actual: TokenEstimate | None = None,
        pricing: EnrichmentPricing | None = None,
    ) -> None:
        stored = self._reservations.get(reservation.reservation_id)
        if stored != (reservation.day, reservation.estimated_cost_usd):
            raise ValueError("unknown or altered budget reservation")
        actual_cost = reservation.estimated_cost_usd
        if actual is not None:
            if pricing is None:
                raise ValueError("actual token settlement requires pinned pricing")
            actual_cost = actual.cost_usd(pricing)
            if actual_cost > reservation.estimated_cost_usd:
                self._persist()
                raise EnrichmentBudgetReconciliationError()
        del self._reservations[reservation.reservation_id]
        self._committed_usd += actual_cost
        self._daily_committed_usd[reservation.day] = (
            self._daily_committed_usd.get(reservation.day, Decimal("0")) + actual_cost
        )
        self._persist()

    def release(self, reservation: BudgetReservation) -> None:
        stored = self._reservations.get(reservation.reservation_id)
        if stored != (reservation.day, reservation.estimated_cost_usd):
            raise ValueError("unknown or altered budget reservation")
        del self._reservations[reservation.reservation_id]
        self._persist()

    def _daily_total(self, on_day: date) -> Decimal:
        pending = sum(
            (
                cost
                for reservation_day, cost in self._reservations.values()
                if reservation_day == on_day
            ),
            Decimal("0"),
        )
        return self._daily_committed_usd.get(on_day, Decimal("0")) + pending

    def _load(self, path: Path) -> None:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload["schema_version"] != self._SCHEMA_VERSION:
                raise ValueError
            self._committed_usd = _usd(payload["committed_usd"])
            self._daily_committed_usd = {
                date.fromisoformat(day): _usd(cost)
                for day, cost in payload["daily_committed_usd"].items()
            }
            self._reservations = {
                reservation_id: (date.fromisoformat(item["day"]), _usd(item["estimated_cost_usd"]))
                for reservation_id, item in payload["reservations"].items()
            }
        except (KeyError, TypeError, ValueError, InvalidOperation, json.JSONDecodeError):
            raise EnrichmentBudgetError("AI_ENRICHMENT_BUDGET_LEDGER_INVALID") from None
        reservation_costs = (cost for _, cost in self._reservations.values())
        if self._committed_usd < 0 or any(
            cost < 0 for cost in (*self._daily_committed_usd.values(), *reservation_costs)
        ):
            raise EnrichmentBudgetError("AI_ENRICHMENT_BUDGET_LEDGER_INVALID")

    def _persist(self) -> None:
        if self._ledger_path is None:
            return
        self._ledger_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": self._SCHEMA_VERSION,
            "committed_usd": format(self._committed_usd, "f"),
            "daily_committed_usd": {
                day.isoformat(): format(cost, "f")
                for day, cost in sorted(self._daily_committed_usd.items())
            },
            "reservations": {
                reservation_id: {
                    "day": reservation_day.isoformat(),
                    "estimated_cost_usd": format(cost, "f"),
                }
                for reservation_id, (reservation_day, cost) in sorted(self._reservations.items())
            },
        }
        temporary_path = self._ledger_path.with_suffix(".tmp")
        temporary_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        temporary_path.replace(self._ledger_path)


def _usd(value: object) -> Decimal:
    if not isinstance(value, str):
        raise ValueError
    amount = Decimal(value)
    if not amount.is_finite():
        raise ValueError
    return amount
