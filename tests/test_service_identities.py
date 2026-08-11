from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import snowflake.connector
from pydantic import ValidationError

from reviewlens.config import EXPECTED_SNOWFLAKE_IDENTITIES, ServiceName, load_settings
from reviewlens.providers.snowflake import SnowflakeClient, SnowflakeProviderError
from reviewlens.security.credentials import inspect_credential_readiness

IDENTITY_DDL = Path("infra/snowflake/003_service_identities.sql")
RUNBOOK = Path("docs/runbooks/M1_CREDENTIAL_ROTATION.md")
EMPTY_ENV = Path("tests/fixtures/.missing-service-identity.env")


class FakeCursor:
    def __init__(
        self,
        statements: list[str],
        *,
        fail: bool = False,
        rows: list[tuple[Any, ...]] | None = None,
    ) -> None:
        self.statements = statements
        self.fail = fail
        self.rows = rows or [(r'{"roles":"","value":""}',)]
        self.closed = False

    def execute(self, command: str) -> FakeCursor:
        self.statements.append(command)
        if self.fail:
            raise RuntimeError(f"provider leaked statement: {command}")
        return self

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self.rows

    def close(self) -> None:
        self.closed = True


class FakeConnection:
    def __init__(
        self,
        *,
        fail: bool = False,
        rows: list[tuple[Any, ...]] | None = None,
    ) -> None:
        self.statements: list[str] = []
        self.fail = fail
        self.rows = rows
        self.closed = False

    def cursor(self) -> FakeCursor:
        return FakeCursor(self.statements, fail=self.fail, rows=self.rows)

    def close(self) -> None:
        self.closed = True


def test_typed_identity_inventory_is_exact_and_least_privilege() -> None:
    settings = load_settings(environ={}, env_file=EMPTY_ENV)
    identities = {item.service: item for item in settings.identities.snowflake_services}

    assert set(identities) == set(ServiceName)
    assert settings.identities.credential_max_age_days == 90
    assert settings.identities.rotation_grace_hours == 24
    assert settings.identities.r2_ingest_access_key_env != (
        settings.identities.r2_stage_access_key_env
    )
    for service, expected in EXPECTED_SNOWFLAKE_IDENTITIES.items():
        identity = identities[service]
        assert (identity.user, identity.role, identity.warehouse) == expected
        assert identity.role not in {
            "REVIEWLENS_OWNER",
            "SYSADMIN",
            "SECURITYADMIN",
            "ACCOUNTADMIN",
        }


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ('role = "INGEST_ROLE"', 'role = "ACCOUNTADMIN"', "least-privilege"),
        (
            'user = "REVIEWLENS_TRANSFORM_SVC"',
            'user = "REVIEWLENS_INGEST_SVC"',
            "unique",
        ),
        (
            'r2_stage_access_key_env = "R2_STAGE_ACCESS_KEY_ID"',
            'r2_stage_access_key_env = "R2_INGEST_ACCESS_KEY_ID"',
            "distinct",
        ),
    ],
)
def test_identity_inventory_rejects_boundary_weakening(
    tmp_path: Path, old: str, new: str, message: str
) -> None:
    profile = Path("config/config.toml").read_text(encoding="utf-8").replace(old, new)
    config_path = tmp_path / "config.toml"
    config_path.write_text(profile, encoding="utf-8")
    with pytest.raises(ValidationError, match=message):
        load_settings(environ={}, config_path=config_path, env_file=tmp_path / ".env")


def test_credential_readiness_is_boolean_only_and_never_leaks_values(tmp_path: Path) -> None:
    settings = load_settings(environ={}, env_file=tmp_path / ".env")
    environment = {
        "SNOWFLAKE_ACCOUNT": "seeded-account",
        "R2_ACCOUNT_ID": "seeded-r2-account",
        "R2_INGEST_ACCESS_KEY_ID": "seeded-ingest-access",
        "R2_INGEST_SECRET_ACCESS_KEY": "seeded-ingest-secret",
        "R2_STAGE_ACCESS_KEY_ID": "seeded-stage-access",
        "R2_STAGE_SECRET_ACCESS_KEY": "seeded-stage-secret",
        "OPENROUTER_API_KEY": "sk-or-v1-seeded",
        "CHROMA_AUTH_TOKEN": "seeded-chroma-token",
        "APP_AUTH_TOKEN": "seeded-app-token",
    }
    for identity in settings.identities.snowflake_services:
        environment[identity.private_key_path_env] = f"C:/keys/{identity.service.value}.p8"

    readiness = inspect_credential_readiness(
        settings,
        environ=environment,
        env_file=tmp_path / ".env",
    )
    text = str(readiness.model_dump(mode="json"))

    assert readiness.all_runtime_credentials_configured
    assert all(readiness.snowflake.values())
    for value in environment.values():
        assert value not in text


