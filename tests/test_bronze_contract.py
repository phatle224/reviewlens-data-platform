from __future__ import annotations

import re
from pathlib import Path

from reviewlens.ingestion.bronze import BRONZE_TABLE_BY_DATASET
from reviewlens.ingestion.contracts import LogicalType, load_olist_contract

DDL_PATH = Path("infra/snowflake/005_bronze.sql")
CANONICAL_METADATA = {
    "SOURCE_RELEASE_ID": "VARCHAR NOT NULL",
    "INGESTION_BATCH_ID": "VARCHAR NOT NULL",
    "DATASET_RUN_ID": "VARCHAR NOT NULL",
    "SOURCE_FILE_NAME": "VARCHAR NOT NULL",
    "SOURCE_ROW_NUMBER": "NUMBER(38, 0) NOT NULL",
    "SOURCE_OBJECT_SHA256": "VARCHAR(64) NOT NULL",
    "RECORD_HASH": "VARCHAR(64) NOT NULL",
    "INGESTED_AT": "TIMESTAMP_TZ(6) NOT NULL",
    "SCHEMA_VERSION": "VARCHAR NOT NULL",
    "RAW_PAYLOAD": "VARCHAR NOT NULL",
}


def _table_bodies(source: str) -> dict[str, str]:
    return {
        name: body
        for name, body in re.findall(
            r"CREATE TABLE IF NOT EXISTS REVIEWLENS[.]BRONZE[.]([A-Z0-9_]+) [(](.*?)\n[)]\nCOMMENT",
            source,
            re.DOTALL,
        )
    }


def _expected_type(logical_type: LogicalType) -> str:
    if logical_type is LogicalType.STRING:
        return "VARCHAR"
    if logical_type is LogicalType.INTEGER:
        return "NUMBER(38, 0)"
    if logical_type is LogicalType.DECIMAL:
        return "NUMBER(38, 18)"
    return "TIMESTAMP_NTZ(6)"


def test_bronze_ddl_has_exact_nine_typed_contract_tables_and_lineage() -> None:
    source = DDL_PATH.read_text(encoding="utf-8")
    tables = _table_bodies(source)
    contract = load_olist_contract()

    assert set(tables) == set(BRONZE_TABLE_BY_DATASET.values())
    assert len(tables) == 9
    for dataset in contract.datasets:
        body = tables[BRONZE_TABLE_BY_DATASET[dataset.dataset_name]]
        for column in dataset.columns:
            nullability = "" if column.nullable else " NOT NULL"
            expected = f"{column.name.upper()} {_expected_type(column.logical_type)}{nullability}"
            assert expected in body
        for metadata_column, declaration in CANONICAL_METADATA.items():
            assert f"{metadata_column} {declaration}" in body
        assert (
            "UNIQUE\n    (INGESTION_BATCH_ID, DATASET_RUN_ID, RECORD_HASH, SOURCE_ROW_NUMBER)"
            in body
        )


def test_bronze_migration_is_idempotent_secret_free_and_insert_only() -> None:
    source = DDL_PATH.read_text(encoding="utf-8")
    upper = source.upper()

    assert upper.count("CREATE TABLE IF NOT EXISTS REVIEWLENS.BRONZE.") == 9
    assert "CREATE OR REPLACE TABLE" not in upper
    assert "AWS_KEY_ID" not in upper
    assert "AWS_SECRET_KEY" not in upper
    assert "CREATE FILE FORMAT IF NOT EXISTS REVIEWLENS.BRONZE.OLIST_PARQUET_FORMAT" in upper
    assert "TYPE = PARQUET" in upper
    assert "USE_LOGICAL_TYPE = TRUE" in upper
    assert "USE_VECTORIZED_SCANNER = TRUE" in upper
    assert "CREATE TABLE IF NOT EXISTS REVIEWLENS.AUDIT.BRONZE_LOAD_EVENT" in upper
    assert "RECORDED_AT TIMESTAMP_TZ(9) NOT NULL DEFAULT CURRENT_TIMESTAMP()" in upper
    assert "GRANT INSERT ON ALL TABLES IN SCHEMA REVIEWLENS.BRONZE TO ROLE INGEST_ROLE" in upper
    assert "GRANT SELECT ON ALL TABLES IN SCHEMA REVIEWLENS.BRONZE TO ROLE INGEST_ROLE" not in upper
    assert "REVOKE SELECT ON ALL TABLES IN SCHEMA REVIEWLENS.BRONZE FROM ROLE INGEST_ROLE" in upper
    assert (
        "GRANT SELECT ON ALL TABLES IN SCHEMA REVIEWLENS.BRONZE TO ROLE TRANSFORMER_ROLE" in upper
    )
    assert "GRANT USAGE ON SCHEMA REVIEWLENS.AUDIT TO ROLE INGEST_ROLE" in upper
    for forbidden in ("GRANT UPDATE", "GRANT DELETE", "GRANT TRUNCATE", "GRANT OWNERSHIP"):
        assert forbidden not in upper


def test_bronze_dbt_sources_and_ddl_table_names_are_synchronized() -> None:
    source = DDL_PATH.read_text(encoding="utf-8")
    dbt_source = Path("dbt/models/sources/bronze_olist.yml").read_text(encoding="utf-8")

    for table_name in BRONZE_TABLE_BY_DATASET.values():
        assert f"REVIEWLENS.BRONZE.{table_name}" in source
        assert f"identifier: {table_name}" in dbt_source
