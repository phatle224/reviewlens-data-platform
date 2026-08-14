from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from reviewlens.providers.snowflake import SnowflakeClient, split_sql_statements

MIGRATION = Path("infra/snowflake/006_processing_candidates.sql")
EXPECTED_TABLES = {
    "PROCESSING_RUN",
    "PROCESSING_INPUT_REF",
    "CANDIDATE_PHYSICAL_REF_EVENT",
}


class RecordingCursor:
    def __init__(self, statements: list[str]) -> None:
        self._statements = statements
        self.sfqid = "synthetic-query-id"

    def execute(self, command: str) -> RecordingCursor:
        self._statements.append(command)
        return self

    def fetchall(self) -> list[tuple[Any, ...]]:
        return []

    def close(self) -> None:
        return None


class RecordingConnection:
    def __init__(self) -> None:
        self.statements: list[str] = []

    def cursor(self) -> RecordingCursor:
        return RecordingCursor(self.statements)

    def close(self) -> None:
        return None


def _source() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def _tables() -> dict[str, str]:
    return {
        name: body.upper()
        for name, body in re.findall(
            r"CREATE TABLE IF NOT EXISTS REVIEWLENS\.AUDIT\.(\w+)\s*\((.*?)\)\s*COMMENT\s*=",
            _source(),
            re.DOTALL,
        )
    }


def test_processing_migration_models_one_to_many_lineage_and_physical_refs() -> None:
    tables = _tables()

    assert set(tables) == EXPECTED_TABLES
    assert "INPUT_COUNT NUMBER(38, 0) NOT NULL" in tables["PROCESSING_RUN"]
    for required in (
        "PROCESS_RUN_ID VARCHAR(64) NOT NULL",
        "INPUT_ORDINAL NUMBER(38, 0) NOT NULL",
        "INPUT_VERSION_ID VARCHAR(128) NOT NULL",
        "PHYSICAL_DATABASE VARCHAR(255) NOT NULL",
        "PHYSICAL_SCHEMA VARCHAR(255) NOT NULL",
        "PHYSICAL_OBJECT VARCHAR(255) NOT NULL",
    ):
        assert required in tables["PROCESSING_INPUT_REF"]
    assert "UNIQUE (PROCESS_RUN_ID, INPUT_ORDINAL)" in tables["PROCESSING_INPUT_REF"]
    for required in (
        "CANDIDATE_ID VARCHAR(64) NOT NULL",
        "STRATEGY_VERSION VARCHAR(128) NOT NULL",
        "STATE VARCHAR(32) NOT NULL",
        "LEASE_OWNER VARCHAR(64)",
        "LEASE_EXPIRES_AT TIMESTAMP_TZ(9)",
    ):
        assert required in tables["CANDIDATE_PHYSICAL_REF_EVENT"]


def test_processing_migration_is_additive_secret_free_and_append_only() -> None:
    upper = _source().upper()
    statements = tuple(" ".join(item.upper().split()) for item in split_sql_statements(_source()))

    assert upper.count("CREATE TABLE IF NOT EXISTS") == 3
    assert "CREATE OR REPLACE" not in upper
    for forbidden in (
        "UPDATE ",
        "DELETE ",
        "MERGE INTO",
        "DROP TABLE",
        "RAW_PAYLOAD",
        "REVIEW_TEXT",
        "PASSWORD",
        "PRIVATE_KEY",
        "API_KEY",
        "USE WAREHOUSE",
    ):
        assert forbidden not in upper
    grants = tuple(item for item in statements if item.startswith("GRANT "))
    assert len(grants) == 8
    assert all("SELECT, INSERT ON TABLE" in item or "USAGE ON SCHEMA" in item for item in grants)
    assert not any("ALL TABLES" in item or "FUTURE TABLES" in item for item in grants)


def test_processing_migration_has_stable_compatibility_marker() -> None:
    upper = _source().upper()

    assert "CREATE VIEW IF NOT EXISTS REVIEWLENS.AUDIT.M3_SCHEMA_COMPATIBILITY" in upper
    assert "'IMP-M3-001-PROCESSING-V1'::VARCHAR(128) AS MIGRATION_ID" in upper
    assert "3::NUMBER(10, 0) AS TABLE_COUNT" in upper


def test_processing_migration_replays_same_ddl_plan_through_adapter() -> None:
    connection = RecordingConnection()
    client = SnowflakeClient(connection)
    expected = split_sql_statements(_source())

    client.apply_sql_file(MIGRATION, operation="M3 processing migration")
    client.apply_sql_file(MIGRATION, operation="M3 processing migration replay")

    assert tuple(connection.statements) == expected + expected
