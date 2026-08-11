"""Fail-closed helpers for the owner-operated Snowflake rotation smoke."""

from __future__ import annotations

import hmac
import os
import re
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from reviewlens.config import AppSettings, ServiceName, SnowflakeServiceIdentityConfig

ROTATION_SMOKE_KEY_PAIR_NAME = "REVIEWLENS_ROTATION_SMOKE"
ROTATION_SMOKE_SERVICE = ServiceName.ANALYTICS
ROTATION_SMOKE_CONFIRMATION = "ROTATE_REVIEWLENS_ANALYTICS_SVC_REVIEWLENS_ROTATION_SMOKE"

_IDENTIFIER = re.compile(r"^[A-Z][A-Z0-9_]*$")
_PUBLIC_KEY_BODY = re.compile(r"^[A-Za-z0-9+/=]+$")


class RotationSafetyError(ValueError):
    """Raised before any live mutation when a rotation safety gate is not met."""


@dataclass(frozen=True)
class RotationSmokePlan:
    """The deliberately narrow, read-only service used for the M1 live smoke."""

    identity: SnowflakeServiceIdentityConfig
    key_pair_name: str = ROTATION_SMOKE_KEY_PAIR_NAME
    rotated_key_grace_hours: int = 0
    days_to_expiry: int = 1


@dataclass(frozen=True)
class EphemeralKeyPair:
    """A temporary private-key path and its public-key body."""

    private_key_path: Path
    public_key_body: str


def build_rotation_smoke_plan(settings: AppSettings) -> RotationSmokePlan:
    """Select the fixed read-only canary; never accept a mutable service target."""

    matches = [
        identity
        for identity in settings.identities.snowflake_services
        if identity.service is ROTATION_SMOKE_SERVICE
    ]
    if len(matches) != 1:
        raise RotationSafetyError("rotation smoke requires exactly one analytics identity")
    identity = matches[0]
    if identity.user != "REVIEWLENS_ANALYTICS_SVC" or identity.role != "ANALYST_ROLE":
        raise RotationSafetyError("rotation smoke canary must remain the read-only analytics user")
    return RotationSmokePlan(identity=identity)


def require_rotation_confirmation(value: str | None) -> None:
    """Require an exact, non-secret owner acknowledgement before live mutation."""

    if value is None or not hmac.compare_digest(value, ROTATION_SMOKE_CONFIRMATION):
        raise RotationSafetyError(
            "rotation smoke requires the exact REVIEWLENS_SNOWFLAKE_ROTATION_CONFIRM value"
        )


def generate_ephemeral_rsa_key_pair(directory: Path, *, stem: str) -> EphemeralKeyPair:
    """Generate an unencrypted short-lived key pair inside an isolated temp directory."""

    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", stem):
        raise RotationSafetyError("unsafe ephemeral key filename")
    directory.mkdir(parents=True, exist_ok=True)
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    private_key_path = directory / f"{stem}.p8"
    private_key_path.write_bytes(private_bytes)
    os.chmod(private_key_path, 0o600)

    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    public_key_body = "".join(
        line for line in public_pem.decode("ascii").splitlines() if not line.startswith("-----")
    )
    if not _PUBLIC_KEY_BODY.fullmatch(public_key_body):
        raise RotationSafetyError("generated public key has an unexpected format")
    return EphemeralKeyPair(
        private_key_path=private_key_path,
        public_key_body=public_key_body,
    )


def render_add_smoke_key_sql(plan: RotationSmokePlan, public_key_body: str) -> str:
    """Render the initial temporary key registration statement."""

    user, key_name, role = _plan_identifiers(plan)
    public_key = _public_key(public_key_body)
    return (
        f"ALTER USER IF EXISTS {user} ADD KEY PAIR {key_name} "
        f"PUBLIC_KEY = '{public_key}' ROLE_RESTRICTION = '{role}' "
        f"DAYS_TO_EXPIRY = {plan.days_to_expiry} "
        "COMMENT = 'ReviewLens M1 isolated rotation smoke; safe to remove'"
    )


def render_rotate_smoke_key_sql(plan: RotationSmokePlan, public_key_body: str) -> str:
    """Render an immediate old-key expiry for deterministic revocation evidence."""

    user, key_name, _role = _plan_identifiers(plan)
    public_key = _public_key(public_key_body)
    return (
        f"ALTER USER IF EXISTS {user} ROTATE KEY PAIR {key_name} "
        f"PUBLIC_KEY = '{public_key}' "
        f"EXPIRE_ROTATED_KEY_PAIR_AFTER_HOURS = {plan.rotated_key_grace_hours}"
    )


def render_remove_smoke_key_sql(plan: RotationSmokePlan) -> str:
    """Render cleanup for the active smoke key; runtime keys are never targeted."""

    user, key_name, _role = _plan_identifiers(plan)
    return f"ALTER USER IF EXISTS {user} REMOVE KEY PAIR {key_name}"


def render_show_key_pairs_sql(plan: RotationSmokePlan) -> str:
    """Render the metadata-only inspection used by preflight and evidence checks."""

    user, _key_name, _role = _plan_identifiers(plan)
    return f"SHOW USER KEY PAIRS FOR USER {user}"


def _plan_identifiers(plan: RotationSmokePlan) -> tuple[str, str, str]:
    if plan.rotated_key_grace_hours != 0:
        raise RotationSafetyError("rotation smoke must expire its old temporary key immediately")
    if plan.days_to_expiry != 1:
        raise RotationSafetyError("rotation smoke key must expire after one day")
    return (
        _identifier(plan.identity.user),
        _identifier(plan.key_pair_name),
        _identifier(plan.identity.role),
    )


def _identifier(value: str) -> str:
    normalized = value.upper()
    if not _IDENTIFIER.fullmatch(normalized):
        raise RotationSafetyError("unsafe Snowflake rotation identifier")
    return normalized


def _public_key(value: str) -> str:
    if not value or not _PUBLIC_KEY_BODY.fullmatch(value):
        raise RotationSafetyError("unsafe Snowflake public key body")
    return value
