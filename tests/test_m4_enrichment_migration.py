from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from reviewlens.providers.snowflake import SnowflakeClient, split_sql_statements

MIGRATION_PATH = Path("infra/snowflake/009_ai_enrichment_ledgers.sql")
EXPECTED_TABLES = {
    "AI_ENRICHMENT_RUN",
    "AI_ENRICHMENT_INVOCATION",
    "AI_ENRICHMENT_RESULT_MAP",
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
    return MIGRATION_PATH.read_text(encoding="utf-8")


def _table_bodies() -> dict[str, str]:
    pattern = re.compile(
        r"CREATE TABLE IF NOT EXISTS REVIEWLENS\.AUDIT\.(\w+)\s*\((.*?)\)\s*COMMENT\s*=",
        re.DOTALL,
    )
    return {name: body.upper() for name, body in pattern.findall(_source())}


def test_m4_enrichment_ledger_migration_is_additive_exact_and_secret_free() -> None:
    source = _source()
    upper = source.upper()
    tables = _table_bodies()

    assert set(tables) == EXPECTED_TABLES
    assert upper.count("CREATE TABLE IF NOT EXISTS") == 3
    assert "CREATE OR REPLACE" not in upper
    assert "DROP " not in upper
    assert "INSERT INTO" not in upper
    assert "MERGE INTO" not in upper
    assert "USE WAREHOUSE" not in upper
    for table in tables.values():
        assert "LEDGER_SCHEMA_VERSION NUMBER(10, 0) NOT NULL DEFAULT 1" in table
        assert "TRACE_ID VARCHAR(128) NOT NULL" in table
        assert "RECORDED_AT TIMESTAMP_TZ(9) NOT NULL DEFAULT CURRENT_TIMESTAMP()" in table
    for forbidden in (
        "REVIEW_TEXT",
        "PROMPT_TEXT",
        "RESPONSE_BODY",
        "RAW_PAYLOAD",
        "ORDER_ID",
        "CUSTOMER_ID",
        "SELLER_ID",
        "PAYMENT_VALUE",
        "API_KEY",
        "PRIVATE_KEY",
        "PASSWORD",
    ):
        assert forbidden not in upper


def test_m4_enrichment_ledger_migration_has_exact_append_only_ai_grants() -> None:
    grants = tuple(
        " ".join(statement.upper().split())
        for statement in split_sql_statements(_source())
        if statement.lstrip().upper().startswith("GRANT ")
    )

    assert grants == (
        "GRANT USAGE ON SCHEMA REVIEWLENS.AUDIT TO ROLE AI_ENRICH_ROLE",
        "GRANT SELECT, INSERT ON TABLE REVIEWLENS.AUDIT.AI_ENRICHMENT_RUN TO ROLE AI_ENRICH_ROLE",
        "GRANT SELECT, INSERT ON TABLE REVIEWLENS.AUDIT.AI_ENRICHMENT_INVOCATION "
        "TO ROLE AI_ENRICH_ROLE",
        "GRANT SELECT, INSERT ON TABLE REVIEWLENS.AUDIT.AI_ENRICHMENT_RESULT_MAP "
        "TO ROLE AI_ENRICH_ROLE",
    )
    assert not any(" ALL " in statement or "FUTURE" in statement for statement in grants)
    assert not any(
        privilege in statement
        for statement in grants
        for privilege in ("UPDATE", "DELETE", "TRUNCATE", "OWNERSHIP")
    )


def test_m4_enrichment_ledger_migration_replays_same_ddl_through_adapter_fake() -> None:
    connection = RecordingConnection()
    client = SnowflakeClient(connection)
    expected = split_sql_statements(_source())

    client.apply_sql_file(MIGRATION_PATH, operation="M4 enrichment ledger migration")
    client.apply_sql_file(MIGRATION_PATH, operation="M4 enrichment ledger migration replay")

    assert tuple(connection.statements) == expected + expected
    assert any("M4_ENRICHMENT_SCHEMA_COMPATIBILITY" in statement for statement in expected)
