from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from reviewlens.providers.snowflake import SnowflakeClient, split_sql_statements

UP_PATH = Path("infra/snowflake/004_audit_ledgers.sql")
DOWN_PATH = Path("infra/snowflake/004_audit_ledgers_down.sql")

EXPECTED_TABLES = {
    "INGESTION_EVENT",
    "SOURCE_FILE_EVENT",
    "PROCESS_EVENT",
    "RELEASE_EVENT",
    "ACTIVE_RELEASE_POINTER",
    "AI_INVOCATION_EVENT",
}
EVENT_TABLES = EXPECTED_TABLES - {"ACTIVE_RELEASE_POINTER"}


class RecordingCursor:
    def __init__(self, statements: list[str]) -> None:
        self._statements = statements

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


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _normalized_statements() -> tuple[str, ...]:
    return tuple(
        " ".join(statement.upper().split()) for statement in split_sql_statements(_source(UP_PATH))
    )


def _table_bodies() -> dict[str, str]:
    pattern = re.compile(
        r"CREATE TABLE IF NOT EXISTS REVIEWLENS\.AUDIT\.(\w+)\s*\((.*?)\)\s*COMMENT\s*=",
        re.DOTALL,
    )
    return {name: body.upper() for name, body in pattern.findall(_source(UP_PATH))}


def test_up_migration_has_complete_versioned_ledger_contract() -> None:
    tables = _table_bodies()

    assert set(tables) == EXPECTED_TABLES
    for table_name in EVENT_TABLES:
        body = tables[table_name]
        assert "LEDGER_SCHEMA_VERSION NUMBER(10, 0) NOT NULL DEFAULT 1" in body
        assert "TRACE_ID VARCHAR(128) NOT NULL" in body
        assert "RECORDED_AT TIMESTAMP_TZ(9) NOT NULL DEFAULT CURRENT_TIMESTAMP()" in body
        primary_key = "INVOCATION_ID" if table_name == "AI_INVOCATION_EVENT" else "EVENT_ID"
        assert f"PRIMARY KEY ({primary_key})" in body

    assert "SOURCE_OBJECT_SHA256 VARCHAR(64) NOT NULL" in tables["SOURCE_FILE_EVENT"]
    assert "PHYSICAL_ROW_COUNT NUMBER(38, 0)" in tables["SOURCE_FILE_EVENT"]
    assert "CANDIDATE_VERSION VARCHAR(128)" in tables["PROCESS_EVENT"]
    assert "PREVIOUS_RELEASE_ID VARCHAR(64)" in tables["RELEASE_EVENT"]
    assert "POINTER_VERSION NUMBER(38, 0) NOT NULL" in tables["ACTIVE_RELEASE_POINTER"]


def test_ai_ledger_tracks_cost_versions_and_hashes_without_restricted_content() -> None:
    body = _table_bodies()["AI_INVOCATION_EVENT"]

    for required in (
        "MODEL_ID",
        "PROMPT_VERSION",
        "OUTPUT_SCHEMA_VERSION",
        "PROVIDER_POLICY_VERSION",
        "INPUT_TOKEN_COUNT",
        "OUTPUT_TOKEN_COUNT",
        "COST_USD",
        "LATENCY_MS",
        "REQUEST_HASH",
        "RESPONSE_HASH",
        "SANITIZED_ERROR_CODE",
    ):
        assert required in body
    for forbidden in (
        "REVIEW_TEXT",
        "PROMPT_TEXT",
        "RESPONSE_BODY",
        "RAW_PAYLOAD",
        "EMAIL",
        "PHONE",
        "TOKEN_VALUE",
        "API_KEY",
    ):
        assert forbidden not in body


def test_up_migration_is_secret_free_additive_and_idempotent_by_construction() -> None:
    source = _source(UP_PATH)
    upper = source.upper()
    statements = _normalized_statements()

    assert upper.count("CREATE TABLE IF NOT EXISTS") == len(EXPECTED_TABLES)
    assert "CREATE OR REPLACE" not in upper
    assert "DROP TABLE" not in upper
    assert "DROP SCHEMA" not in upper
    assert "PASSWORD" not in upper
    assert "PRIVATE_KEY" not in upper
    assert "AWS_SECRET" not in upper
    assert "OPENROUTER_API_KEY" not in upper
    assert "MERGE INTO" not in upper
    assert "INSERT INTO" not in upper
    assert "USE WAREHOUSE" not in upper
    assert any(
        statement.startswith("CREATE VIEW IF NOT EXISTS REVIEWLENS.AUDIT.SCHEMA_COMPATIBILITY")
        for statement in statements
    )
    assert statements == _normalized_statements()


