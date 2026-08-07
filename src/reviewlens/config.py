"""Typed, secret-safe configuration for the ReviewLens local demo."""

from __future__ import annotations

import argparse
import json
import os
import tomllib
from collections.abc import Mapping
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Any

from dotenv import dotenv_values
from pydantic import BaseModel, Field, SecretStr, model_validator


class Runtime(StrEnum):
    LOCAL = "local"


class DeploymentMode(StrEnum):
    LOCAL_DEMO = "local_demo"


class DataMode(StrEnum):
    SYNTHETIC = "synthetic"
    OLIST = "olist"


class ServiceName(StrEnum):
    INGESTION = "ingestion"
    TRANSFORM = "transform"
    AI_ENRICH = "ai_enrich"
    VECTOR_INDEX = "vector_index"
    GOLD_BUILD = "gold_build"
    ANALYTICS = "analytics"
    TEXT_TO_SQL = "text_to_sql"
    RAG = "rag"


EXPECTED_SNOWFLAKE_IDENTITIES: dict[ServiceName, tuple[str, str, str]] = {
    ServiceName.INGESTION: ("REVIEWLENS_INGEST_SVC", "INGEST_ROLE", "REVIEWLENS_WH"),
    ServiceName.TRANSFORM: (
        "REVIEWLENS_TRANSFORM_SVC",
        "TRANSFORMER_ROLE",
        "REVIEWLENS_WH",
    ),
    ServiceName.AI_ENRICH: (
        "REVIEWLENS_AI_ENRICH_SVC",
        "AI_ENRICH_ROLE",
        "REVIEWLENS_WH",
    ),
    ServiceName.VECTOR_INDEX: (
        "REVIEWLENS_VECTOR_INDEXER_SVC",
        "VECTOR_INDEXER_ROLE",
        "REVIEWLENS_WH",
    ),
    ServiceName.GOLD_BUILD: (
        "REVIEWLENS_GOLD_BUILDER_SVC",
        "GOLD_BUILDER_ROLE",
        "REVIEWLENS_WH",
    ),
    ServiceName.ANALYTICS: (
        "REVIEWLENS_ANALYTICS_SVC",
        "ANALYST_ROLE",
        "REVIEWLENS_WH",
    ),
    ServiceName.TEXT_TO_SQL: (
        "REVIEWLENS_TEXT_TO_SQL_SVC",
        "TEXT_TO_SQL_ROLE",
        "REVIEWLENS_SQL_WH",
    ),
    ServiceName.RAG: ("REVIEWLENS_RAG_SVC", "RAG_ROLE", "REVIEWLENS_WH"),
}


class LicenseConfig(BaseModel, frozen=True, extra="forbid"):
    dataset: str
    provider: str
    source_url: str
    accessed_at: date
    license_id: str
    license_url: str
    commercial_use_allowed: bool
    attribution_required: bool
    share_alike_required: bool
    status: str

    @model_validator(mode="after")
    def validate_olist_contract(self) -> LicenseConfig:
        if self.dataset != "brazilian-ecommerce" or self.provider != "Olist":
            raise ValueError("the active source contract must identify the Olist dataset")
        if self.license_id != "CC-BY-NC-SA-4.0":
            raise ValueError("Olist source data must use the CC BY-NC-SA 4.0 contract")
        if self.commercial_use_allowed:
            raise ValueError("the Olist dataset contract is non-commercial")
        if not self.attribution_required or not self.share_alike_required:
            raise ValueError("Olist attribution and ShareAlike obligations must remain enabled")
        if self.status != "active":
            raise ValueError("only an active license may be configured")
        return self


class R2Config(BaseModel, frozen=True, extra="forbid"):
    enabled: bool
    bucket: str
    location: str
    storage_class: str
    public_access: bool
    prefixes: tuple[str, ...]
    account_id: str | None = None
    access_key_id: SecretStr | None = None
    secret_access_key: SecretStr | None = None

    @property
    def endpoint(self) -> str | None:
        return f"https://{self.account_id}.r2.cloudflarestorage.com" if self.account_id else None

    def require_live_credentials(self) -> None:
        if not all((self.account_id, self.access_key_id, self.secret_access_key)):
            raise ValueError("R2 live access requires account ID and scoped credentials")


