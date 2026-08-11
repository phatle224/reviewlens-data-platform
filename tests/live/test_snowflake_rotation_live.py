from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from reviewlens.config import AppSettings, load_environment_values, load_settings
from reviewlens.providers.snowflake import SnowflakeClient, SnowflakeProviderError
from reviewlens.security.snowflake_rotation import (
    RotationSmokePlan,
    build_rotation_smoke_plan,
    generate_ephemeral_rsa_key_pair,
    render_add_smoke_key_sql,
    render_remove_smoke_key_sql,
    render_rotate_smoke_key_sql,
    render_show_key_pairs_sql,
    require_rotation_confirmation,
)

pytestmark = pytest.mark.live


def _require_owner_opt_in() -> None:
    if os.environ.get("REVIEWLENS_RUN_LIVE_SNOWFLAKE_ROTATION") != "1":
        pytest.skip("set REVIEWLENS_RUN_LIVE_SNOWFLAKE_ROTATION=1 for the isolated rotation smoke")
    require_rotation_confirmation(os.environ.get("REVIEWLENS_SNOWFLAKE_ROTATION_CONFIRM"))


def _assert_exact_session(
    client: SnowflakeClient,
    *,
    user: str,
    role: str,
    warehouse: str,
    database: str,
) -> None:
    facts = client.query_all(
        "SELECT CURRENT_USER(), CURRENT_ROLE(), CURRENT_WAREHOUSE(), CURRENT_DATABASE()",
        operation="Snowflake rotation identity facts",
    )
    assert facts == [(user, role, warehouse, database)]


def _connect_with_key(
    *,
    settings: AppSettings,
    plan: RotationSmokePlan,
    private_key_path: Path,
) -> SnowflakeClient:
    # Kept local to this live test so ephemeral paths never enter process environment/.env.
    return SnowflakeClient.connect_service(
        settings.snowflake,
        plan.identity,
        credential_values={plan.identity.private_key_path_env: str(private_key_path)},
    )


def test_isolated_named_key_rotation_revokes_old_key_and_preserves_runtime_key() -> None:
    _require_owner_opt_in()
    settings = load_settings()
    credentials = load_environment_values()
    plan = build_rotation_smoke_plan(settings)
    bootstrap = SnowflakeClient.connect_bootstrap(settings.snowflake)
    smoke_key_registered = False
    try:
        runtime = SnowflakeClient.connect_service(
            settings.snowflake,
            plan.identity,
            credential_values=credentials,
        )
        try:
            _assert_exact_session(
                runtime,
                user=plan.identity.user,
                role=plan.identity.role,
                warehouse=plan.identity.warehouse,
                database=settings.snowflake.database,
            )
        finally:
            runtime.close()

        preflight_rows = bootstrap.query_all(
            render_show_key_pairs_sql(plan),
            operation="Snowflake rotation preflight",
        )
        assert not any(str(row[0]).upper() == plan.key_pair_name for row in preflight_rows), (
            "rotation smoke key already exists; inspect and clean it manually before retrying"
        )

        with TemporaryDirectory(prefix="reviewlens-snowflake-rotation-") as temp_dir:
            temp_path = Path(temp_dir)
            old_key = generate_ephemeral_rsa_key_pair(temp_path, stem="old_canary")
            new_key = generate_ephemeral_rsa_key_pair(temp_path, stem="new_canary")

            bootstrap.execute(
                render_add_smoke_key_sql(plan, old_key.public_key_body),
                operation="Snowflake rotation smoke key registration",
            )
            smoke_key_registered = True

            old_client = _connect_with_key(
                settings=settings,
                plan=plan,
                private_key_path=old_key.private_key_path,
            )
            try:
                _assert_exact_session(
                    old_client,
                    user=plan.identity.user,
                    role=plan.identity.role,
                    warehouse=plan.identity.warehouse,
                    database=settings.snowflake.database,
                )
            finally:
                old_client.close()

            bootstrap.execute(
                render_rotate_smoke_key_sql(plan, new_key.public_key_body),
                operation="Snowflake isolated key rotation",
            )

            try:
                unexpectedly_active = _connect_with_key(
                    settings=settings,
                    plan=plan,
                    private_key_path=old_key.private_key_path,
                )
            except SnowflakeProviderError:
                pass
            else:
                unexpectedly_active.close()
                pytest.fail("rotated-out temporary key still authenticated")

            new_client = _connect_with_key(
                settings=settings,
                plan=plan,
                private_key_path=new_key.private_key_path,
            )
            try:
                _assert_exact_session(
                    new_client,
                    user=plan.identity.user,
                    role=plan.identity.role,
                    warehouse=plan.identity.warehouse,
                    database=settings.snowflake.database,
                )
            finally:
                new_client.close()

            rotated_rows = bootstrap.query_all(
                render_show_key_pairs_sql(plan),
                operation="Snowflake rotation evidence inspection",
            )
            active = [row for row in rotated_rows if str(row[0]).upper() == plan.key_pair_name]
            assert len(active) == 1
            assert str(active[0][3]).upper() == plan.identity.role
            assert str(active[0][4]).upper() == "ACTIVE"
            rotated_old = [
                row
                for row in rotated_rows
                if str(row[0]).upper().startswith(f"{plan.key_pair_name}_ROTATED_")
                and str(row[9]).upper() == plan.key_pair_name
            ]
            # With grace=0 Snowflake may purge the immediately expired tombstone
            # before SHOW runs. If it is still visible, it must be non-active.
            assert all(str(row[4]).upper() in {"DISABLED", "EXPIRED"} for row in rotated_old)
    finally:
        try:
            if smoke_key_registered:
                bootstrap.execute(
                    render_remove_smoke_key_sql(plan),
                    operation="Snowflake rotation smoke key cleanup",
                )
                cleanup_rows = bootstrap.query_all(
                    render_show_key_pairs_sql(plan),
                    operation="Snowflake rotation cleanup verification",
                )
                assert not any(str(row[0]).upper() == plan.key_pair_name for row in cleanup_rows), (
                    "active rotation smoke key remained after cleanup"
                )
        finally:
            bootstrap.suspend_warehouse(plan.identity.warehouse)
            bootstrap.close()

    runtime_after = SnowflakeClient.connect_service(
        settings.snowflake,
        plan.identity,
        credential_values=credentials,
    )
    try:
        _assert_exact_session(
            runtime_after,
            user=plan.identity.user,
            role=plan.identity.role,
            warehouse=plan.identity.warehouse,
            database=settings.snowflake.database,
        )
    finally:
        runtime_after.close()
