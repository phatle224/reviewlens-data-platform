from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from reviewlens.synthetic.generator import REQUIRED_FILES

DBT_DIR = Path("dbt")
EXPECTED_SOURCES = {
    "customers": "BRZ_OLIST_CUSTOMERS_RAW",
    "geolocation": "BRZ_OLIST_GEOLOCATION_RAW",
    "order_items": "BRZ_OLIST_ORDER_ITEMS_RAW",
    "order_payments": "BRZ_OLIST_ORDER_PAYMENTS_RAW",
    "order_reviews": "BRZ_OLIST_ORDER_REVIEWS_RAW",
    "orders": "BRZ_OLIST_ORDERS_RAW",
    "products": "BRZ_OLIST_PRODUCTS_RAW",
    "sellers": "BRZ_OLIST_SELLERS_RAW",
    "category_translation": "BRZ_PRODUCT_CATEGORY_TRANSLATION_RAW",
}


def test_dbt_scaffold_is_single_local_snowflake_and_secret_safe() -> None:
    project = (DBT_DIR / "dbt_project.yml").read_text(encoding="utf-8")
    profile = (DBT_DIR / "profiles.yml").read_text(encoding="utf-8")
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    combined = f"{project}\n{profile}\n{pyproject}".lower()

    assert "type: snowflake" in profile
    assert "dbt-snowflake>=1.10,<2" in pyproject
    assert "reviewlens_transform_svc" in combined
    assert "transformer_role" in combined
    assert "reviewlens_wh" in combined
    assert "private_key_path" in profile
    assert "snowflake_transform_private_key_path" in combined
    assert "password:" not in combined
    assert "duckdb" not in combined
    assert "staging:" not in profile
    assert "production:" not in profile
    assert "prod:" not in profile
    assert "target: local" in profile
    assert "send_anonymous_usage_stats: false" in project
    assert "target-path: target" in project


def test_dbt_olist_sources_registry_and_privacy_contract_are_exact() -> None:
    sources = (DBT_DIR / "models/sources/bronze_olist.yml").read_text(encoding="utf-8")
    registry = (DBT_DIR / "models/foundation/source_contract_registry.sql").read_text(
        encoding="utf-8"
    )
    properties = (DBT_DIR / "models/foundation/source_contract_registry.yml").read_text(
        encoding="utf-8"
    )

    for source_name, identifier in EXPECTED_SOURCES.items():
        assert f"name: {source_name}" in sources
        assert f"identifier: {identifier}" in sources
        assert f"'{source_name}'" in registry
        assert f"'{identifier}'" in registry
    for file_name in REQUIRED_FILES:
        assert f"'{file_name}'" in registry
    assert "CC-BY-NC-SA-4.0" in sources
    assert "raw_payload_allowed_in_public_artifacts: false" in sources
    assert "contains_restricted_ugc: true" in sources
    assert "external_ai_requires_dlp_projection: true" in sources
    assert "contract:\n        enforced: true" in properties
    assert "data_class: synthetic_metadata" in properties


@pytest.mark.contract
def test_dbt_parse_manifest_is_snowflake_only_and_complete(tmp_path: Path) -> None:
    dbt = shutil.which("dbt")
    if dbt is None:
        executable_name = "dbt.exe" if os.name == "nt" else "dbt"
        candidate = Path(sys.executable).with_name(executable_name)
        dbt = str(candidate) if candidate.is_file() else None
    if dbt is None:
        pytest.skip("install the locked dbt dependency group to run the dbt contract")
    target_path = tmp_path / "target"
    log_path = tmp_path / "logs"
    environment = {
        **os.environ,
        "SNOWFLAKE_ACCOUNT": "synthetic-account",
        "SNOWFLAKE_TRANSFORM_PRIVATE_KEY_PATH": "synthetic-key.p8",
        "DBT_LOG_PATH": str(log_path),
        "DBT_SEND_ANONYMOUS_USAGE_STATS": "false",
    }
    subprocess.run(  # noqa: S603 - resolved local dbt executable
        [
            dbt,
            "--quiet",
            "--no-use-colors",
            "parse",
            "--project-dir",
            str(DBT_DIR),
            "--profiles-dir",
            str(DBT_DIR),
            "--target-path",
            str(target_path),
            "--no-partial-parse",
        ],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    manifest: dict[str, Any] = json.loads(
        (target_path / "manifest.json").read_text(encoding="utf-8")
    )

    assert manifest["metadata"]["adapter_type"] == "snowflake"
    sources = manifest["sources"]
    assert len(sources) == 9
    actual_sources = {node["name"]: node["identifier"] for node in sources.values()}
    assert actual_sources == EXPECTED_SOURCES
    models = [node for node in manifest["nodes"].values() if node["resource_type"] == "model"]
    assert {model["name"] for model in models} == {
        "source_contract_registry",
        "sil_customer",
        "sil_category_translation",
        "sil_geolocation_zip",
        "sil_order",
        "sil_order_item",
        "sil_order_payment",
        "sil_order_review",
        "sil_product",
        "sil_seller",
        "sil_dq_quarantine",
        "sil_unknown_member_registry",
        "dim_customer",
        "dim_date",
        "dim_geography",
        "dim_product",
        "dim_seller",
        "fact_order",
        "fact_order_item",
        "fact_payment",
        "fact_review_base",
        "bridge_review_item_attribution",
        "mart_order_delivery",
        "mart_product_review",
        "mart_seller_performance",
        "mart_customer_overview",
        "sem_order_delivery",
        "sem_product_review",
        "sem_seller_performance",
        "sem_customer_overview",
    }
    model = next(item for item in models if item["name"] == "source_contract_registry")
    assert model["name"] == "source_contract_registry"
    assert model["config"]["contract"]["enforced"] is True
    assert model["config"]["materialized"] == "view"
    assert model["schema"] == "SILVER"
    gold_models = [
        item
        for item in models
        if item["name"].startswith(("dim_", "fact_", "bridge_", "mart_", "sem_"))
    ]
    assert len(gold_models) == 18
    assert {item["schema"] for item in gold_models} == {"GOLD"}
    assert "duckdb" not in json.dumps(manifest).lower()