class SnowflakeConfig(BaseModel, frozen=True, extra="forbid"):
    enabled: bool
    cloud: str
    region: str
    edition: str
    database: str
    warehouse: str
    role: str
    warehouse_size: str
    auto_suspend_seconds: int = Field(ge=60)
    trial_expires_at: date
    account: str | None = None
    user: str | None = None
    private_key_path: str | None = None
    password: SecretStr | None = None

    def require_live_credentials(self) -> None:
        has_auth = bool(self.private_key_path or self.password)
        if not self.account or not self.user or not has_auth:
            raise ValueError(
                "Snowflake live access requires account, user and local authentication"
            )


class OpenRouterConfig(BaseModel, frozen=True, extra="forbid"):
    enabled: bool
    base_url: str
    hard_budget_usd: float = Field(gt=0, le=5.0)
    daily_warning_usd: float = Field(gt=0)
    enrichment_model: str
    rag_model: str
    sql_model: str
    embedding_model: str
    api_key: SecretStr | None = None

    @model_validator(mode="after")
    def validate_budget(self) -> OpenRouterConfig:
        if self.daily_warning_usd > self.hard_budget_usd:
            raise ValueError("daily warning cannot exceed project hard budget")
        return self

    def require_live_credentials(self) -> None:
        if self.api_key is None:
            raise ValueError("OpenRouter live access requires OPENROUTER_API_KEY")


class ChromaConfig(BaseModel, frozen=True, extra="forbid"):
    enabled: bool
    host: str
    port: int = Field(gt=0, lt=65536)
    persistence_path: str
    collection_prefix: str
    auth_token: SecretStr | None = None


class AppConfig(BaseModel, frozen=True, extra="forbid"):
    bind_host: str
    port: int = Field(gt=0, lt=65536)
    auth_required: bool
    auth_token: SecretStr | None = None


class SnowflakeServiceIdentityConfig(BaseModel, frozen=True, extra="forbid"):
    service: ServiceName
    user: str = Field(pattern=r"^REVIEWLENS_[A-Z0-9_]+_SVC$")
    role: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")
    warehouse: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")
    private_key_path_env: str = Field(pattern=r"^SNOWFLAKE_[A-Z0-9_]+_PRIVATE_KEY_PATH$")
    private_key_passphrase_env: str = Field(
        pattern=r"^SNOWFLAKE_[A-Z0-9_]+_PRIVATE_KEY_PASSPHRASE$"
    )


class IdentityConfig(BaseModel, frozen=True, extra="forbid"):
    snowflake_key_pair_name: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")
    credential_max_age_days: int = Field(gt=0, le=90)
    rotation_grace_hours: int = Field(ge=0, le=24)
    snowflake_services: tuple[SnowflakeServiceIdentityConfig, ...]
    r2_ingest_access_key_env: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")
    r2_ingest_secret_key_env: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")
    r2_stage_access_key_env: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")
    r2_stage_secret_key_env: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")
    openrouter_api_key_env: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")
    chroma_auth_token_env: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")
    app_auth_token_env: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")

    @model_validator(mode="after")
    def validate_service_boundaries(self) -> IdentityConfig:
        by_service = {identity.service: identity for identity in self.snowflake_services}
        if set(by_service) != set(ServiceName):
            raise ValueError("exactly one Snowflake identity is required for every service")
        users = [identity.user for identity in self.snowflake_services]
        path_envs = [identity.private_key_path_env for identity in self.snowflake_services]
        passphrase_envs = [
            identity.private_key_passphrase_env for identity in self.snowflake_services
        ]
        if len(users) != len(set(users)):
            raise ValueError("Snowflake service users must be unique")
        if len(path_envs) != len(set(path_envs)) or len(passphrase_envs) != len(
            set(passphrase_envs)
        ):
            raise ValueError("Snowflake service credential environment names must be unique")
        for service, expected in EXPECTED_SNOWFLAKE_IDENTITIES.items():
            actual = by_service[service]
            if (actual.user, actual.role, actual.warehouse) != expected:
                raise ValueError(f"invalid least-privilege identity mapping for {service.value}")
        r2_envs = {
            self.r2_ingest_access_key_env,
            self.r2_ingest_secret_key_env,
            self.r2_stage_access_key_env,
            self.r2_stage_secret_key_env,
        }
        if len(r2_envs) != 4:
            raise ValueError("R2 ingestion and Snowflake stage credentials must be distinct")
        return self


