from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import snowflake.connector
from pydantic import SecretStr

from reviewlens.config import load_settings
from reviewlens.providers.snowflake import (
    SnowflakeClient,
    SnowflakeProviderError,
    render_r2_stage_sql,
    split_sql_statements,
)


class FakeCursor:
    def __init__(self, statements: list[str], *, fail: bool = False) -> None:
        self.statements = statements
        self.fail = fail
        self.closed = False

    def execute(self, command: str) -> FakeCursor:
        self.statements.append(command)
        if self.fail:
            raise RuntimeError(f"provider echoed sensitive SQL: {command}")
        return self

    def fetchall(self) -> list[tuple[Any, ...]]:
        return [("synthetic-result",)]

    def close(self) -> None:
        self.closed = True


class FakeConnection:
    def __init__(self, *, fail: bool = False) -> None:
        self.statements: list[str] = []
        self.fail = fail
        self.closed = False

    def cursor(self) -> FakeCursor:
        return FakeCursor(self.statements, fail=self.fail)

    def close(self) -> None:
        self.closed = True


def test_foundation_sql_contract_matches_single_local_config() -> None:
    settings = load_settings(environ={})
    source = Path("infra/snowflake/001_foundation.sql").read_text(encoding="utf-8")
    normalized = " ".join(source.upper().split())

    assert f"CREATE DATABASE IF NOT EXISTS {settings.snowflake.database}" in normalized
    assert f"CREATE WAREHOUSE IF NOT EXISTS {settings.snowflake.warehouse}" in normalized
    assert "WAREHOUSE_SIZE = XSMALL" in normalized
    assert f"AUTO_SUSPEND = {settings.snowflake.auto_suspend_seconds}" in normalized
    assert "CREDIT_QUOTA = 10" in normalized
    assert "ON 50 PERCENT DO NOTIFY" in normalized
    assert "ON 80 PERCENT DO NOTIFY" in normalized
    assert "ON 100 PERCENT DO SUSPEND_IMMEDIATE" in normalized
    for schema in ("BRONZE", "SILVER", "AI", "GOLD", "AUDIT", "QUARANTINE"):
        assert f"CREATE SCHEMA IF NOT EXISTS REVIEWLENS.{schema}" in normalized
    assert "CREATE FILE FORMAT IF NOT EXISTS REVIEWLENS.BRONZE.OLIST_CSV_FORMAT" in normalized
    assert "TYPE = CSV" in normalized
    assert "SKIP_HEADER = 1" in normalized
    assert "FIELD_OPTIONALLY_ENCLOSED_BY = '\"'" in normalized


def test_foundation_sql_is_secret_free_and_splittable() -> None:
    source = Path("infra/snowflake/001_foundation.sql").read_text(encoding="utf-8")
    assert "AWS_KEY_ID" not in source
    assert "AWS_SECRET_KEY" not in source
    assert "r2.cloudflarestorage.com" not in source
    statements = split_sql_statements(source)
    assert len(statements) == 14
    assert all("--" not in statement for statement in statements)
    assert any("warehouse; approved private data only" in statement for statement in statements)


def test_sql_splitter_preserves_quotes_and_escaped_quotes() -> None:
    assert split_sql_statements("SELECT 'a;b'; SELECT 'it''s;safe';") == (
        "SELECT 'a;b'",
        "SELECT 'it''s;safe'",
    )


def test_r2_stage_sql_uses_s3_compat_and_manual_refresh() -> None:
    statement = render_r2_stage_sql(
        database="REVIEWLENS",
        bucket="reviewlens-data-dev",
        endpoint="https://seeded-account.r2.cloudflarestorage.com",
        access_key_id="seeded-access-key",
        secret_access_key="seeded-secret-key",
    )
    assert "URL = 's3compat://reviewlens-data-dev/'" in statement
    assert "ENDPOINT = 'seeded-account.r2.cloudflarestorage.com'" in statement
    assert "AUTO_REFRESH = FALSE" in statement
    assert "seeded-access-key" in statement
    assert "seeded-secret-key" in statement


@pytest.mark.parametrize(
    ("endpoint", "bucket"),
    [
        ("https://example.invalid", "reviewlens-data-dev"),
        ("https://seeded.r2.cloudflarestorage.com", "invalid/bucket"),
    ],
)
def test_r2_stage_rejects_invalid_provider_contract(endpoint: str, bucket: str) -> None:
    with pytest.raises(ValueError, match="R2"):
        render_r2_stage_sql(
            database="REVIEWLENS",
            bucket=bucket,
            endpoint=endpoint,
            access_key_id="seeded-access-key",
            secret_access_key="seeded-secret-key",
        )


def test_adapter_executes_foundation_and_returns_fake_query_results() -> None:
    fake = FakeConnection()
    client = SnowflakeClient(fake)
    client.apply_foundation(Path("infra/snowflake/001_foundation.sql"))
    result = client.query_all("SELECT 'synthetic-result'")
    client.close()

    assert len(fake.statements) == 15
    assert result == [("synthetic-result",)]
    assert fake.closed


def test_sensitive_provider_failure_does_not_echo_sql_or_credentials() -> None:
    fake = FakeConnection(fail=True)
    client = SnowflakeClient(fake)
    statement = render_r2_stage_sql(
        database="REVIEWLENS",
        bucket="reviewlens-data-dev",
        endpoint="https://seeded-account.r2.cloudflarestorage.com",
        access_key_id="seeded-access-key",
        secret_access_key="seeded-secret-key",
    )

    with pytest.raises(SnowflakeProviderError) as captured:
        client.execute(statement, operation="sensitive R2 stage creation")

    message = str(captured.value)
    assert message == "sensitive R2 stage creation failed"
    assert "seeded-access-key" not in message
    assert "seeded-secret-key" not in message


