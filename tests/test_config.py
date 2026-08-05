from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
from pydantic import ValidationError

from reviewlens.config import DataMode, Runtime, load_settings


def test_single_local_config_contract() -> None:
    settings = load_settings(environ={})
    assert settings.runtime is Runtime.LOCAL
    assert settings.r2.bucket == "reviewlens-data-dev"
    assert settings.snowflake.database == "REVIEWLENS"
    assert settings.chroma.persistence_path == "./chroma_data"


def test_config_toml_contains_no_secret_fields() -> None:
    with Path("config/config.toml").open("rb") as handle:
        payload = tomllib.load(handle)
    forbidden = {
        "account_id",
        "access_key_id",
        "secret_access_key",
        "account",
        "user",
        "private_key_path",
        "password",
        "api_key",
        "auth_token",
    }
    configured_keys = {
        field_name for value in payload.values() if isinstance(value, dict) for field_name in value
    }
    assert configured_keys.isdisjoint(forbidden)


def test_safe_summary_never_exposes_secrets() -> None:
    environment = {
        "R2_ACCOUNT_ID": "seeded-account-id",
        "R2_ACCESS_KEY_ID": "seeded-access-key",
        "R2_SECRET_ACCESS_KEY": "seeded-secret-key",
        "SNOWFLAKE_ACCOUNT": "seeded-snowflake-account",
        "SNOWFLAKE_USER": "synthetic_service_user",
        "SNOWFLAKE_PRIVATE_KEY_PATH": "seeded-private-key-path",
        "SNOWFLAKE_PASSWORD": "seeded-password",
        "OPENROUTER_API_KEY": "sk-or-v1-seeded-secret",
        "CHROMA_AUTH_TOKEN": "seeded-chroma-token",
        "APP_AUTH_TOKEN": "seeded-app-token",
    }
    text = str(load_settings(environ=environment).safe_summary())
    for secret in environment.values():
        assert secret not in text


def test_dotenv_credentials_are_loaded_and_process_values_win(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "OPENROUTER_API_KEY=from-dotenv\nAPP_AUTH_TOKEN=from-dotenv\n",
        encoding="utf-8",
    )
    settings = load_settings(
        environ={"OPENROUTER_API_KEY": "from-process"},
        env_file=env_file,
    )
    assert settings.openrouter.api_key is not None
    assert settings.openrouter.api_key.get_secret_value() == "from-process"
    assert settings.app.auth_token is not None
    assert settings.app.auth_token.get_secret_value() == "from-dotenv"


def test_olist_mode_supports_private_managed_data_platform(tmp_path: Path) -> None:
    profile = (
        Path("config/config.toml")
        .read_text(encoding="utf-8")
        .replace('data_mode = "synthetic"', 'data_mode = "olist"')
    )
    config_path = tmp_path / "config.toml"
    config_path.write_text(profile, encoding="utf-8")
    settings = load_settings(environ={}, config_path=config_path, env_file=tmp_path / ".env")
    assert settings.data_mode is DataMode.OLIST
    assert settings.r2.enabled
    assert settings.snowflake.enabled


def test_olist_license_contract_is_non_commercial_and_attributed() -> None:
    settings = load_settings(environ={})
    assert settings.data_mode is DataMode.SYNTHETIC
    assert settings.license.dataset == "brazilian-ecommerce"
    assert settings.license.provider == "Olist"
    assert settings.license.accessed_at.isoformat() == "2026-08-05"
    assert settings.license.license_id == "CC-BY-NC-SA-4.0"
    assert not settings.license.commercial_use_allowed
    assert settings.license.attribution_required
    assert settings.license.share_alike_required
    assert settings.openrouter.hard_budget_usd == 5.0


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ("commercial_use_allowed = false", "commercial_use_allowed = true", "non-commercial"),
        ('license_id = "CC-BY-NC-SA-4.0"', 'license_id = "MIT"', "CC BY-NC-SA 4.0"),
        ("attribution_required = true", "attribution_required = false", "attribution"),
    ],
)
def test_olist_license_rejects_weakened_obligations(
    tmp_path: Path, old: str, new: str, message: str
) -> None:
    profile = Path("config/config.toml").read_text(encoding="utf-8").replace(old, new)
    config_path = tmp_path / "config.toml"
    config_path.write_text(profile, encoding="utf-8")
    with pytest.raises(ValidationError, match=message):
        load_settings(environ={}, config_path=config_path, env_file=tmp_path / ".env")