class AppSettings(BaseModel, frozen=True, extra="forbid"):
    runtime: Runtime
    deployment_mode: DeploymentMode
    data_mode: DataMode
    license: LicenseConfig
    r2: R2Config
    snowflake: SnowflakeConfig
    openrouter: OpenRouterConfig
    chroma: ChromaConfig
    app: AppConfig
    identities: IdentityConfig

    @model_validator(mode="after")
    def validate_security_boundaries(self) -> AppSettings:
        if self.r2.public_access:
            raise ValueError("R2 public access must remain disabled")
        if self.deployment_mode is DeploymentMode.LOCAL_DEMO and self.app.bind_host not in {
            "127.0.0.1",
            "localhost",
            "::1",
        }:
            raise ValueError("local demo must bind only to loopback")
        if not self.app.auth_required:
            raise ValueError("local demo requires application authentication")
        return self

    def safe_summary(self) -> dict[str, Any]:
        summary = self.model_dump(
            mode="json",
            exclude={
                "r2": {"account_id", "access_key_id", "secret_access_key"},
                "snowflake": {"account", "user", "private_key_path", "password"},
                "openrouter": {"api_key"},
                "chroma": {"auth_token"},
                "app": {"auth_token"},
            },
        )
        summary["r2"]["credentials_configured"] = bool(
            self.r2.access_key_id and self.r2.secret_access_key
        )
        summary["snowflake"]["credentials_configured"] = bool(
            self.snowflake.user and (self.snowflake.private_key_path or self.snowflake.password)
        )
        summary["openrouter"]["credentials_configured"] = self.openrouter.api_key is not None
        summary["chroma"]["token_configured"] = self.chroma.auth_token is not None
        summary["app"]["token_configured"] = self.app.auth_token is not None
        return summary


ENV_OVERRIDES: dict[str, tuple[str, str]] = {
    "R2_ACCOUNT_ID": ("r2", "account_id"),
    "R2_ACCESS_KEY_ID": ("r2", "access_key_id"),
    "R2_SECRET_ACCESS_KEY": ("r2", "secret_access_key"),
    "SNOWFLAKE_ACCOUNT": ("snowflake", "account"),
    "SNOWFLAKE_USER": ("snowflake", "user"),
    "SNOWFLAKE_PRIVATE_KEY_PATH": ("snowflake", "private_key_path"),
    "SNOWFLAKE_PASSWORD": ("snowflake", "password"),
    "OPENROUTER_API_KEY": ("openrouter", "api_key"),
    "CHROMA_AUTH_TOKEN": ("chroma", "auth_token"),
    "APP_AUTH_TOKEN": ("app", "auth_token"),
}


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_environment_values(
    *,
    environ: Mapping[str, str] | None = None,
    env_file: Path | None = None,
) -> dict[str, str]:
    """Load secret-bearing environment values; callers must never log the result."""

    selected_env_file = env_file or project_root() / ".env"
    file_values = {
        key: value
        for key, value in dotenv_values(selected_env_file).items()
        if isinstance(value, str)
    }
    process_values = os.environ if environ is None else environ
    return {**file_values, **process_values}


def load_settings(
    *,
    environ: Mapping[str, str] | None = None,
    config_path: Path | None = None,
    env_file: Path | None = None,
) -> AppSettings:
    """Load the one local config, with process variables overriding ``.env`` values."""

    root = project_root()
    selected_config = config_path or root / "config" / "config.toml"
    selected_env_file = env_file or root / ".env"
    source_env = load_environment_values(environ=environ, env_file=selected_env_file)
    with selected_config.open("rb") as handle:
        payload: dict[str, Any] = tomllib.load(handle)
    for env_name, (section, field_name) in ENV_OVERRIDES.items():
        value = source_env.get(env_name)
        if value:
            payload[section][field_name] = value
    return AppSettings.model_validate(payload)


def main() -> None:
    argparse.ArgumentParser(
        description="Validate and print the secret-safe ReviewLens local config"
    ).parse_args()
    settings = load_settings()
    print(json.dumps(settings.safe_summary(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
