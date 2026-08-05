"""Secret-safe readiness checks for dedicated ReviewLens service identities."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from reviewlens.config import AppSettings, ServiceName, load_environment_values


class CredentialReadiness(BaseModel):
    """Boolean-only identity status that is safe to print and persist as evidence."""

    model_config = ConfigDict(frozen=True)

    snowflake: dict[ServiceName, bool]
    r2_ingest: bool
    r2_stage: bool
    openrouter: bool
    chroma: bool
    app: bool

    @property
    def all_runtime_credentials_configured(self) -> bool:
        return all(self.snowflake.values()) and all(
            (self.r2_ingest, self.r2_stage, self.openrouter, self.chroma, self.app)
        )


def inspect_credential_readiness(
    settings: AppSettings,
    *,
    environ: Mapping[str, str] | None = None,
    env_file: Path | None = None,
) -> CredentialReadiness:
    """Return readiness booleans without retaining or returning credential values."""

    values = load_environment_values(environ=environ, env_file=env_file)
    has_snowflake_account = bool(settings.snowflake.account or values.get("SNOWFLAKE_ACCOUNT"))
    snowflake = {
        identity.service: bool(has_snowflake_account and values.get(identity.private_key_path_env))
        for identity in settings.identities.snowflake_services
    }
    has_r2_account = bool(settings.r2.account_id or values.get("R2_ACCOUNT_ID"))
    return CredentialReadiness(
        snowflake=snowflake,
        r2_ingest=bool(
            has_r2_account
            and values.get(settings.identities.r2_ingest_access_key_env)
            and values.get(settings.identities.r2_ingest_secret_key_env)
        ),
        r2_stage=bool(
            has_r2_account
            and values.get(settings.identities.r2_stage_access_key_env)
            and values.get(settings.identities.r2_stage_secret_key_env)
        ),
        openrouter=bool(
            settings.openrouter.api_key or values.get(settings.identities.openrouter_api_key_env)
        ),
        chroma=bool(
            settings.chroma.auth_token or values.get(settings.identities.chroma_auth_token_env)
        ),
        app=bool(settings.app.auth_token or values.get(settings.identities.app_auth_token_env)),
    )