def test_stage_creation_and_list_use_adapter_boundary() -> None:
    settings = load_settings(environ={})
    r2 = settings.r2.model_copy(
        update={
            "account_id": "seeded-account",
            "access_key_id": SecretStr("seeded-access-key"),
            "secret_access_key": SecretStr("seeded-secret-key"),
        }
    )
    fake = FakeConnection()
    client = SnowflakeClient(fake)

    client.create_or_replace_r2_stage(snowflake=settings.snowflake, r2=r2)
    result = client.list_stage_path(
        database=settings.snowflake.database,
        key="manifests/_snowflake_smoke/synthetic.json",
    )

    assert "CREATE OR REPLACE STAGE REVIEWLENS.BRONZE.R2_STAGE" in fake.statements[0]
    assert fake.statements[1] == (
        "LIST @REVIEWLENS.BRONZE.R2_STAGE/manifests/_snowflake_smoke/synthetic.json"
    )
    assert result == [("synthetic-result",)]


def test_runtime_stage_uses_dedicated_read_only_credential_references() -> None:
    settings = load_settings(environ={})
    fake = FakeConnection()
    client = SnowflakeClient(fake)

    client.create_or_replace_r2_runtime_stage(
        snowflake=settings.snowflake,
        r2=settings.r2,
        identities=settings.identities,
        credential_values={
            "R2_ACCOUNT_ID": "seeded-account",
            "R2_STAGE_ACCESS_KEY_ID": "seeded-stage-access",
            "R2_STAGE_SECRET_ACCESS_KEY": "seeded-stage-secret",
            "R2_ACCESS_KEY_ID": "forbidden-bootstrap-access",
            "R2_SECRET_ACCESS_KEY": "forbidden-bootstrap-secret",
        },
    )

    statement = fake.statements[0]
    assert "seeded-stage-access" in statement
    assert "seeded-stage-secret" in statement
    assert "forbidden-bootstrap-access" not in statement
    assert "forbidden-bootstrap-secret" not in statement


def test_bootstrap_connection_uses_key_pair_without_target_objects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = load_settings(environ={})
    config = settings.snowflake.model_copy(
        update={
            "account": "seeded-account",
            "user": "seeded-user",
            "private_key_path": "C:/outside-repo/snowflake_key.p8",
            "password": None,
        }
    )
    captured: dict[str, Any] = {}

    def fake_connect(**kwargs: Any) -> FakeConnection:
        captured.update(kwargs)
        return FakeConnection()

    monkeypatch.setattr(snowflake.connector, "connect", fake_connect)
    client = SnowflakeClient.connect_bootstrap(config)
    client.close()

    assert captured["authenticator"] == "SNOWFLAKE_JWT"
    assert captured["private_key_file"] == "C:/outside-repo/snowflake_key.p8"
    assert "database" not in captured
    assert "warehouse" not in captured
    assert "role" not in captured


def test_bootstrap_connection_supports_password_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = load_settings(environ={})
    config = settings.snowflake.model_copy(
        update={
            "account": "seeded-account",
            "user": "seeded-user",
            "private_key_path": None,
            "password": SecretStr("seeded-password"),
        }
    )
    captured: dict[str, Any] = {}

    def fake_connect(**kwargs: Any) -> FakeConnection:
        captured.update(kwargs)
        return FakeConnection()

    monkeypatch.setattr(snowflake.connector, "connect", fake_connect)
    client = SnowflakeClient.connect_bootstrap(config)
    client.close()

    assert captured["password"] == "seeded-password"
    assert "private_key_file" not in captured


def test_bootstrap_connection_failure_is_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = load_settings(environ={})
    config = settings.snowflake.model_copy(
        update={
            "account": "seeded-account",
            "user": "seeded-user",
            "private_key_path": "C:/outside-repo/snowflake_key.p8",
        }
    )

    def fail_connect(**kwargs: Any) -> FakeConnection:
        raise RuntimeError(f"provider echoed kwargs: {kwargs}")

    monkeypatch.setattr(snowflake.connector, "connect", fail_connect)
    with pytest.raises(SnowflakeProviderError) as captured:
        SnowflakeClient.connect_bootstrap(config)

    assert str(captured.value) == "Snowflake bootstrap connection failed"
    assert "seeded" not in str(captured.value)


def test_suspend_warehouse_is_best_effort() -> None:
    success = FakeConnection()
    SnowflakeClient(success).suspend_warehouse("REVIEWLENS_WH")
    assert success.statements == ["ALTER WAREHOUSE REVIEWLENS_WH SUSPEND"]

    failing = FakeConnection(fail=True)
    SnowflakeClient(failing).suspend_warehouse("REVIEWLENS_WH")


@pytest.mark.parametrize(
    ("database", "key"),
    [("REVIEWLENS; DROP DATABASE X", "safe.json"), ("REVIEWLENS", "../secret")],
)
def test_stage_list_rejects_unsafe_identifiers_and_keys(database: str, key: str) -> None:
    client = SnowflakeClient(FakeConnection())
    with pytest.raises(ValueError, match="unsafe"):
        client.list_stage_path(database=database, key=key)
