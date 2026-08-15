"""Deterministic metric-dictionary oracles for M3 Gold marts."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

METRIC_POLICY_VERSION = "olist-metric-dictionary-v1"
REPEAT_CUSTOMER_POLICY_VERSION = "olist-repeat-customer-lifetime-v1"
REVIEW_ALLOCATION_POLICY_VERSION = "olist-review-item-equal-weight-v1"

_RATE_QUANTUM = Decimal("0.000000000000000001")
_AVERAGE_QUANTUM = Decimal("0.000001")
_ZERO = Decimal(0)
_HASH = re.compile(r"^[0-9a-f]{64}$")


class MetricContractError(ValueError):
    """Sanitized metric-contract failure without source values."""

    code = "WAREHOUSE_METRIC_INVALID"

    def __init__(self) -> None:
        super().__init__(self.code)


@dataclass(frozen=True, slots=True)
class OrderMetricInput:
    order_status: str
    delivery_interval_valid: bool
    delivery_lead_seconds: int | None
    delivery_delay_seconds: int | None
    is_on_time_delivery: bool | None
    gross_merchandise_value: Decimal
    freight_value: Decimal
    payment_value: Decimal

    def __post_init__(self) -> None:
        delivery_values = (
            self.delivery_lead_seconds,
            self.delivery_delay_seconds,
            self.is_on_time_delivery,
        )
        if (
            not self.order_status.strip()
            or any(
                value < _ZERO
                for value in (
                    self.gross_merchandise_value,
                    self.freight_value,
                    self.payment_value,
                )
            )
            or (self.delivery_lead_seconds is not None and self.delivery_lead_seconds < 0)
            or (self.delivery_interval_valid and any(value is None for value in delivery_values))
        ):
            raise MetricContractError()


@dataclass(frozen=True, slots=True)
class OrderMetricSummary:
    order_count: int
    delivered_order_count: int
    cancelled_order_count: int
    delivery_eligible_order_count: int
    on_time_order_count: int
    on_time_delivery_rate: Decimal | None
    average_delivery_lead_seconds: Decimal | None
    average_delivery_delay_seconds: Decimal | None
    gross_merchandise_value: Decimal
    freight_value: Decimal
    payment_value: Decimal
    payment_reconciliation_delta: Decimal
    metric_policy_version: str = METRIC_POLICY_VERSION


@dataclass(frozen=True, slots=True)
class ReviewMetricInput:
    allocation_weight: Decimal
    allocated_review_score: Decimal
    allocation_policy_version: str = REVIEW_ALLOCATION_POLICY_VERSION

    def __post_init__(self) -> None:
        if (
            self.allocation_weight <= _ZERO
            or self.allocation_weight > Decimal(1)
            or self.allocated_review_score < self.allocation_weight
            or self.allocated_review_score > self.allocation_weight * 5
            or self.allocation_policy_version != REVIEW_ALLOCATION_POLICY_VERSION
        ):
            raise MetricContractError()


@dataclass(frozen=True, slots=True)
class ReviewMetricSummary:
    allocated_review_count: Decimal
    allocated_review_score: Decimal
    average_review_score: Decimal | None
    allocation_policy_version: str = REVIEW_ALLOCATION_POLICY_VERSION
    metric_policy_version: str = METRIC_POLICY_VERSION


@dataclass(frozen=True, slots=True)
class CustomerCohortInput:
    repeat_customer_key: str | None
    lifetime_order_count: int

    def __post_init__(self) -> None:
        if (
            self.lifetime_order_count < 0
            or (self.repeat_customer_key is None and self.lifetime_order_count != 0)
            or (
                self.repeat_customer_key is not None
                and (
                    _HASH.fullmatch(self.repeat_customer_key) is None
                    or self.lifetime_order_count < 1
                )
            )
        ):
            raise MetricContractError()


@dataclass(frozen=True, slots=True)
class CustomerCohortSummary:
    customer_count: int
    repeat_customer_count: int
    repeat_customer_rate: Decimal | None
    unknown_customer_order_count: int
    repeat_customer_definition_version: str = REPEAT_CUSTOMER_POLICY_VERSION


def _average(values: tuple[int, ...]) -> Decimal | None:
    if not values:
        return None
    return (Decimal(sum(values)) / len(values)).quantize(
        _AVERAGE_QUANTUM,
        rounding=ROUND_HALF_UP,
    )


def _rate(numerator: int | Decimal, denominator: int | Decimal) -> Decimal | None:
    if denominator == 0:
        return None
    if numerator < 0 or denominator < 0 or numerator > denominator:
        raise MetricContractError()
    return (Decimal(numerator) / Decimal(denominator)).quantize(
        _RATE_QUANTUM,
        rounding=ROUND_HALF_UP,
    )


def summarize_order_metrics(rows: Iterable[OrderMetricInput]) -> OrderMetricSummary:
    """Apply metric dictionary v1 without multiplying order-grain measures."""

    materialized = tuple(rows)
    eligible = tuple(
        row
        for row in materialized
        if row.order_status == "delivered"
        and row.delivery_interval_valid
        and row.delivery_lead_seconds is not None
        and row.delivery_delay_seconds is not None
        and row.is_on_time_delivery is not None
    )
    on_time_count = sum(row.is_on_time_delivery is True for row in eligible)
    gross_merchandise_value = sum(
        (row.gross_merchandise_value for row in materialized),
        start=_ZERO,
    )
    freight_value = sum((row.freight_value for row in materialized), start=_ZERO)
    payment_value = sum((row.payment_value for row in materialized), start=_ZERO)
    return OrderMetricSummary(
        order_count=len(materialized),
        delivered_order_count=sum(row.order_status == "delivered" for row in materialized),
        cancelled_order_count=sum(row.order_status == "canceled" for row in materialized),
        delivery_eligible_order_count=len(eligible),
        on_time_order_count=on_time_count,
        on_time_delivery_rate=_rate(on_time_count, len(eligible)),
        average_delivery_lead_seconds=_average(
            tuple(
                row.delivery_lead_seconds
                for row in eligible
                if row.delivery_lead_seconds is not None
            )
        ),
        average_delivery_delay_seconds=_average(
            tuple(
                row.delivery_delay_seconds
                for row in eligible
                if row.delivery_delay_seconds is not None
            )
        ),
        gross_merchandise_value=gross_merchandise_value,
        freight_value=freight_value,
        payment_value=payment_value,
        payment_reconciliation_delta=(payment_value - gross_merchandise_value - freight_value),
    )


def summarize_review_metrics(rows: Iterable[ReviewMetricInput]) -> ReviewMetricSummary:
    """Aggregate only allocated review measures and retain the policy label."""

    materialized = tuple(rows)
    allocated_review_count = sum(
        (row.allocation_weight for row in materialized),
        start=_ZERO,
    )
    allocated_review_score = sum(
        (row.allocated_review_score for row in materialized),
        start=_ZERO,
    )
    average = (
        None
        if allocated_review_count == 0
        else (allocated_review_score / allocated_review_count).quantize(
            _AVERAGE_QUANTUM,
            rounding=ROUND_HALF_UP,
        )
    )
    return ReviewMetricSummary(
        allocated_review_count=allocated_review_count,
        allocated_review_score=allocated_review_score,
        average_review_score=average,
    )


def summarize_customer_cohort(rows: Iterable[CustomerCohortInput]) -> CustomerCohortSummary:
    """Count distinct known repeat identities active in a selected cohort."""

    materialized = tuple(rows)
    known_counts: dict[str, int] = {}
    for row in materialized:
        if row.repeat_customer_key is None:
            continue
        existing = known_counts.setdefault(
            row.repeat_customer_key,
            row.lifetime_order_count,
        )
        if existing != row.lifetime_order_count:
            raise MetricContractError()
    repeat_customer_count = sum(count > 1 for count in known_counts.values())
    return CustomerCohortSummary(
        customer_count=len(known_counts),
        repeat_customer_count=repeat_customer_count,
        repeat_customer_rate=_rate(repeat_customer_count, len(known_counts)),
        unknown_customer_order_count=sum(row.repeat_customer_key is None for row in materialized),
    )
