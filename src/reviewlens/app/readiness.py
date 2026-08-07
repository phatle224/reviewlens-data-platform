"""Provider-free application readiness derived from boolean credential signals."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from reviewlens.config import AppSettings
from reviewlens.security.credentials import CredentialReadiness, inspect_credential_readiness


class ReadinessState(StrEnum):
    READY = "ready"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class ReadinessCheck:
    name: str
    configured: bool
    detail: str


@dataclass(frozen=True, slots=True)
class ReadinessReport:
    state: ReadinessState
    checks: tuple[ReadinessCheck, ...]
    data_mode: str
    provider_calls_performed: bool = False

    def public_payload(self) -> dict[str, object]:
        """Return a boolean-only payload suitable for UI, logs, and tests."""

        return {
            "state": self.state.value,
            "data_mode": self.data_mode,
            "provider_calls_performed": self.provider_calls_performed,
            "checks": {
                check.name: {"configured": check.configured, "detail": check.detail}
                for check in self.checks
            },
        }


class CredentialInspector(Protocol):
    def __call__(
        self,
        settings: AppSettings,
        *,
        environ: Mapping[str, str] | None = None,
        env_file: Path | None = None,
    ) -> CredentialReadiness: ...


def _report_from_credentials(
    settings: AppSettings,
    credentials: CredentialReadiness,
) -> ReadinessReport:
    checks = (
        ReadinessCheck("local_auth", credentials.app, "Required local token is configured."),
        ReadinessCheck(
            "snowflake_services",
            all(credentials.snowflake.values()),
            "All eight least-privilege service key paths are configured.",
        ),
        ReadinessCheck(
            "r2_ingestion",
            credentials.r2_ingest,
            "Bucket-scoped ingestion identity is configured.",
        ),
        ReadinessCheck(
            "r2_stage",
            credentials.r2_stage,
            "Read-only Snowflake stage identity is configured.",
        ),
        ReadinessCheck(
            "openrouter",
            credentials.openrouter,
            "OpenRouter project credential is configured.",
        ),
        ReadinessCheck(
            "chroma",
            credentials.chroma,
            "Local Chroma authentication token is configured.",
        ),
    )
    state = (
        ReadinessState.READY
        if all(check.configured for check in checks)
        else ReadinessState.DEGRADED
    )
    return ReadinessReport(state=state, checks=checks, data_mode=settings.data_mode.value)


def collect_readiness(
    settings: AppSettings,
    *,
    environ: Mapping[str, str] | None = None,
    env_file: Path | None = None,
    inspector: CredentialInspector = inspect_credential_readiness,
) -> ReadinessReport:
    """Collect safe configuration readiness without connecting to any provider."""

    try:
        credentials = inspector(settings, environ=environ, env_file=env_file)
    except Exception:
        return ReadinessReport(
            state=ReadinessState.UNAVAILABLE,
            checks=(
                ReadinessCheck(
                    "credential_readiness",
                    False,
                    "Credential readiness could not be evaluated.",
                ),
            ),
            data_mode=settings.data_mode.value,
        )
    return _report_from_credentials(settings, credentials)
