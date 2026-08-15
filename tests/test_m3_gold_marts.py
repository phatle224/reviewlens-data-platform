from __future__ import annotations

import hashlib
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]

from reviewlens.warehouse.metrics import (
    METRIC_POLICY_VERSION,
    REPEAT_CUSTOMER_POLICY_VERSION,
    REVIEW_ALLOCATION_POLICY_VERSION,
    CustomerCohortInput,
    MetricContractError,
    OrderMetricInput,
    ReviewMetricInput,
    summarize_customer_cohort,
    summarize_order_metrics,
    summarize_review_metrics,
)

DBT_DIR = Path("dbt")
GOLD_DIR = DBT_DIR / "models" / "gold"
MART_MODELS = {
    "mart_order_delivery",
    "mart_product_review",
    "mart_seller_performance",
    "mart_customer_overview",
}


def _order(
    status: str,
    *,
    lead: int | None,
    delay: int | None,
    on_time: bool | None,
    gmv: str,
    freight: str,
    payment: str,
) -> OrderMetricInput:
    return OrderMetricInput(
        order_status=status,
        delivery_interval_valid=lead is not None,
        delivery_lead_seconds=lead,
        delivery_delay_seconds=delay,
        is_on_time_delivery=on_time,
        gross_merchandise_value=Decimal(gmv),
        freight_value=Decimal(freight),
        payment_value=Decimal(payment),
    )


def test_metric_dictionary_order_fixture_matches_expected_values() -> None:
    summary = summarize_order_metrics(
        (
            _order(
                "delivered",
                lead=100,
                delay=-10,
                on_time=True,
                gmv="100",
                freight="10",
                payment="110",
            ),
            _order(
                "delivered",
                lead=200,
                delay=20,
                on_time=False,
                gmv="50",
                freight="5",
                payment="55",
            ),
            _order(
                "canceled",
                lead=None,
                delay=None,
                on_time=None,
                gmv="20",
                freight="2",
                payment="0",
            ),
        )
    )

    assert summary.order_count == 3
    assert summary.delivered_order_count == 2
    assert summary.cancelled_order_count == 1
    assert summary.delivery_eligible_order_count == 2
    assert summary.on_time_order_count == 1
    assert summary.on_time_delivery_rate == Decimal("0.500000000000000000")
    assert summary.average_delivery_lead_seconds == Decimal("150.000000")
    assert summary.average_delivery_delay_seconds == Decimal("5.000000")
    assert summary.gross_merchandise_value == Decimal("170")
    assert summary.freight_value == Decimal("17")
    assert summary.payment_value == Decimal("165")
    assert summary.payment_reconciliation_delta == Decimal("-22")
    assert summary.metric_policy_version == METRIC_POLICY_VERSION


def test_metric_dictionary_zero_denominators_stay_null() -> None:
    summary = summarize_order_metrics(
        (
            _order(
                "canceled",
                lead=None,
                delay=None,
                on_time=None,
                gmv="0",
                freight="0",
                payment="0",
            ),
        )
    )

    assert summary.on_time_delivery_rate is None
    assert summary.average_delivery_lead_seconds is None
    assert summary.average_delivery_delay_seconds is None


def test_allocated_review_fixture_uses_fractional_sample_size() -> None:
    summary = summarize_review_metrics(
        (
            ReviewMetricInput(Decimal("0.5"), Decimal("2.5")),
            ReviewMetricInput(Decimal("0.5"), Decimal("2.5")),
            ReviewMetricInput(Decimal("1"), Decimal("1")),
        )
    )

    assert summary.allocated_review_count == Decimal("2.0")
    assert summary.allocated_review_score == Decimal("6.0")
    assert summary.average_review_score == Decimal("3.000000")
    assert summary.allocation_policy_version == REVIEW_ALLOCATION_POLICY_VERSION


def test_repeat_customer_fixture_is_distinct_and_excludes_unknown() -> None:
    repeat_key = hashlib.sha256(b"repeat").hexdigest()
    single_key = hashlib.sha256(b"single").hexdigest()
    summary = summarize_customer_cohort(
        (
            CustomerCohortInput(repeat_key, 2),
            CustomerCohortInput(repeat_key, 2),
            CustomerCohortInput(single_key, 1),
            CustomerCohortInput(None, 0),
        )
    )

    assert summary.customer_count == 2
    assert summary.repeat_customer_count == 1
    assert summary.repeat_customer_rate == Decimal("0.500000000000000000")
    assert summary.unknown_customer_order_count == 1
    assert summary.repeat_customer_definition_version == REPEAT_CUSTOMER_POLICY_VERSION