def test_credential_readiness_fails_closed_when_dedicated_values_are_absent(
    tmp_path: Path,
) -> None:
    settings = load_settings(environ={}, env_file=tmp_path / ".env")
    readiness = inspect_credential_readiness(
        settings,
        environ={},
        env_file=tmp_path / ".env",
    )

    assert not readiness.all_runtime_credentials_configured
    assert not any(readiness.snowflake.values())
    assert not any(
        (
            readiness.r2_ingest,
            readiness.r2_stage,
            readiness.openrouter,
            readiness.chroma,
            readiness.app,
        )
    )


def test_service_user_ddl_is_disabled_secret_free_and_one_role_per_user() -> None:
    source = IDENTITY_DDL.read_text(encoding="utf-8")
    normalized = " ".join(
        line.strip() for line in source.upper().splitlines() if not line.startswith("--")
    )

    assert normalized.count("CREATE USER IF NOT EXISTS") == 8
    assert normalized.count("TYPE = SERVICE") == 16
    assert normalized.count("DISABLED = TRUE") == 8
    assert normalized.count("DEFAULT_SECONDARY_ROLES = ()") == 16
    for user, role, warehouse in EXPECTED_SNOWFLAKE_IDENTITIES.values():
        assert f"CREATE USER IF NOT EXISTS {user}" in normalized
        assert f"DEFAULT_ROLE = {role}" in normalized
        assert f"DEFAULT_WAREHOUSE = {warehouse}" in normalized
        assert f"GRANT ROLE {role} TO USER {user}" in normalized
    for forbidden in (
        "PASSWORD =",
        "RSA_PUBLIC_KEY",
        "ADD KEY PAIR",
        "GRANT ROLE ACCOUNTADMIN",
        "GRANT ROLE SECURITYADMIN",
        "GRANT ROLE SYSADMIN",
        "GRANT ROLE REVIEWLENS_OWNER TO USER",
    ):
        assert forbidden not in normalized


def test_service_user_ddl_does_not_disable_existing_activated_users_on_reapply() -> None:
    statements = [
        " ".join(part.split())
        for part in IDENTITY_DDL.read_text(encoding="utf-8").split(";")
        if part.strip()
    ]
    alter_statements = [statement.upper() for statement in statements if "ALTER USER" in statement]
    assert len(alter_statements) == 8
    assert not any("DISABLED" in statement for statement in alter_statements)


def test_service_connection_uses_exact_identity_key_and_verifies_no_secondary_roles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = load_settings(environ={}, env_file=EMPTY_ENV)
    identity = next(
        item
        for item in settings.identities.snowflake_services
        if item.service is ServiceName.TEXT_TO_SQL
    )
    config = settings.snowflake.model_copy(update={"account": "seeded-account"})
    captured: dict[str, Any] = {}
    fake = FakeConnection()

    def fake_connect(**kwargs: Any) -> FakeConnection:
        captured.update(kwargs)
        return fake

    monkeypatch.setattr(snowflake.connector, "connect", fake_connect)
    client = SnowflakeClient.connect_service(
        config,
        identity,
        credential_values={
            identity.private_key_path_env: "C:/outside-repo/text_to_sql.p8",
            identity.private_key_passphrase_env: "seeded-passphrase",
        },
    )
    client.close()

    assert captured["user"] == "REVIEWLENS_TEXT_TO_SQL_SVC"
    assert captured["role"] == "TEXT_TO_SQL_ROLE"
    assert captured["warehouse"] == "REVIEWLENS_SQL_WH"
    assert captured["database"] == "REVIEWLENS"
    assert captured["authenticator"] == "SNOWFLAKE_JWT"
    assert captured["private_key_file"] == "C:/outside-repo/text_to_sql.p8"
    assert captured["private_key_file_pwd"] == "seeded-passphrase"
    assert "password" not in captured
    assert fake.statements == ["SELECT CURRENT_SECONDARY_ROLES()"]
    assert fake.closed


