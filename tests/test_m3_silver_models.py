from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]

from reviewlens.warehouse.silver import (
    GEOLOCATION_RULE_VERSION,
    ORDER_SCOPE_VERSION,
    ORDER_TIME_POLICY_VERSION,
    REPEAT_CUSTOMER_KEY_VERSION,
    GeolocationPoint,
    GeolocationQuality,
    OrderScope,
    SilverContractError,
    classify_order,
    normalize_location,
    normalize_zip_prefix,
    repeat_customer_key,
    summarize_geolocation,
)

SILVER_DIR = Path("dbt/models/silver")


def test_customer_contract_is_deterministic_minimized_and_normalized() -> None:
    first = repeat_customer_key("customer-repeat-1")
    second = repeat_customer_key("customer-repeat-1")

    assert first == second
    assert len(first) == 64
    assert "customer-repeat-1" not in first
    assert normalize_zip_prefix("123") == "00123"
    assert normalize_location("  são paulo ") == "SÃO PAULO"
    with pytest.raises(SilverContractError, match=SilverContractError.code):
        repeat_customer_key("")


def test_geolocation_centroid_has_one_deterministic_zip_row_without_multiplication() -> None:
    summary = summarize_geolocation(
        (
            GeolocationPoint("123", Decimal("-23.5"), Decimal("-46.6"), "Sao Paulo", "SP"),
            GeolocationPoint("00123", Decimal("-23.7"), Decimal("-46.8"), "Sao Paulo", "SP"),
        )
    )

    assert summary.zip_prefix == "00123"
    assert summary.latitude == Decimal("-23.600000000000000000")
    assert summary.longitude == Decimal("-46.700000000000000000")
    assert summary.source_count == summary.valid_coordinate_count == 2
    assert summary.invalid_coordinate_count == 0
    assert summary.quality is GeolocationQuality.VALID


def test_geolocation_flags_ambiguity_and_invalid_coordinate_cases() -> None:
    ambiguous = summarize_geolocation(
        (
            GeolocationPoint("01001", Decimal("-23"), Decimal("-46"), "A", "SP"),
            GeolocationPoint("01001", Decimal("-24"), Decimal("-47"), "B", "SP"),
        )
    )
    invalid = summarize_geolocation(
        (GeolocationPoint("01002", Decimal("91"), Decimal("0"), "A", "SP"),)
    )

    assert ambiguous.quality is GeolocationQuality.AMBIGUOUS_LOCATION
    assert invalid.quality is GeolocationQuality.NO_VALID_COORDINATE
    assert invalid.latitude is invalid.longitude is None


@pytest.mark.parametrize(
    ("status", "customer_exists", "item_count", "scope", "reason"),
    [
        ("delivered", True, 1, OrderScope.IN_SCOPE, "ELIGIBLE_DELIVERED"),
        ("delivered", False, 1, OrderScope.QUARANTINED, "MISSING_CUSTOMER"),
        ("delivered", True, 0, OrderScope.QUARANTINED, "MISSING_ORDER_ITEM"),
        ("canceled", True, 1, OrderScope.OUT_OF_SCOPE_DELIVERY, "TERMINAL_NON_DELIVERY"),
        ("shipped", True, 1, OrderScope.OUT_OF_SCOPE_DELIVERY, "NOT_DELIVERED"),
        ("unexpected", True, 1, OrderScope.UNKNOWN, "UNRECOGNIZED_STATUS"),
    ],
)
def test_order_scope_fixture_is_explicit(
    status: str,
    customer_exists: bool,
    item_count: int,
    scope: OrderScope,
    reason: str,
) -> None:
    result = classify_order(
        status=status,
        customer_exists=customer_exists,
        item_count=item_count,
        purchased_at=datetime(2026, 1, 1),
        delivered_at=datetime(2026, 1, 3) if status == "delivered" else None,
        estimated_delivery_at=datetime(2026, 1, 4),
    )

    assert result.scope is scope
    assert result.reason == reason


def test_order_delivery_intervals_are_guarded_and_on_time_is_inclusive() -> None:
    valid = classify_order(
        status="delivered",
        customer_exists=True,
        item_count=1,
        purchased_at=datetime(2026, 1, 1),
        delivered_at=datetime(2026, 1, 4),
        estimated_delivery_at=datetime(2026, 1, 4),
    )
    invalid = classify_order(
        status="delivered",
        customer_exists=True,
        item_count=1,
        purchased_at=datetime(2026, 1, 2),
        delivered_at=datetime(2026, 1, 1),
        estimated_delivery_at=datetime(2026, 1, 4),
    )

    assert valid.delivery_lead_seconds == 3 * 86400
    assert valid.delivery_delay_seconds == 0
    assert valid.is_on_time is True
    assert invalid.delivery_interval_valid is False
    assert invalid.delivery_lead_seconds is invalid.delivery_delay_seconds is None
    assert invalid.is_on_time is None


def test_silver_sql_is_candidate_bound_lineage_safe_and_versioned() -> None:
    models = {path.stem: path.read_text(encoding="utf-8") for path in SILVER_DIR.glob("*.sql")}

    assert set(models) == {"sil_customer", "sil_geolocation_zip", "sil_order"}
    for sql in models.values():
        assert "candidate_namespace" in sql
        assert "source_release_id" in sql
        assert "ingestion_batch_id" in sql
        assert "__REQUIRED_SOURCE_RELEASE_ID__" in sql
        assert "__REQUIRED_INGESTION_BATCH_ID__" in sql
        assert "raw_payload" not in sql.lower()
    assert "as customer_unique_id" not in models["sil_customer"].lower()
    assert REPEAT_CUSTOMER_KEY_VERSION in models["sil_customer"]
    assert GEOLOCATION_RULE_VERSION in models["sil_geolocation_zip"]
    assert ORDER_SCOPE_VERSION in models["sil_order"]
    assert ORDER_TIME_POLICY_VERSION in models["sil_order"]


def test_silver_yaml_has_exact_grains_contracts_and_runtime_gate() -> None:
    payload: dict[str, Any] = yaml.safe_load(
        (SILVER_DIR / "silver.yml").read_text(encoding="utf-8")
    )
    models = {item["name"]: item for item in payload["models"]}
    runtime_test = Path("dbt/tests/m3_runtime_contract.sql").read_text(encoding="utf-8")

    assert {name: item["config"]["meta"]["grain"] for name, item in models.items()} == {
        "sil_customer": "customer_id",
        "sil_geolocation_zip": "geolocation_zip_prefix",
        "sil_order": "order_id",
    }
    assert all(item["config"]["contract"]["enforced"] is True for item in models.values())
    assert models["sil_customer"]["config"]["meta"]["contains_raw_customer_unique_id"] is False
    assert "^C_[A-F0-9]{64}$" in runtime_test
    assert re.search(r"\^olist_\[0-9a-f\]\{64\}\$", runtime_test)
    assert re.search(r"\^batch_\[0-9a-f\]\{64\}\$", runtime_test)