def test_repeat_customer_fixture_rejects_conflicting_lifetime_counts() -> None:
    repeat_key = hashlib.sha256(b"repeat").hexdigest()
    with pytest.raises(MetricContractError) as error:
        summarize_customer_cohort(
            (
                CustomerCohortInput(repeat_key, 1),
                CustomerCohortInput(repeat_key, 2),
            )
        )
    assert str(error.value) == MetricContractError.code


def test_metric_contract_rejects_incoherent_delivery_input() -> None:
    with pytest.raises(MetricContractError) as error:
        _order(
            "delivered",
            lead=1,
            delay=None,
            on_time=True,
            gmv="1",
            freight="0",
            payment="1",
        )
    assert str(error.value) == MetricContractError.code


@pytest.mark.parametrize(
    ("weight", "score", "policy"),
    [
        ("0", "0", REVIEW_ALLOCATION_POLICY_VERSION),
        ("0.5", "3", REVIEW_ALLOCATION_POLICY_VERSION),
        ("1", "5", "unversioned"),
    ],
)
def test_metric_contract_rejects_invalid_review_inputs(
    weight: str,
    score: str,
    policy: str,
) -> None:
    with pytest.raises(MetricContractError) as error:
        ReviewMetricInput(
            Decimal(weight),
            Decimal(score),
            allocation_policy_version=policy,
        )
    assert str(error.value) == MetricContractError.code


def test_gold_mart_sql_uses_preaggregated_grains_and_policy_labels() -> None:
    models = {name: (GOLD_DIR / f"{name}.sql").read_text(encoding="utf-8") for name in MART_MODELS}

    for sql in models.values():
        assert "candidate_namespace" in sql
        assert "tags=['m3_gold_marts']" in sql
        assert "olist-metric-dictionary-v1" in sql
        assert "raw_payload" not in sql.lower()
        assert "review_comment" not in sql.lower()
    assert "order_item_totals" in models["mart_order_delivery"]
    assert "payment_totals" in models["mart_order_delivery"]
    assert "allocation_policy_version" in models["mart_product_review"]
    assert "allocated_review_count" in models["mart_product_review"]
    assert "seller_orders" in models["mart_seller_performance"]
    assert "count(distinct order_key)" in models["mart_seller_performance"]
    assert "lifetime_customer_orders" in models["mart_customer_overview"]
    assert REPEAT_CUSTOMER_POLICY_VERSION in models["mart_customer_overview"]


def test_gold_mart_properties_declare_grains_metrics_and_privacy() -> None:
    properties: dict[str, Any] = yaml.safe_load(
        (GOLD_DIR / "marts.yml").read_text(encoding="utf-8")
    )
    models = {model["name"]: model for model in properties["models"]}

    assert set(models) == MART_MODELS
    for model in models.values():
        meta = model["config"]["meta"]
        columns = {column["name"] for column in model["columns"]}
        assert meta["work_item"] == "IMP-M3-015"
        assert meta["contains_review_text"] is False
        assert "metric_policy_version" in columns
        assert "source_release_id" in columns
    assert models["mart_product_review"]["config"]["meta"]["review_metrics"] == ("allocated_only")
    assert "repeat_customer_definition_version" in {
        column["name"] for column in models["mart_customer_overview"]["columns"]
    }


def test_gold_mart_reconciliation_gate_and_selector_cover_all_marts() -> None:
    gate = (DBT_DIR / "tests" / "m3_gold_mart_reconciliation.sql").read_text(encoding="utf-8")
    selector = (DBT_DIR / "selectors.yml").read_text(encoding="utf-8")
    adr = Path("docs/ADR/ADR-012-gold-mart-metric-semantics.md").read_text(encoding="utf-8")

    for failure in (
        "ORDER_DELIVERY_ORDER_COUNT",
        "PRODUCT_ITEM_COUNT",
        "PRODUCT_REVIEW_COUNT",
        "SELLER_ITEM_COUNT",
        "SELLER_REVIEW_COUNT",
        "CUSTOMER_ORDER_COUNT",
    ):
        assert f"'{failure}'" in gate
    assert "severity='error'" in gate
    assert "name: m3_gold_marts" in selector
    assert "aggregated to order grain before joining" in adr
    assert "zero denominator produces `NULL`" in adr
    assert "excluded from both customer" in adr
