from __future__ import annotations

import hashlib
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]

from reviewlens.warehouse.gold import (
    GOLD_HISTORY_VERSION,
    GOLD_KEY_VERSION,
    REVIEW_ATTRIBUTION_POLICY_VERSION,
    DimensionHistoryRow,
    GoldContractError,
    ReviewAttributionMethod,
    allocate_review_to_items,
    gold_dimension_key,
    reconcile_fact_partition,
    resolve_dimension_as_of,
)
from reviewlens.warehouse.revisions import DimensionEntity, unknown_member

DBT_DIR = Path("dbt")
GOLD_DIR = DBT_DIR / "models" / "gold"
DIMENSION_MODELS = {
    "dim_date",
    "dim_customer",
    "dim_product",
    "dim_seller",
    "dim_geography",
}
FACT_MODELS = {"fact_order", "fact_order_item", "fact_payment", "fact_review_base"}
BRIDGE_MODELS = {"bridge_review_item_attribution"}


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def test_gold_dimension_keys_are_stable_and_entity_scoped() -> None:
    customer = gold_dimension_key(DimensionEntity.CUSTOMER, "customer-1")
    product = gold_dimension_key(DimensionEntity.PRODUCT, "customer-1")

    assert customer == gold_dimension_key(DimensionEntity.CUSTOMER, " customer-1 ")
    assert customer != product
    assert customer != gold_dimension_key(
        DimensionEntity.CUSTOMER,
        "customer-1",
        version_hash=_hash("version-2"),
    )
    assert len(customer) == 64
    assert (
        gold_dimension_key(DimensionEntity.CUSTOMER, None)
        == unknown_member(DimensionEntity.CUSTOMER).member_key
    )
    assert (
        gold_dimension_key(DimensionEntity.CUSTOMER, " ")
        == unknown_member(DimensionEntity.CUSTOMER).member_key
    )
    assert GOLD_KEY_VERSION == "reviewlens-gold-key-v1"
    with pytest.raises(GoldContractError):
        gold_dimension_key(DimensionEntity.CUSTOMER, "customer-1", version_hash="invalid")


def test_dimension_history_resolves_half_open_as_of_boundary_deterministically() -> None:
    natural_key_hash = _hash("customer-1")
    first = DimensionHistoryRow(
        natural_key_hash,
        _hash("member-v1"),
        datetime(2020, 1, 1),
        datetime(2021, 1, 1),
        False,
    )
    second = DimensionHistoryRow(
        natural_key_hash,
        _hash("member-v2"),
        datetime(2021, 1, 1),
        None,
        True,
    )

    assert (
        resolve_dimension_as_of(
            entity_type=DimensionEntity.CUSTOMER,
            natural_key_hash=natural_key_hash,
            event_at=datetime(2020, 12, 31, 23, 59, 59),
            history=(second, first),
        )
        == first.member_key
    )
    assert (
        resolve_dimension_as_of(
            entity_type=DimensionEntity.CUSTOMER,
            natural_key_hash=natural_key_hash,
            event_at=datetime(2021, 1, 1),
            history=(first, second),
        )
        == second.member_key
    )
    assert (
        resolve_dimension_as_of(
            entity_type=DimensionEntity.CUSTOMER,
            natural_key_hash=natural_key_hash,
            event_at=datetime(2019, 12, 31),
            history=(first, second),
        )
        == unknown_member(DimensionEntity.CUSTOMER).member_key
    )
    assert GOLD_HISTORY_VERSION == "reviewlens-gold-history-v1"


def test_dimension_history_rejects_overlap_and_mixed_keys_without_echo() -> None:
    seeded = "sensitive-natural-key"
    natural_key_hash = _hash(seeded)
    rows = (
        DimensionHistoryRow(
            natural_key_hash,
            _hash("member-v1"),
            datetime(2020, 1, 1),
            datetime(2022, 1, 1),
            False,
        ),
        DimensionHistoryRow(
            natural_key_hash,
            _hash("member-v2"),
            datetime(2021, 1, 1),
            None,
            True,
        ),
    )

    with pytest.raises(GoldContractError) as overlap:
        resolve_dimension_as_of(
            entity_type=DimensionEntity.CUSTOMER,
            natural_key_hash=natural_key_hash,
            event_at=datetime(2021, 6, 1),
            history=rows,
        )
    with pytest.raises(GoldContractError):
        DimensionHistoryRow(natural_key_hash, _hash("bad"), datetime.now(), None, False)

    assert str(overlap.value) == GoldContractError.code
    assert seeded not in str(overlap.value)


