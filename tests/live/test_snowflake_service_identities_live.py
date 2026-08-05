from __future__ import annotations

import os
from pathlib import Path

import pytest

from reviewlens.config import load_environment_values, load_settings
from reviewlens.providers.snowflake import SnowflakeClient

pytestmark = pytest.mark.live


def _require_opt_in() -> None:
    if os.environ.get("REVIEWLENS_RUN_LIVE_SNOWFLAKE_IDENTITIES") != "1":
        pytest.skip(
            "set REVIEWLENS_RUN_LIVE_SNOWFLAKE_IDENTITIES=1 for service identity provisioning"
        )


def test_live_service_identities_are_idempotent_and_exactly_role_scoped() -> None:
    _require_opt_in()
    settings = load_settings()
    credentials = load_environment_values()
    client = SnowflakeClient.connect_bootstrap(settings.snowflake)
    forbidden_roles = {"REVIEWLENS_OWNER", "SYSADMIN", "SECURITYADMIN", "ACCOUNTADMIN"}
    try:
        for _ in range(2):
            client.apply_sql_file(
                Path("infra/snowflake/003_service_identities.sql"),
                operation="Snowflake service identity statement",
            )

        for identity in settings.identities.snowflake_services:
            properties = {
                str(row[0]).upper(): str(row[1]).upper()
                for row in client.query_all(
                    f"DESCRIBE USER {identity.user}",
                    operation="Snowflake service user description",
                )
            }
            assert properties["TYPE"] == "SERVICE"
            assert properties["DEFAULT_ROLE"] == identity.role
            assert properties["DEFAULT_WAREHOUSE"] == identity.warehouse
            assert properties["DEFAULT_SECONDARY_ROLES"] in {"[]", "()", "NONE"}
            assert properties["DISABLED"] == "FALSE"

            grants = client.query_all(
                f"SHOW GRANTS TO USER {identity.user}",
                operation="Snowflake service user grants",
            )
            granted_roles = {str(row[4]).upper() for row in grants if row[4] is not None}
            assert granted_roles == {identity.role}
            assert granted_roles.isdisjoint(forbidden_roles)

            key_pairs = client.query_all(
                f"SHOW USER KEY PAIRS FOR USER {identity.user}",
                operation="Snowflake service user key-pair listing",
            )
            active_key = [
                row
                for row in key_pairs
                if str(row[0]).upper() == settings.identities.snowflake_key_pair_name
            ]
            assert len(active_key) == 1
            assert str(active_key[0][3]).upper() == identity.role
            assert str(active_key[0][4]).upper() == "ACTIVE"

            service_client = SnowflakeClient.connect_service(
                settings.snowflake,
                identity,
                credential_values=credentials,
            )
            try:
                facts = service_client.query_all(
                    "SELECT CURRENT_USER(), CURRENT_ROLE(), CURRENT_WAREHOUSE(), "
                    "CURRENT_DATABASE()",
                    operation="Snowflake service identity facts",
                )
                assert facts == [
                    (
                        identity.user,
                        identity.role,
                        identity.warehouse,
                        settings.snowflake.database,
                    )
                ]
            finally:
                service_client.close()
    finally:
        client.suspend_warehouse("REVIEWLENS_WH")
        client.suspend_warehouse("REVIEWLENS_SQL_WH")
        client.close()
