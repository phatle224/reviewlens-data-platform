from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]

from reviewlens.warehouse.semantic import (
    SEMANTIC_CATALOG_VERSION,
    SEMANTIC_PHYSICAL_NAME_POLICY,
    SemanticCatalogError,
    load_semantic_catalog,
    parse_semantic_catalog,
    resolve_semantic_view,
)

CATALOG_PATH = Path("config/semantic_catalog.v1.json")
GOLD_DIR = Path("dbt/models/gold")
SEMANTIC_MODELS = {
    "sem_order_delivery": "ORDER_DELIVERY",
    "sem_product_review": "PRODUCT_REVIEW",
    "sem_seller_performance": "SELLER_PERFORMANCE",
    "sem_customer_overview": "CUSTOMER_OVERVIEW",
}
EXPECTED_MART_REFS = {
    "sem_order_delivery": "mart_order_delivery",
    "sem_product_review": "mart_product_review",
    "sem_seller_performance": "mart_seller_performance",
    "sem_customer_overview": "mart_customer_overview",
}


def _payload() -> dict[str, Any]:
    loaded: Any = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def test_semantic_catalog_loads_four_release_bound_allowlists() -> None:
    catalog = load_semantic_catalog(CATALOG_PATH)

    assert catalog.schema_version == 1
    assert catalog.contract_version == SEMANTIC_CATALOG_VERSION
    assert catalog.physical_name_policy == SEMANTIC_PHYSICAL_NAME_POLICY
    assert {view.logical_name: view.dbt_model for view in catalog.views} == {
        logical_name: model for model, logical_name in SEMANTIC_MODELS.items()
    }
    for view in catalog.views:
        assert view.audiences == frozenset({"DASHBOARD", "TEXT_TO_SQL"})
        assert view.grant_roles == frozenset({"ANALYST_ROLE", "TEXT_TO_SQL_ROLE"})
        assert {
            "data_release_id",
            "metric_policy_version",
            "semantic_contract_version",
        } <= set(view.approved_columns)


def test_semantic_resolver_accepts_only_exact_logical_names() -> None:
    catalog = load_semantic_catalog(CATALOG_PATH)

    assert resolve_semantic_view(catalog, "ORDER_DELIVERY").dbt_model == ("sem_order_delivery")
    for unsafe in (
        "order_delivery",
        "sem_order_delivery",
        "C_RELEASE__SEM_ORDER_DELIVERY",
        "REVIEWLENS.GOLD.ORDER_DELIVERY",
        "FACT_ORDER",
        "BRZ_OLIST_ORDERS_RAW",
    ):
        with pytest.raises(SemanticCatalogError) as error:
            resolve_semantic_view(catalog, unsafe)
        assert str(error.value) == SemanticCatalogError.code
        assert unsafe not in str(error.value)


@pytest.mark.parametrize(
    "mutation",
    [
        "unsafe_column",
        "unknown_field",
        "duplicate_view",
        "unsafe_role",
        "physical_policy",
    ],
)
def test_semantic_catalog_rejects_unsafe_or_ambiguous_contracts(mutation: str) -> None:
    payload = copy.deepcopy(_payload())
    views: list[dict[str, Any]] = payload["views"]
    if mutation == "unsafe_column":
        views[0]["approved_columns"].append("review_comment_message")
    elif mutation == "unknown_field":
        views[0]["unexpected"] = True
    elif mutation == "duplicate_view":
        views.append(copy.deepcopy(views[0]))
    elif mutation == "unsafe_role":
        views[0]["grant_roles"].append("ACCOUNTADMIN")
    else:
        payload["physical_name_policy"] = "accept_user_identifier"

    with pytest.raises(SemanticCatalogError) as error:
        parse_semantic_catalog(payload)
    assert str(error.value) == SemanticCatalogError.code


def test_semantic_dbt_contract_columns_exactly_match_catalog() -> None:
    catalog = load_semantic_catalog(CATALOG_PATH)
    properties: dict[str, Any] = yaml.safe_load(
        (GOLD_DIR / "semantic.yml").read_text(encoding="utf-8")
    )
    dbt_models = {model["name"]: model for model in properties["models"]}

    assert set(dbt_models) == set(SEMANTIC_MODELS)
    for view in catalog.views:
        dbt_model = dbt_models[view.dbt_model]
        columns = tuple(column["name"] for column in dbt_model["columns"])
        meta = dbt_model["config"]["meta"]
        assert columns == view.approved_columns
        assert meta["logical_name"] == view.logical_name
        assert meta["audiences"] == ["DASHBOARD", "TEXT_TO_SQL"]
        assert meta["contains_review_text"] is False
        assert meta["exposes_physical_identifier"] is False
        assert dbt_model["config"]["materialized"] == "view"


def test_semantic_sql_reads_one_approved_mart_and_labels_context() -> None:
    forbidden_refs = re.compile(r"ref\('(fact_|bridge_|sil_|brz_|dim_)")
    forbidden_output_tokens = {
        "review_comment_message",
        "review_comment_title",
        "source_record_hash",
        "customer_id",
        "order_id",
        "review_id",
        "seller_id",
        "raw_payload",
    }

    for model, expected_mart in EXPECTED_MART_REFS.items():
        sql = (GOLD_DIR / f"{model}.sql").read_text(encoding="utf-8").lower()
        assert f"ref('{expected_mart}')" in sql
        assert len(re.findall(r"ref\('", sql)) == 1
        assert forbidden_refs.search(sql) is None
        assert "materialized='view'" in sql
        assert "tags=['m3_semantic']" in sql
        assert "source_release_id as varchar) as data_release_id" in sql
        assert SEMANTIC_CATALOG_VERSION in sql
        assert "post_hook" not in sql
        assert not forbidden_output_tokens & set(re.findall(r"[a-z_]+", sql))


def test_semantic_policy_labels_non_additivity_and_partial_ai() -> None:
    catalog = load_semantic_catalog(CATALOG_PATH)
    product = resolve_semantic_view(catalog, "PRODUCT_REVIEW")
    seller = resolve_semantic_view(catalog, "SELLER_PERFORMANCE")
    combined_sql = "\n".join(
        (GOLD_DIR / f"{name}.sql").read_text(encoding="utf-8")
        for name in (product.dbt_model, seller.dbt_model)
    )

    assert "order_count" in product.non_additive_measures
    assert "order_count" in seller.non_additive_measures
    assert "allocated_review_sample_size" in product.approved_columns
    assert "NON_ADDITIVE_ACROSS_PRODUCTS" in combined_sql
    assert "NON_ADDITIVE_ACROSS_SELLERS" in combined_sql
    assert combined_sql.count("NOT_AVAILABLE_UNTIL_M4") == 2


def test_semantic_selector_and_adr_preserve_later_atomic_activation() -> None:
    selector = Path("dbt/selectors.yml").read_text(encoding="utf-8")
    adr = Path("docs/ADR/ADR-013-semantic-serving-boundary.md").read_text(encoding="utf-8")

    assert "name: m3_semantic" in selector
    assert "resolve_active_release_server_side" in adr
    assert "not automatically granted or published" in adr
    assert "active pointer implementation remains" in adr