def test_fact_partition_requires_exact_unique_explained_reconciliation() -> None:
    source = tuple(_hash(value) for value in ("one", "two", "three"))

    result = reconcile_fact_partition(
        source_grain_hashes=source,
        fact_grain_hashes=reversed(source[:2]),
        excluded_grain_hashes=(source[2],),
    )

    assert result.source_count == 3
    assert result.fact_count == 2
    assert result.excluded_count == 1
    with pytest.raises(GoldContractError):
        reconcile_fact_partition(
            source_grain_hashes=source,
            fact_grain_hashes=(source[0],),
            excluded_grain_hashes=(source[2],),
        )
    with pytest.raises(GoldContractError):
        reconcile_fact_partition(
            source_grain_hashes=source,
            fact_grain_hashes=(source[0], source[0]),
            excluded_grain_hashes=source[1:],
        )


def test_review_attribution_preserves_exact_contribution_and_input_order() -> None:
    review_key = _hash("review")
    items = tuple(_hash(value) for value in ("item-c", "item-a", "item-b"))

    rows = allocate_review_to_items(
        review_key=review_key,
        review_score=5,
        eligible_order_item_keys=items,
    )
    reordered = allocate_review_to_items(
        review_key=review_key,
        review_score=5,
        eligible_order_item_keys=reversed(items),
    )
    two_items = allocate_review_to_items(
        review_key=review_key,
        review_score=2,
        eligible_order_item_keys=items[:2],
    )

    assert rows == reordered
    assert tuple(row.order_item_key for row in rows) == tuple(sorted(items))
    assert sum((row.allocation_weight for row in rows), start=Decimal(0)) == Decimal(1)
    assert sum((row.allocated_review_score for row in rows), start=Decimal(0)) == Decimal(5)
    assert rows[-1].allocation_weight == Decimal("0.333333333333333334")
    assert [row.allocation_weight for row in two_items] == [
        Decimal("0.500000000000000000"),
        Decimal("0.500000000000000000"),
    ]
    assert sum((row.allocated_review_score for row in two_items), start=Decimal(0)) == Decimal(2)
    assert all(row.item_count_for_review == 3 for row in rows)
    assert all(row.allocation_method is ReviewAttributionMethod.EQUAL_ITEM_WEIGHT for row in rows)
    assert all(row.allocation_policy_version == REVIEW_ATTRIBUTION_POLICY_VERSION for row in rows)


def test_review_attribution_handles_single_and_unknown_item_without_loss() -> None:
    review_key = _hash("review")
    item_key = _hash("item")

    single = allocate_review_to_items(
        review_key=review_key,
        review_score=1,
        eligible_order_item_keys=(item_key,),
    )
    fallback = allocate_review_to_items(
        review_key=review_key,
        review_score=4,
        eligible_order_item_keys=(),
    )

    assert single[0].allocation_weight == Decimal("1.000000000000000000")
    assert single[0].order_item_key == item_key
    assert fallback[0].allocation_method is ReviewAttributionMethod.UNKNOWN_ITEM_FALLBACK
    assert fallback[0].order_item_key is None
    assert fallback[0].item_count_for_review == 0
    assert fallback[0].allocated_review_score == Decimal("4.000000000000000000")


@pytest.mark.parametrize(
    ("review_key", "review_score", "item_keys"),
    [
        ("invalid", 5, ()),
        (_hash("review"), 0, ()),
        (_hash("review"), True, ()),
        (_hash("review"), 5, ("invalid",)),
        (_hash("review"), 5, (_hash("duplicate"), _hash("duplicate"))),
    ],
)
def test_review_attribution_rejects_invalid_or_duplicate_grains_without_echo(
    review_key: str,
    review_score: int,
    item_keys: tuple[str, ...],
) -> None:
    with pytest.raises(GoldContractError) as error:
        allocate_review_to_items(
            review_key=review_key,
            review_score=review_score,
            eligible_order_item_keys=item_keys,
        )

    assert str(error.value) == GoldContractError.code
    assert "invalid" not in str(error.value)


def test_gold_sql_is_candidate_bound_and_uses_declared_conformed_inputs() -> None:
    models = {
        name: (GOLD_DIR / f"{name}.sql").read_text(encoding="utf-8")
        for name in DIMENSION_MODELS | FACT_MODELS | BRIDGE_MODELS
    }

    for sql in models.values():
        assert "candidate_namespace" in sql
        assert "reviewlens-" in sql
        assert "raw_payload" not in sql.lower()
    assert "ref('sil_unknown_member_registry')" in models["dim_customer"]
    assert "ref('dim_geography')" in models["dim_customer"]
    assert "ref('dim_geography')" in models["dim_seller"]
    assert "ref('fact_order')" in models["fact_order_item"]
    assert "customer.effective_from" in models["fact_order"]
    assert "product.effective_from" in models["fact_order_item"]
    assert "seller.effective_from" in models["fact_order_item"]
    assert "amount_quality_status = 'VALID'" in models["fact_order_item"]
    assert "amount_quality_status = 'VALID'" in models["fact_payment"]
    attribution = models["bridge_review_item_attribution"]
    assert "ref('fact_review_base')" in attribution
    assert "ref('fact_order_item')" in attribution
    assert "olist-review-item-equal-weight-v1" in attribution
    assert "trunc(" in attribution
    assert "unknown_keys" in attribution