def test_service_connection_fails_closed_when_secondary_roles_are_active(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = load_settings(environ={}, env_file=EMPTY_ENV)
    identity = settings.identities.snowflake_services[0]
    config = settings.snowflake.model_copy(update={"account": "seeded-account"})
    fake = FakeConnection(rows=[(r'{"roles":"FORBIDDEN_ROLE","value":"ALL"}',)])
    monkeypatch.setattr(snowflake.connector, "connect", lambda **_kwargs: fake)

    with pytest.raises(SnowflakeProviderError, match="service connection failed"):
        SnowflakeClient.connect_service(
            config,
            identity,
            credential_values={identity.private_key_path_env: "C:/seeded/private.p8"},
        )
    assert fake.closed


def test_service_connection_missing_or_provider_failure_is_secret_safe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = load_settings(environ={}, env_file=EMPTY_ENV)
    identity = settings.identities.snowflake_services[0]
    config = settings.snowflake.model_copy(update={"account": "seeded-account"})

    with pytest.raises(ValueError, match=identity.private_key_path_env):
        SnowflakeClient.connect_service(config, identity, credential_values={})

    def fail_connect(**kwargs: Any) -> FakeConnection:
        raise RuntimeError(f"provider leaked kwargs: {kwargs}")

    monkeypatch.setattr(snowflake.connector, "connect", fail_connect)
    with pytest.raises(SnowflakeProviderError) as captured:
        SnowflakeClient.connect_service(
            config,
            identity,
            credential_values={
                identity.private_key_path_env: "C:/seeded/private.p8",
                identity.private_key_passphrase_env: "seeded-secret-passphrase",
            },
        )
    assert str(captured.value) == "Snowflake service connection failed"
    assert "seeded" not in str(captured.value)


def test_service_session_hardening_and_cleanup_failures_are_sanitized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = load_settings(environ={}, env_file=EMPTY_ENV)
    identity = settings.identities.snowflake_services[0]
    config = settings.snowflake.model_copy(update={"account": "seeded-account"})

    class CleanupFailure(FakeConnection):
        def close(self) -> None:
            raise RuntimeError("seeded cleanup leak")

    monkeypatch.setattr(
        snowflake.connector,
        "connect",
        lambda **_kwargs: CleanupFailure(fail=True),
    )
    with pytest.raises(SnowflakeProviderError) as captured:
        SnowflakeClient.connect_service(
            config,
            identity,
            credential_values={identity.private_key_path_env: "C:/seeded/private.p8"},
        )
    assert str(captured.value) == "Snowflake service connection failed"
    assert "seeded" not in str(captured.value)


def test_rotation_runbook_covers_all_provider_cutover_and_revocation_gates() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")
    for expected in (
        "ADD KEY PAIR REVIEWLENS_RUNTIME",
        "ROLE_RESTRICTION = 'INGEST_ROLE'",
        "DAYS_TO_EXPIRY = 90",
        "ROTATE KEY PAIR REVIEWLENS_RUNTIME",
        "EXPIRE_ROTATED_KEY_PAIR_AFTER_HOURS = 24",
        "REMOVE KEY PAIR REVIEWLENS_RUNTIME",
        "REVIEWLENS_RUN_LIVE_SNOWFLAKE_ROTATION",
        "ROTATE_REVIEWLENS_ANALYTICS_SVC_REVIEWLENS_ROTATION_SMOKE",
        "tests\\live\\test_snowflake_rotation_live.py",
        "không rotate hoặc sửa",
        "Object Read & Write",
        "Object Read Only",
        "R2_INGEST_",
        "R2_STAGE_",
        "OPENROUTER_API_KEY",
        "CHROMA_AUTH_TOKEN",
        "APP_AUTH_TOKEN",
        "old key fails",
        "Git\\usr\\bin\\openssl.exe",
        "New-Item -ItemType Directory",
        "Registration SQL copied to clipboard",
        "Create Account API token",
        "inspect_credential_readiness",
        "## 11. Lỗi thường gặp",
    ):
        assert expected in text
    for forbidden in ("sk-or-v1-", "AKIA", "R2_SECRET_ACCESS_KEY="):
        assert forbidden not in text
