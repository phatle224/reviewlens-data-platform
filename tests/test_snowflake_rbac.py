from __future__ import annotations

from pathlib import Path

from reviewlens.providers.snowflake import split_sql_statements

RBAC_PATH = Path("infra/snowflake/002_roles.sql")
SERVICE_ROLES = (
    "INGEST_ROLE",
    "TRANSFORMER_ROLE",
    "AI_ENRICH_ROLE",
    "VECTOR_INDEXER_ROLE",
    "GOLD_BUILDER_ROLE",
    "ANALYST_ROLE",
    "TEXT_TO_SQL_ROLE",
    "RAG_ROLE",
)


def _normalized_statements() -> tuple[str, ...]:
    source = RBAC_PATH.read_text(encoding="utf-8")
    return tuple(" ".join(statement.upper().split()) for statement in split_sql_statements(source))


def _direct_grants(role: str) -> tuple[str, ...]:
    suffix = f" TO ROLE {role}"
    return tuple(
        statement
        for statement in _normalized_statements()
        if statement.startswith("GRANT ") and statement.endswith(suffix)
    )


def test_role_hierarchy_is_complete_and_flows_up_to_sysadmin() -> None:
    statements = _normalized_statements()
    owner_statement = (
        "CREATE ROLE IF NOT EXISTS REVIEWLENS_OWNER COMMENT = "
        "'TOP CUSTOM REVIEWLENS ROLE; PARENT OF SERVICE ROLES, NEVER AN APP IDENTITY'"
    )
    assert owner_statement in statements
    for role in SERVICE_ROLES:
        assert any(
            statement.startswith(f"CREATE ROLE IF NOT EXISTS {role} ") for statement in statements
        )
        assert f"GRANT ROLE {role} TO ROLE REVIEWLENS_OWNER" in statements
    assert "GRANT ROLE REVIEWLENS_OWNER TO ROLE SYSADMIN" in statements
    assert not any(
        statement.startswith("GRANT ROLE SYSADMIN TO ROLE REVIEWLENS")
        or statement.startswith("GRANT ROLE ACCOUNTADMIN TO ROLE REVIEWLENS")
        for statement in statements
    )


def test_text_to_sql_has_an_isolated_cost_bounded_warehouse() -> None:
    normalized = " ".join(RBAC_PATH.read_text(encoding="utf-8").upper().split())
    assert "CREATE WAREHOUSE IF NOT EXISTS REVIEWLENS_SQL_WH" in normalized
    assert "WAREHOUSE_SIZE = XSMALL" in normalized
    assert "AUTO_SUSPEND = 60" in normalized
    assert "RESOURCE_MONITOR = REVIEWLENS_MONTHLY_MONITOR" in normalized
    sql_grants = _direct_grants("TEXT_TO_SQL_ROLE")
    assert "GRANT USAGE ON WAREHOUSE REVIEWLENS_SQL_WH TO ROLE TEXT_TO_SQL_ROLE" in sql_grants
    assert not any("REVIEWLENS_WH" in statement for statement in sql_grants)


def test_ingest_is_write_only_and_stage_scoped() -> None:
    grants = _direct_grants("INGEST_ROLE")
    assert "GRANT USAGE ON STAGE REVIEWLENS.BRONZE.R2_STAGE TO ROLE INGEST_ROLE" in grants
    assert "GRANT USAGE ON FILE FORMAT REVIEWLENS.BRONZE.JSONL_FORMAT TO ROLE INGEST_ROLE" in grants
    assert (
        "GRANT USAGE ON FILE FORMAT REVIEWLENS.BRONZE.OLIST_CSV_FORMAT TO ROLE INGEST_ROLE"
        in grants
    )
    assert "GRANT INSERT ON FUTURE TABLES IN SCHEMA REVIEWLENS.BRONZE TO ROLE INGEST_ROLE" in grants
    assert (
        "GRANT INSERT ON FUTURE TABLES IN SCHEMA REVIEWLENS.QUARANTINE TO ROLE INGEST_ROLE"
        in grants
    )
    assert not any(
        privilege in statement
        for statement in grants
        for privilege in ("GRANT SELECT ", "GRANT UPDATE ", "GRANT DELETE ", "GRANT TRUNCATE ")
    )


def test_transformer_is_limited_to_bronze_read_and_silver_build() -> None:
    grants = _direct_grants("TRANSFORMER_ROLE")
    assert (
        "GRANT SELECT ON FUTURE TABLES IN SCHEMA REVIEWLENS.BRONZE TO ROLE TRANSFORMER_ROLE"
        in grants
    )
    assert (
        "GRANT CREATE TABLE, CREATE VIEW ON SCHEMA REVIEWLENS.SILVER TO ROLE TRANSFORMER_ROLE"
        in grants
    )
    assert any(
        statement.startswith("GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON FUTURE TABLES")
        and "REVIEWLENS.SILVER" in statement
        for statement in grants
    )
    assert not any(
        schema in statement
        for statement in grants
        for schema in ("REVIEWLENS.AI", "REVIEWLENS.GOLD", "REVIEWLENS.AUDIT")
    )


def test_sensitive_consumers_have_no_schema_wide_object_grants() -> None:
    exact_only_roles = (
        "AI_ENRICH_ROLE",
        "VECTOR_INDEXER_ROLE",
        "GOLD_BUILDER_ROLE",
        "ANALYST_ROLE",
        "TEXT_TO_SQL_ROLE",
        "RAG_ROLE",
    )
    for role in exact_only_roles:
        grants = _direct_grants(role)
        assert not any(" ON ALL TABLES " in statement for statement in grants)
        assert not any(" ON FUTURE TABLES " in statement for statement in grants)
        assert not any(" ON ALL VIEWS " in statement for statement in grants)
        assert not any(" ON FUTURE VIEWS " in statement for statement in grants)


def test_no_public_account_admin_or_all_privilege_grants() -> None:
    statements = _normalized_statements()
    grant_statements = tuple(
        statement for statement in statements if statement.startswith("GRANT ")
    )
    assert not any("ALL PRIVILEGES" in statement for statement in grant_statements)
    assert not any(" ON ACCOUNT " in statement for statement in grant_statements)
    assert not any(statement.endswith(" TO ROLE PUBLIC") for statement in grant_statements)
    assert not any(" TO USER " in statement for statement in grant_statements)


def test_rbac_artifact_is_secret_free_and_idempotent_by_construction() -> None:
    source = RBAC_PATH.read_text(encoding="utf-8")
    assert "CREATE ROLE IF NOT EXISTS" in source
    assert "CREATE WAREHOUSE IF NOT EXISTS" in source
    assert "CREATE OR REPLACE" not in source
    for forbidden in ("PASSWORD", "PRIVATE_KEY", "AWS_SECRET", "OPENROUTER", "R2_ACCESS"):
        assert forbidden not in source.upper()