def test_gold_properties_declare_exact_grains_history_and_relationships() -> None:
    dimensions: dict[str, Any] = yaml.safe_load(
        (GOLD_DIR / "dimensions.yml").read_text(encoding="utf-8")
    )
    facts: dict[str, Any] = yaml.safe_load((GOLD_DIR / "facts.yml").read_text(encoding="utf-8"))
    attribution: dict[str, Any] = yaml.safe_load(
        (GOLD_DIR / "attribution.yml").read_text(encoding="utf-8")
    )
    dimension_models = {model["name"]: model for model in dimensions["models"]}
    fact_models = {model["name"]: model for model in facts["models"]}

    assert set(dimension_models) == DIMENSION_MODELS
    assert set(fact_models) == FACT_MODELS
    assert dimension_models["dim_date"]["config"]["meta"]["grain"] == "full_date"
    for name in DIMENSION_MODELS - {"dim_date"}:
        columns = {column["name"] for column in dimension_models[name]["columns"]}
        assert {"effective_from", "effective_to", "is_current"} <= columns
        assert "history_policy_version" in columns
        assert "reviewlens_scd_no_overlap" in str(dimension_models[name]["data_tests"])
    assert fact_models["fact_order"]["config"]["meta"]["grain"] == "order_id"
    assert fact_models["fact_order_item"]["config"]["meta"]["grain"] == ("order_id + order_item_id")
    assert fact_models["fact_payment"]["config"]["meta"]["grain"] == (
        "order_id + payment_sequential"
    )
    attribution_model = attribution["models"][0]
    assert attribution_model["name"] == "bridge_review_item_attribution"
    assert attribution_model["config"]["meta"]["grain"] == ("review_key + attribution_ordinal")
    assert attribution_model["config"]["meta"]["naturally_additive"] is False
    assert attribution_model["config"]["meta"]["contains_review_text"] is False


def test_review_base_fact_is_minimized_and_independent_of_ai_coverage() -> None:
    sql = (GOLD_DIR / "fact_review_base.sql").read_text(encoding="utf-8").lower()
    properties: dict[str, Any] = yaml.safe_load(
        (GOLD_DIR / "facts.yml").read_text(encoding="utf-8")
    )
    review = next(model for model in properties["models"] if model["name"] == "fact_review_base")
    column_names = {column["name"] for column in review["columns"]}

    assert "review_comment_title" not in sql
    assert "review_comment_message" not in sql
    assert "sil_order_item" not in sql
    assert "fact_review_enrichment" not in sql
    assert "review_comment_title" not in column_names
    assert "review_comment_message" not in column_names
    assert review["config"]["meta"]["contains_review_text"] is False
    assert review["config"]["meta"]["independent_of_ai_coverage"] is True


def test_gold_reconciliation_gate_covers_counts_and_additive_amounts() -> None:
    gate = (DBT_DIR / "tests" / "m3_gold_base_reconciliation.sql").read_text(encoding="utf-8")
    selector = (DBT_DIR / "selectors.yml").read_text(encoding="utf-8")
    schema_macro = (DBT_DIR / "macros" / "generate_schema_name.sql").read_text(encoding="utf-8")

    for fact in ("FACT_ORDER", "FACT_ORDER_ITEM", "FACT_PAYMENT", "FACT_REVIEW_BASE"):
        assert f"'{fact}_COUNT'" in gate
    assert "FACT_ORDER_ITEM_AMOUNT" in gate
    assert "FACT_PAYMENT_AMOUNT" in gate
    assert "severity='error'" in gate
    assert "name: m3_gold_base" in selector
    assert "custom_schema_name | trim" in schema_macro


def test_review_attribution_gate_prevents_silent_double_count() -> None:
    gate = (DBT_DIR / "tests" / "m3_review_attribution_reconciliation.sql").read_text(
        encoding="utf-8"
    )
    selector = (DBT_DIR / "selectors.yml").read_text(encoding="utf-8")
    adr = Path("docs/ADR/ADR-011-review-item-attribution-policy.md").read_text(encoding="utf-8")

    assert "sum(allocation_weight)" in gate
    assert "sum(allocated_review_count)" in gate
    assert "sum(allocated_review_score)" in gate
    assert "greatest(item_count_for_review, 1)" in gate
    assert "ref('fact_review_base')" in gate
    assert "severity='error'" in gate
    assert "name: m3_review_attribution" in selector
    assert "Full-credit duplication is rejected" in adr
    assert "not naturally\nadditive" in adr
