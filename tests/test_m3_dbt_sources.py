from __future__ import annotations

import re
from pathlib import Path
from typing import Any, cast

import yaml  # type: ignore[import-untyped]

SOURCE_YAML = Path("dbt/models/sources/bronze_olist.yml")
BRONZE_DDL = Path("infra/snowflake/005_bronze.sql")
SELECTORS_YAML = Path("dbt/selectors.yml")


def _source_definition() -> dict[str, Any]:
    payload: dict[str, Any] = yaml.safe_load(SOURCE_YAML.read_text(encoding="utf-8"))
    return cast(dict[str, Any], payload["sources"][0])


def _ddl_columns() -> dict[str, dict[str, str]]:
    source = BRONZE_DDL.read_text(encoding="utf-8")
    tables: dict[str, dict[str, str]] = {}
    for table, body in re.findall(
        r"CREATE TABLE IF NOT EXISTS REVIEWLENS\.BRONZE\.(\w+) \((.*?)\)\nCOMMENT",
        source,
        re.DOTALL,
    ):
        columns: dict[str, str] = {}
        for line in body.splitlines():
            normalized = line.strip().rstrip(",")
            match = re.match(
                r"(\w+)\s+((?:VARCHAR(?:\(\d+\))?)|"
                r"(?:NUMBER\(\d+, \d+\))|(?:TIMESTAMP_\w+\(\d+\)))",
                normalized,
            )
            if match:
                columns[match.group(1).lower()] = _normalized_type(match.group(2))
        tables[table] = columns
    return tables


def _normalized_type(value: str) -> str:
    lower = value.lower()
    return "varchar" if lower.startswith("varchar") else lower


def test_all_nine_dbt_sources_match_bronze_columns_and_types() -> None:
    source = _source_definition()
    ddl = _ddl_columns()
    tables = {item["identifier"]: item for item in source["tables"]}

    assert set(tables) == set(ddl)
    for identifier, expected_columns in ddl.items():
        declared = {
            item["name"]: _normalized_type(item["data_type"])
            for item in tables[identifier]["columns"]
        }
        assert declared == expected_columns


def test_sources_have_bounded_freshness_and_canonical_physical_grain_tests() -> None:
    source = _source_definition()
    config = source["config"]

    assert config["loaded_at_field"] == "ingested_at"
    assert config["freshness"] == {
        "warn_after": {"count": 2, "period": "day"},
        "error_after": {"count": 7, "period": "day"},
    }
    for table in source["tables"]:
        tests = table["data_tests"]
        assert tests == [
            {
                "reviewlens_unique_combination": {
                    "arguments": {
                        "combination_of_columns": [
                            "ingestion_batch_id",
                            "dataset_run_id",
                            "record_hash",
                            "source_row_number",
                        ]
                    }
                }
            }
        ]
        columns = {item["name"]: item for item in table["columns"]}
        for name in (
            "source_release_id",
            "ingestion_batch_id",
            "dataset_run_id",
            "source_file_name",
            "source_row_number",
            "source_object_sha256",
            "record_hash",
            "ingested_at",
            "schema_version",
            "raw_payload",
        ):
            assert "not_null" in columns[name]["data_tests"]


def test_source_privacy_and_attribution_metadata_fail_closed() -> None:
    source = _source_definition()
    meta = source["config"]["meta"]
    tables = {item["name"]: item for item in source["tables"]}

    assert meta["license"] == "CC-BY-NC-SA-4.0"
    assert meta["data_access"] == "private"
    assert meta["raw_payload_allowed_in_public_artifacts"] is False
    review_meta = tables["order_reviews"]["config"]["meta"]
    assert review_meta == {
        "contains_restricted_ugc": True,
        "external_ai_requires_dlp_projection": True,
    }
    for table in tables.values():
        raw_payload = next(item for item in table["columns"] if item["name"] == "raw_payload")
        assert raw_payload["config"]["meta"] == {
            "data_class": "restricted",
            "downstream_allowed": False,
        }


def test_m3_selector_targets_only_the_bronze_source_contract() -> None:
    payload: dict[str, Any] = yaml.safe_load(SELECTORS_YAML.read_text(encoding="utf-8"))
    selectors = {item["name"]: item for item in payload["selectors"]}

    assert selectors["m3_bronze_contract"] == {
        "name": "m3_bronze_contract",
        "description": (
            "Test all nine immutable Olist Bronze sources before a Silver candidate build."
        ),
        "definition": {"method": "source", "value": "bronze_olist"},
    }