def test_up_migration_replays_the_same_ddl_only_plan_through_adapter() -> None:
    connection = RecordingConnection()
    client = SnowflakeClient(connection)
    expected = split_sql_statements(_source(UP_PATH))

    client.apply_sql_file(UP_PATH, operation="audit migration")
    client.apply_sql_file(UP_PATH, operation="audit migration replay")

    assert tuple(connection.statements) == expected + expected
    assert all(not statement.lstrip().upper().startswith("MERGE ") for statement in expected)
    assert all(not statement.lstrip().upper().startswith("INSERT ") for statement in expected)


def test_runtime_grants_keep_event_ledgers_append_only_and_exact() -> None:
    grant_statements = tuple(
        statement for statement in _normalized_statements() if statement.startswith("GRANT ")
    )

    assert (
        "GRANT SELECT, INSERT ON TABLE REVIEWLENS.AUDIT.INGESTION_EVENT TO ROLE INGEST_ROLE"
        in grant_statements
    )
    assert (
        "GRANT SELECT, INSERT ON TABLE REVIEWLENS.AUDIT.AI_INVOCATION_EVENT TO ROLE AI_ENRICH_ROLE"
        in grant_statements
    )
    assert not any(" ON ALL TABLES " in statement for statement in grant_statements)
    assert not any(" ON FUTURE TABLES " in statement for statement in grant_statements)
    assert not any(
        privilege in statement
        for statement in grant_statements
        for privilege in ("UPDATE", "DELETE", "TRUNCATE", "OWNERSHIP", "ALL PRIVILEGES")
    )


def test_active_release_pointer_is_read_only_until_guarded_release_procedure_exists() -> None:
    pointer_grants = tuple(
        statement
        for statement in _normalized_statements()
        if "REVIEWLENS.AUDIT.ACTIVE_RELEASE_POINTER" in statement and statement.startswith("GRANT ")
    )

    assert len(pointer_grants) == 4
    assert all(statement.startswith("GRANT SELECT ON TABLE ") for statement in pointer_grants)
    assert {statement.rsplit(" ", maxsplit=1)[-1] for statement in pointer_grants} == {
        "GOLD_BUILDER_ROLE",
        "ANALYST_ROLE",
        "TEXT_TO_SQL_ROLE",
        "RAG_ROLE",
    }


def test_schema_compatibility_marker_is_stable_and_contains_no_source_data() -> None:
    source = _source(UP_PATH)
    upper = source.upper()

    assert "'IMP-M1-013-AUDIT-V1'::VARCHAR(128) AS MIGRATION_ID" in upper
    assert "1::NUMBER(10, 0) AS SCHEMA_VERSION" in upper
    assert "'INFRA/SNOWFLAKE/004_AUDIT_LEDGERS.SQL'::VARCHAR(256) AS ARTIFACT_NAME" in upper
    compatibility_statement = next(
        statement
        for statement in _normalized_statements()
        if statement.startswith("CREATE VIEW IF NOT EXISTS REVIEWLENS.AUDIT.SCHEMA_COMPATIBILITY")
    )
    for forbidden in ("SOURCE_RECORD_HASH", "SOURCE_FILE_NAME", "SANITIZED_METADATA"):
        assert forbidden not in compatibility_statement


def test_down_migration_fails_closed_before_local_only_destructive_steps() -> None:
    source = _source(DOWN_PATH)
    upper = source.upper()

    assert "EXECUTE IMMEDIATE $$" in upper
    assert "GETVARIABLE('REVIEWLENS_RUNTIME')" in upper
    assert "GETVARIABLE('REVIEWLENS_AUDIT_DOWN_CONFIRMATION')" in upper
    assert "COALESCE(RUNTIME_NAME, '') <> 'LOCAL'" in upper
    assert "COALESCE(CONFIRMATION, '') <> 'DROP_REVIEWLENS_AUDIT_LEDGERS'" in upper
    assert upper.index("RAISE DESTRUCTIVE_DOWN_DENIED") < upper.index("DROP TABLE IF EXISTS")
    assert "DROP DATABASE" not in upper
    assert "DROP SCHEMA" not in upper
    assert "DROP VIEW IF EXISTS REVIEWLENS.AUDIT.SCHEMA_COMPATIBILITY" in upper
    for table_name in EXPECTED_TABLES:
        assert f"DROP TABLE IF EXISTS REVIEWLENS.AUDIT.{table_name}" in upper
