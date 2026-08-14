"""Deterministic M3 Silver contract oracles for tests and orchestration guards."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Decimal
from enum import StrEnum

REPEAT_CUSTOMER_KEY_VERSION = "reviewlens-repeat-customer-v1"
GEOLOCATION_RULE_VERSION = "olist-geolocation-centroid-v1"
ORDER_SCOPE_VERSION = "olist_order_scope_v1"
ORDER_TIME_POLICY_VERSION = "olist-brazil-local-civil-v1"
AMOUNT_QUALITY_VERSION = "olist-amount-quality-v1"
PRODUCT_CONTRACT_VERSION = "reviewlens-sil-product-v1"
REVIEW_ELIGIBILITY_VERSION = "review-ai-eligibility-v1"

_ALLOWED_ORDER_STATUSES = frozenset(
    {
        "approved",
        "canceled",
        "created",
        "delivered",
        "invoiced",
        "processing",
        "shipped",
        "unavailable",
    }
)
_CENTROID_SCALE = Decimal("0.000000000000000001")


class SilverContractError(ValueError):
    """Stable sanitized Silver contract failure."""

    code = "SILVER_CONTRACT_INVALID"

    def __init__(self) -> None:
        super().__init__(self.code)


class GeolocationQuality(StrEnum):
    VALID = "VALID"
    AMBIGUOUS_LOCATION = "AMBIGUOUS_LOCATION"
    PARTIAL_COORDINATE = "PARTIAL_COORDINATE"
    NO_VALID_COORDINATE = "NO_VALID_COORDINATE"


class OrderScope(StrEnum):
    IN_SCOPE = "IN_SCOPE"
    OUT_OF_SCOPE_DELIVERY = "OUT_OF_SCOPE_DELIVERY"
    QUARANTINED = "QUARANTINED"
    UNKNOWN = "UNKNOWN"


class AmountQuality(StrEnum):
    VALID = "VALID"
    ORPHAN_ORDER = "ORPHAN_ORDER"
    INVALID_PRICE = "INVALID_PRICE"
    INVALID_FREIGHT = "INVALID_FREIGHT"
    INVALID_PAYMENT_VALUE = "INVALID_PAYMENT_VALUE"
    INVALID_INSTALLMENTS = "INVALID_INSTALLMENTS"


class ReviewEligibility(StrEnum):
    PENDING_DLP = "PENDING_DLP"
    SCORE_ONLY = "SCORE_ONLY"
    OUT_OF_SCOPE_ORDER = "OUT_OF_SCOPE_ORDER"
    ORPHAN_ORDER = "ORPHAN_ORDER"
    INVALID_RESPONSE_INTERVAL = "INVALID_RESPONSE_INTERVAL"


@dataclass(frozen=True, slots=True)
class GeolocationPoint:
    zip_prefix: str
    latitude: Decimal
    longitude: Decimal
    city: str
    state: str


@dataclass(frozen=True, slots=True)
class GeolocationSummary:
    zip_prefix: str
    latitude: Decimal | None
    longitude: Decimal | None
    source_count: int
    valid_coordinate_count: int
    invalid_coordinate_count: int
    city: str
    state: str
    quality: GeolocationQuality


@dataclass(frozen=True, slots=True)
class OrderClassification:
    scope: OrderScope
    reason: str
    delivery_interval_valid: bool
    delivery_lead_seconds: int | None
    delivery_delay_seconds: int | None
    is_on_time: bool | None


@dataclass(frozen=True, slots=True)
class ReviewClassification:
    text_present: bool
    text_length: int
    eligibility: ReviewEligibility
    ai_eligible: bool
    response_interval_valid: bool
    response_latency_seconds: int | None


def normalize_zip_prefix(value: str) -> str:
    normalized = value.strip()
    if not normalized.isascii() or not normalized.isdigit() or len(normalized) > 5:
        raise SilverContractError()
    return normalized.zfill(5)


def normalize_location(value: str) -> str:
    normalized = value.strip().upper()
    return normalized or "UNKNOWN"


def repeat_customer_key(customer_unique_id: str) -> str:
    normalized = customer_unique_id.strip()
    if not normalized or len(normalized) > 255:
        raise SilverContractError()
    payload = f"{REPEAT_CUSTOMER_KEY_VERSION}\0{normalized}".encode()
    return hashlib.sha256(payload).hexdigest()


def classify_item_amounts(*, price: Decimal, freight: Decimal, order_exists: bool) -> AmountQuality:
    if not price.is_finite() or not freight.is_finite():
        raise SilverContractError()
    if not order_exists:
        return AmountQuality.ORPHAN_ORDER
    if price <= 0:
        return AmountQuality.INVALID_PRICE
    if freight < 0:
        return AmountQuality.INVALID_FREIGHT
    return AmountQuality.VALID


def classify_payment_amount(
    *,
    value: Decimal,
    installments: int,
    order_exists: bool,
) -> AmountQuality:
    if not value.is_finite():
        raise SilverContractError()
    if not order_exists:
        return AmountQuality.ORPHAN_ORDER
    if value < 0:
        return AmountQuality.INVALID_PAYMENT_VALUE
    if installments < 0:
        return AmountQuality.INVALID_INSTALLMENTS
    return AmountQuality.VALID


def payment_reconciliation_delta(
    *,
    item_amounts: tuple[tuple[Decimal, Decimal], ...],
    payment_values: tuple[Decimal, ...],
) -> Decimal:
    item_total = sum((price + freight for price, freight in item_amounts), Decimal())
    payment_total = sum(payment_values, Decimal())
    if not item_total.is_finite() or not payment_total.is_finite():
        raise SilverContractError()
    return payment_total - item_total


def canonical_category(
    source_category: str | None, english_category: str | None
) -> tuple[str, str]:
    source = normalize_location(source_category or "UNKNOWN")
    english = normalize_location(english_category or "UNKNOWN")
    return source, english


def classify_review(
    *,
    score: int,
    title: str | None,
    comment: str | None,
    order_scope: OrderScope | None,
    created_at: datetime,
    answered_at: datetime,
) -> ReviewClassification:
    if score < 1 or score > 5 or created_at.tzinfo is not None or answered_at.tzinfo is not None:
        raise SilverContractError()
    combined_length = len((title or "").strip()) + len((comment or "").strip())
    text_present = combined_length > 0
    response_interval_valid = answered_at >= created_at
    latency = int((answered_at - created_at).total_seconds()) if response_interval_valid else None
    if not response_interval_valid:
        eligibility = ReviewEligibility.INVALID_RESPONSE_INTERVAL
    elif order_scope is None:
        eligibility = ReviewEligibility.ORPHAN_ORDER
    elif order_scope is not OrderScope.IN_SCOPE:
        eligibility = ReviewEligibility.OUT_OF_SCOPE_ORDER
    elif not text_present:
        eligibility = ReviewEligibility.SCORE_ONLY
    else:
        eligibility = ReviewEligibility.PENDING_DLP
    return ReviewClassification(
        text_present=text_present,
        text_length=combined_length,
        eligibility=eligibility,
        ai_eligible=False,
        response_interval_valid=response_interval_valid,
        response_latency_seconds=latency,
    )


def summarize_geolocation(points: tuple[GeolocationPoint, ...]) -> GeolocationSummary:
    if not points:
        raise SilverContractError()
    try:
        zip_prefix = normalize_zip_prefix(points[0].zip_prefix)
        if any(normalize_zip_prefix(point.zip_prefix) != zip_prefix for point in points):
            raise SilverContractError()
        cities = tuple(normalize_location(point.city) for point in points)
        states = tuple(normalize_location(point.state) for point in points)
    except (AttributeError, TypeError) as error:
        raise SilverContractError() from error

    valid = tuple(
        point
        for point in points
        if Decimal("-90") <= point.latitude <= Decimal("90")
        and Decimal("-180") <= point.longitude <= Decimal("180")
    )
    invalid_count = len(points) - len(valid)
    if not valid:
        latitude = longitude = None
        quality = GeolocationQuality.NO_VALID_COORDINATE
    else:
        latitude = (sum((item.latitude for item in valid), Decimal()) / len(valid)).quantize(
            _CENTROID_SCALE,
            rounding=ROUND_HALF_EVEN,
        )
        longitude = (sum((item.longitude for item in valid), Decimal()) / len(valid)).quantize(
            _CENTROID_SCALE,
            rounding=ROUND_HALF_EVEN,
        )
        if len(set(cities)) > 1 or len(set(states)) > 1:
            quality = GeolocationQuality.AMBIGUOUS_LOCATION
        elif invalid_count:
            quality = GeolocationQuality.PARTIAL_COORDINATE
        else:
            quality = GeolocationQuality.VALID
    return GeolocationSummary(
        zip_prefix=zip_prefix,
        latitude=latitude,
        longitude=longitude,
        source_count=len(points),
        valid_coordinate_count=len(valid),
        invalid_coordinate_count=invalid_count,
        city=min(cities),
        state=min(states),
        quality=quality,
    )


def classify_order(
    *,
    status: str,
    customer_exists: bool,
    item_count: int,
    purchased_at: datetime,
    delivered_at: datetime | None,
    estimated_delivery_at: datetime,
) -> OrderClassification:
    normalized_status = status.strip().lower()
    if (
        item_count < 0
        or purchased_at.tzinfo is not None
        or estimated_delivery_at.tzinfo is not None
    ):
        raise SilverContractError()
    if delivered_at is not None and delivered_at.tzinfo is not None:
        raise SilverContractError()

    if normalized_status not in _ALLOWED_ORDER_STATUSES:
        scope, reason = OrderScope.UNKNOWN, "UNRECOGNIZED_STATUS"
    elif normalized_status == "delivered" and not customer_exists:
        scope, reason = OrderScope.QUARANTINED, "MISSING_CUSTOMER"
    elif normalized_status == "delivered" and item_count == 0:
        scope, reason = OrderScope.QUARANTINED, "MISSING_ORDER_ITEM"
    elif normalized_status == "delivered":
        scope, reason = OrderScope.IN_SCOPE, "ELIGIBLE_DELIVERED"
    elif normalized_status in {"canceled", "unavailable"}:
        scope, reason = OrderScope.OUT_OF_SCOPE_DELIVERY, "TERMINAL_NON_DELIVERY"
    else:
        scope, reason = OrderScope.OUT_OF_SCOPE_DELIVERY, "NOT_DELIVERED"

    lead: int | None
    delay: int | None
    if delivered_at is not None and delivered_at >= purchased_at:
        interval_valid = True
        lead = int((delivered_at - purchased_at).total_seconds())
        delay = int((delivered_at - estimated_delivery_at).total_seconds())
    else:
        interval_valid = False
        lead = delay = None
    return OrderClassification(
        scope=scope,
        reason=reason,
        delivery_interval_valid=interval_valid,
        delivery_lead_seconds=lead,
        delivery_delay_seconds=delay,
        is_on_time=delay <= 0 if delay is not None else None,
    )
