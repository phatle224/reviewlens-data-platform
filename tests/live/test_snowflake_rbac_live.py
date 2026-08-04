from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path

import pytest

from reviewlens.config import DataMode, load_settings
from reviewlens.providers.snowflake import SnowflakeClient, SnowflakeProviderError

pytestmark = pytest.mark.live

PRIMARY_WAREHOUSE = "REVIEWLENS_WH"
SQL_WAREHOUSE = "REVIEWLENS_SQL_WH"

FIXTURE_DDL = (
    "CREATE OR REPLACE TABLE REVIEWLENS.BRONZE.__M1_RBAC_BRONZE (id NUMBER, payload VARIANT)",
    "CREATE OR REPLACE TABLE REVIEWLENS.QUARANTINE.__M1_RBAC_QUARANTINE "
    "(id NUMBER, reason VARCHAR)",
    "CREATE OR REPLACE TABLE REVIEWLENS.SILVER.__M1_RBAC_SILVER (id NUMBER, data_class VARCHAR)",
    "CREATE OR REPLACE TABLE REVIEWLENS.AI.__M1_RBAC_ENRICH (id NUMBER, label VARCHAR)",
    "CREATE OR REPLACE TABLE REVIEWLENS.AUDIT.__M1_RBAC_INVOCATION (id NUMBER, event_type VARCHAR)",
    "CREATE OR REPLACE TABLE REVIEWLENS.GOLD.__M1_RBAC_BUILD (id NUMBER, metric NUMBER)",
    "INSERT INTO REVIEWLENS.SILVER.__M1_RBAC_SILVER VALUES (1, 'synthetic')",
    "INSERT INTO REVIEWLENS.GOLD.__M1_RBAC_BUILD VALUES (1, 1)",
    "CREATE OR REPLACE SECURE VIEW REVIEWLENS.SILVER.__M1_RBAC_AI_REVIEW AS "
    "SELECT id, data_class FROM REVIEWLENS.SILVER.__M1_RBAC_SILVER",
    "CREATE OR REPLACE SECURE VIEW REVIEWLENS.AI.__M1_RBAC_RAG_DOCUMENT AS "
    "SELECT id, data_class FROM REVIEWLENS.SILVER.__M1_RBAC_SILVER",
    "CREATE OR REPLACE SECURE VIEW REVIEWLENS.AI.__M1_RBAC_GOLD_INPUT AS "
    "SELECT id, data_class FROM REVIEWLENS.SILVER.__M1_RBAC_SILVER",
    "CREATE OR REPLACE SECURE VIEW REVIEWLENS.GOLD.__M1_RBAC_ANALYTICS AS "
    "SELECT id, metric FROM REVIEWLENS.GOLD.__M1_RBAC_BUILD",
)

EXACT_GRANTS = (
    "GRANT SELECT ON VIEW REVIEWLENS.SILVER.__M1_RBAC_AI_REVIEW TO ROLE AI_ENRICH_ROLE",
    "GRANT INSERT ON TABLE REVIEWLENS.AI.__M1_RBAC_ENRICH TO ROLE AI_ENRICH_ROLE",
    "GRANT INSERT ON TABLE REVIEWLENS.AUDIT.__M1_RBAC_INVOCATION TO ROLE AI_ENRICH_ROLE",
    "GRANT SELECT ON VIEW REVIEWLENS.AI.__M1_RBAC_RAG_DOCUMENT TO ROLE VECTOR_INDEXER_ROLE",
    "GRANT SELECT ON VIEW REVIEWLENS.SILVER.__M1_RBAC_AI_REVIEW TO ROLE GOLD_BUILDER_ROLE",
    "GRANT SELECT ON VIEW REVIEWLENS.AI.__M1_RBAC_GOLD_INPUT TO ROLE GOLD_BUILDER_ROLE",
    "GRANT INSERT ON TABLE REVIEWLENS.GOLD.__M1_RBAC_BUILD TO ROLE GOLD_BUILDER_ROLE",
    "GRANT SELECT ON VIEW REVIEWLENS.GOLD.__M1_RBAC_ANALYTICS TO ROLE ANALYST_ROLE",
    "GRANT SELECT ON VIEW REVIEWLENS.GOLD.__M1_RBAC_ANALYTICS TO ROLE TEXT_TO_SQL_ROLE",
    "GRANT SELECT ON VIEW REVIEWLENS.AI.__M1_RBAC_RAG_DOCUMENT TO ROLE RAG_ROLE",
)

