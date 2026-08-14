from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]

from reviewlens.warehouse.silver import (
    AMOUNT_QUALITY_VERSION,
    PRODUCT_CONTRACT_VERSION,
    REVIEW_ELIGIBILITY_VERSION,
    AmountQuality,
    OrderScope,
    ReviewEligibility,
    SilverContractError,
    canonical_category,
    classify_item_amounts,
    classify_payment_amount,
    classify_review,
    payment_reconciliation_delta,
)

SILVER_DIR = Path("dbt/models/silver")
RELATIONAL_MODELS = {
    "sil_order_item",
    "sil_order_payment",
    "sil_category_translation",
    "sil_product",
    "sil_seller",
    "sil_order_review",
}


def test_item_payment_amount_quality_and_reconciliation_are_deterministic() -> None:
    assert (
        classify_item_amounts(price=Decimal("10.00"), freight=Decimal("2.50"), order_exists=True)
        is AmountQuality.VALID
    )
    assert (
        classify_item_amounts(price=Decimal("0"), freight=Decimal("1"), order_exists=True)
        is AmountQuality.INVALID_PRICE
    )
    assert (
        classify_payment_amount(value=Decimal("12.50"), installments=1, order_exists=True)
        is AmountQuality.VALID
    )
    assert (
        classify_payment_amount(value=Decimal("12.50"), installments=1, order_exists=False)
        is AmountQuality.ORPHAN_ORDER
    )
    assert payment_reconciliation_delta(
        item_amounts=((Decimal("10.00"), Decimal("2.50")),),
        payment_values=(Decimal("12.50"),),
    ) == Decimal("0.00")


def test_amount_and_review_contracts_fail_closed_on_invalid_values() -> None:
    assert (
        classify_item_amounts(price=Decimal("1"), freight=Decimal("-1"), order_exists=True)
        is AmountQuality.INVALID_FREIGHT
    )
    assert (
        classify_payment_amount(value=Decimal("-1"), installments=1, order_exists=True)
        is AmountQuality.INVALID_PAYMENT_VALUE
    )
    assert (
        classify_payment_amount(value=Decimal("1"), installments=-1, order_exists=True)
        is AmountQuality.INVALID_INSTALLMENTS
    )
    with pytest.raises(SilverContractError, match=SilverContractError.code):
        classify_item_amounts(price=Decimal("NaN"), freight=Decimal("0"), order_exists=True)
    with pytest.raises(SilverContractError, match=SilverContractError.code):
        classify_review(
            score=6,
            title=None,
            comment=None,
            order_scope=OrderScope.IN_SCOPE,
            created_at=datetime(2026, 1, 1),
            answered_at=datetime(2026, 1, 2),
        )


def test_category_contract_normalizes_and_uses_explicit_unknown_fallback() -> None:
    assert canonical_category("cama_mesa_banho", "bed_bath_table") == (
        "CAMA_MESA_BANHO",
        "BED_BATH_TABLE",
    )
    assert canonical_category(None, None) == ("UNKNOWN", "UNKNOWN")


@pytest.mark.parametrize(
    ("scope", "title", "comment", "answered_at", "expected"),
    [
        (
            OrderScope.IN_SCOPE,
            None,
            "synthetic delivery note",
            datetime(2026, 1, 2),
            ReviewEligibility.PENDING_DLP,
        ),
        (OrderScope.IN_SCOPE, None, "  ", datetime(2026, 1, 2), ReviewEligibility.SCORE_ONLY),
        (
            OrderScope.OUT_OF_SCOPE_DELIVERY,
            "synthetic",
            None,
            datetime(2026, 1, 2),
            ReviewEligibility.OUT_OF_SCOPE_ORDER,
        ),
        (None, "synthetic", None, datetime(2026, 1, 2), ReviewEligibility.ORPHAN_ORDER),
        (
            OrderScope.IN_SCOPE,
            "synthetic",
            None,
            datetime(2025, 12, 31),
            ReviewEligibility.INVALID_RESPONSE_INTERVAL,
        ),
    ],
)
def test_review_eligibility_never_bypasses_dlp(
    scope: OrderScope | None,
    title: str | None,
    comment: str | None,
    answered_at: datetime,
    expected: ReviewEligibility,
) -> None:
    result = classify_review(
        score=5,
        title=title,
        comment=comment,
        order_scope=scope,
        created_at=datetime(2026, 1, 1),
        answered_at=answered_at,
    )

    assert result.eligibility is expected
    assert result.ai_eligible is False
    assert result.response_latency_seconds is None or result.response_latency_seconds >= 0


def test_relational_sql_is_candidate_bound_deduplicated_and_lineage_safe() -> None:
    models = {
        name: (SILVER_DIR / f"{name}.sql").read_text(encoding="utf-8") for name in RELATIONAL_MODELS
    }

    for sql in models.values():
        assert "candidate_namespace" in sql
        assert "__REQUIRED_SOURCE_RELEASE_ID__" in sql
        assert "__REQUIRED_INGESTION_BATCH_ID__" in sql
        assert "reviewlens_revision_rank" in sql
        assert "raw_payload" not in sql.lower()
    assert "reviewlens_revision_rank('order_id, order_item_id')" in models["sil_order_item"]
    assert "reviewlens_revision_rank('order_id, payment_sequential')" in models["sil_order_payment"]
    assert "reviewlens_revision_rank('review_id, order_id')" in models["sil_order_review"]
    assert AMOUNT_QUALITY_VERSION in models["sil_order_item"]
    assert AMOUNT_QUALITY_VERSION in models["sil_order_payment"]
    assert PRODUCT_CONTRACT_VERSION in models["sil_product"]
    assert REVIEW_ELIGIBILITY_VERSION in models["sil_order_review"]


def test_product_corrects_source_spelling_and_review_is_not_multiplied_by_items() -> None:
    product = (SILVER_DIR / "sil_product.sql").read_text(encoding="utf-8").lower()
    review = (SILVER_DIR / "sil_order_review.sql").read_text(encoding="utf-8").lower()

    assert "as product_name_length" in product
    assert "as product_description_length" in product
    assert "as product_name_lenght" not in product
    assert "as product_description_lenght" not in product
    assert "order_items" not in review
    assert "cast(false as boolean) as ai_eligible" in review
    assert "pending_dlp" in review


def test_relational_yaml_has_exact_grains_and_restricted_review_metadata() -> None:
    payload: dict[str, Any] = yaml.safe_load(
        (SILVER_DIR / "silver_relational.yml").read_text(encoding="utf-8")
    )
    models = {item["name"]: item for item in payload["models"]}

    assert set(models) == RELATIONAL_MODELS
    assert {name: model["config"]["meta"]["grain"] for name, model in models.items()} == {
        "sil_order_item": "order_id + order_item_id",
        "sil_order_payment": "order_id + payment_sequential",
        "sil_category_translation": "product_category_name",
        "sil_product": "product_id",
        "sil_seller": "seller_id",
        "sil_order_review": "review_id + order_id",
    }
    review = models["sil_order_review"]
    assert review["config"]["meta"]["data_class"] == "restricted_ugc"
    assert review["config"]["meta"]["external_ai_requires_dlp_projection"] is True
    columns = {item["name"]: item for item in review["columns"]}
    for field in ("review_comment_title", "review_comment_message"):
        assert columns[field]["config"]["meta"] == {
            "data_class": "restricted",
            "external_transfer": "denied",
        }