CLEANUP_DDL = (
    "DROP VIEW IF EXISTS REVIEWLENS.GOLD.__M1_RBAC_ANALYTICS",
    "DROP VIEW IF EXISTS REVIEWLENS.AI.__M1_RBAC_GOLD_INPUT",
    "DROP VIEW IF EXISTS REVIEWLENS.AI.__M1_RBAC_RAG_DOCUMENT",
    "DROP VIEW IF EXISTS REVIEWLENS.SILVER.__M1_RBAC_AI_REVIEW",
    "DROP TABLE IF EXISTS REVIEWLENS.GOLD.__M1_RBAC_BUILD",
    "DROP TABLE IF EXISTS REVIEWLENS.AUDIT.__M1_RBAC_INVOCATION",
    "DROP TABLE IF EXISTS REVIEWLENS.AI.__M1_RBAC_ENRICH",
    "DROP TABLE IF EXISTS REVIEWLENS.SILVER.__M1_RBAC_SILVER",
    "DROP TABLE IF EXISTS REVIEWLENS.QUARANTINE.__M1_RBAC_QUARANTINE",
    "DROP TABLE IF EXISTS REVIEWLENS.BRONZE.__M1_RBAC_BRONZE",
)


def _activate_role(client: SnowflakeClient, role: str, warehouse: str) -> None:
    client.execute(f"USE ROLE {role}", operation=f"activate {role}")
    client.execute("USE SECONDARY ROLES NONE", operation="disable secondary roles")
    client.execute(f"USE WAREHOUSE {warehouse}", operation=f"select warehouse for {role}")
    assert client.query_all("SELECT CURRENT_ROLE()") == [(role,)]


def _assert_denied(client: SnowflakeClient, statements: Iterable[str]) -> None:
    for statement in statements:
        with pytest.raises(SnowflakeProviderError, match="RBAC negative probe failed"):
            client.execute(statement, operation="RBAC negative probe")


@pytest.mark.skipif(
    os.environ.get("REVIEWLENS_RUN_LIVE_SNOWFLAKE_RBAC") != "1",
    reason="set REVIEWLENS_RUN_LIVE_SNOWFLAKE_RBAC=1 for Snowflake RBAC live tests",
)
def test_snowflake_service_roles_positive_and_negative_permissions() -> None:
    settings = load_settings()
    assert settings.data_mode is DataMode.SYNTHETIC
    client = SnowflakeClient.connect_bootstrap(settings.snowflake)
    role_path = Path("infra/snowflake/002_roles.sql")

    try:
        client.apply_foundation(Path("infra/snowflake/001_foundation.sql"))
        client.apply_sql_file(role_path, operation="Snowflake RBAC provisioning statement")
        client.execute("USE ROLE ACCOUNTADMIN", operation="activate bootstrap role")
        client.execute("USE SECONDARY ROLES NONE", operation="disable bootstrap secondary roles")
        client.execute(f"USE WAREHOUSE {PRIMARY_WAREHOUSE}", operation="select bootstrap warehouse")
        client.execute_all(FIXTURE_DDL, operation="create synthetic RBAC fixture")

        # Re-apply to prove idempotency and materialize ALL grants on the new fixture tables.
        client.apply_sql_file(role_path, operation="Snowflake RBAC idempotency statement")
        client.execute_all(EXACT_GRANTS, operation="grant synthetic RBAC fixture access")

        _activate_role(client, "INGEST_ROLE", PRIMARY_WAREHOUSE)
        client.execute(
            "INSERT INTO REVIEWLENS.BRONZE.__M1_RBAC_BRONZE "
            'SELECT 1, PARSE_JSON(\'{"data_class":"synthetic"}\')',
            operation="INGEST_ROLE positive insert",
        )
        client.execute(
            "INSERT INTO REVIEWLENS.QUARANTINE.__M1_RBAC_QUARANTINE VALUES (1, 'synthetic-test')",
            operation="INGEST_ROLE positive quarantine insert",
        )
        _assert_denied(
            client,
            (
                "SELECT * FROM REVIEWLENS.BRONZE.__M1_RBAC_BRONZE",
                "UPDATE REVIEWLENS.BRONZE.__M1_RBAC_BRONZE SET id = 2",
                "DELETE FROM REVIEWLENS.BRONZE.__M1_RBAC_BRONZE",
                "SELECT * FROM REVIEWLENS.GOLD.__M1_RBAC_ANALYTICS",
            ),
        )

        _activate_role(client, "TRANSFORMER_ROLE", PRIMARY_WAREHOUSE)
        assert client.query_all("SELECT COUNT(*) FROM REVIEWLENS.BRONZE.__M1_RBAC_BRONZE") == [(1,)]
        client.execute(
            "INSERT INTO REVIEWLENS.SILVER.__M1_RBAC_SILVER VALUES (2, 'synthetic')",
            operation="TRANSFORMER_ROLE positive Silver insert",
        )
        _assert_denied(
            client,
            (
                "INSERT INTO REVIEWLENS.BRONZE.__M1_RBAC_BRONZE SELECT 2, NULL",
                "SELECT * FROM REVIEWLENS.AI.__M1_RBAC_ENRICH",
                "SELECT * FROM REVIEWLENS.GOLD.__M1_RBAC_ANALYTICS",
            ),
        )

        _activate_role(client, "AI_ENRICH_ROLE", PRIMARY_WAREHOUSE)
        assert client.query_all("SELECT COUNT(*) FROM REVIEWLENS.SILVER.__M1_RBAC_AI_REVIEW") == [
            (2,)
        ]
        client.execute(
            "INSERT INTO REVIEWLENS.AI.__M1_RBAC_ENRICH VALUES (1, 'synthetic')",
            operation="AI_ENRICH_ROLE positive AI insert",
        )
        client.execute(
            "INSERT INTO REVIEWLENS.AUDIT.__M1_RBAC_INVOCATION VALUES (1, 'synthetic')",
            operation="AI_ENRICH_ROLE positive audit insert",
        )
        _assert_denied(
            client,
            (
                "SELECT * FROM REVIEWLENS.SILVER.__M1_RBAC_SILVER",
                "INSERT INTO REVIEWLENS.GOLD.__M1_RBAC_BUILD VALUES (2, 2)",
                "SELECT * FROM REVIEWLENS.BRONZE.__M1_RBAC_BRONZE",
            ),
        )

        _activate_role(client, "VECTOR_INDEXER_ROLE", PRIMARY_WAREHOUSE)
        assert client.query_all("SELECT COUNT(*) FROM REVIEWLENS.AI.__M1_RBAC_RAG_DOCUMENT") == [
            (2,)
        ]
        _assert_denied(
            client,
            (
                "SELECT * FROM REVIEWLENS.SILVER.__M1_RBAC_SILVER",
                "INSERT INTO REVIEWLENS.AI.__M1_RBAC_ENRICH VALUES (2, 'denied')",
                "SELECT * FROM REVIEWLENS.GOLD.__M1_RBAC_ANALYTICS",
            ),
        )

        _activate_role(client, "GOLD_BUILDER_ROLE", PRIMARY_WAREHOUSE)
        assert client.query_all("SELECT COUNT(*) FROM REVIEWLENS.AI.__M1_RBAC_GOLD_INPUT") == [(2,)]
        client.execute(
            "INSERT INTO REVIEWLENS.GOLD.__M1_RBAC_BUILD VALUES (2, 2)",
            operation="GOLD_BUILDER_ROLE positive Gold insert",
        )
        _assert_denied(
            client,
            (
                "SELECT * FROM REVIEWLENS.BRONZE.__M1_RBAC_BRONZE",
                "UPDATE REVIEWLENS.SILVER.__M1_RBAC_SILVER SET id = 3",
                "SELECT * FROM REVIEWLENS.AI.__M1_RBAC_ENRICH",
            ),
        )

        _activate_role(client, "ANALYST_ROLE", PRIMARY_WAREHOUSE)
        assert client.query_all("SELECT COUNT(*) FROM REVIEWLENS.GOLD.__M1_RBAC_ANALYTICS") == [
            (2,)
        ]
        _assert_denied(
            client,
            (
                "INSERT INTO REVIEWLENS.GOLD.__M1_RBAC_BUILD VALUES (3, 3)",
                "SELECT * FROM REVIEWLENS.BRONZE.__M1_RBAC_BRONZE",
                "SELECT * FROM REVIEWLENS.AI.__M1_RBAC_RAG_DOCUMENT",
            ),
        )

        _activate_role(client, "TEXT_TO_SQL_ROLE", SQL_WAREHOUSE)
        assert client.query_all("SELECT COUNT(*) FROM REVIEWLENS.GOLD.__M1_RBAC_ANALYTICS") == [
            (2,)
        ]
        _assert_denied(
            client,
            (
                "INSERT INTO REVIEWLENS.GOLD.__M1_RBAC_BUILD VALUES (3, 3)",
                "SELECT * FROM REVIEWLENS.BRONZE.__M1_RBAC_BRONZE",
                "SELECT * FROM REVIEWLENS.AI.__M1_RBAC_RAG_DOCUMENT",
            ),
        )

        _activate_role(client, "RAG_ROLE", PRIMARY_WAREHOUSE)
        assert client.query_all("SELECT COUNT(*) FROM REVIEWLENS.AI.__M1_RBAC_RAG_DOCUMENT") == [
            (2,)
        ]
        _assert_denied(
            client,
            (
                "SELECT * FROM REVIEWLENS.SILVER.__M1_RBAC_SILVER",
                "INSERT INTO REVIEWLENS.AI.__M1_RBAC_ENRICH VALUES (3, 'denied')",
                "SELECT * FROM REVIEWLENS.GOLD.__M1_RBAC_ANALYTICS",
            ),
        )
    finally:
        try:
            client.execute("USE ROLE ACCOUNTADMIN", operation="restore bootstrap role")
            client.execute("USE SECONDARY ROLES NONE", operation="disable cleanup secondary roles")
            client.execute_all(CLEANUP_DDL, operation="drop synthetic RBAC fixture")
        finally:
            client.suspend_warehouse(PRIMARY_WAREHOUSE)
            client.suspend_warehouse(SQL_WAREHOUSE)
            client.close()
