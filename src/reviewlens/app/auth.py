"""Fail-closed local token authentication without retaining candidate tokens."""

from __future__ import annotations

import hashlib
import hmac
from enum import StrEnum

from pydantic import SecretStr

MAX_TOKEN_LENGTH = 512


class AuthDecision(StrEnum):
    """Public-safe result of one local authentication attempt."""

    GRANTED = "granted"
    DENIED = "denied"
    CONFIGURATION_ERROR = "configuration_error"


def _digest(value: str) -> bytes:
    return hashlib.sha256(value.encode("utf-8")).digest()


def verify_auth_token(candidate: str, configured_token: SecretStr | None) -> AuthDecision:
    """Compare fixed-length digests and return no token-bearing result."""

    if configured_token is None or not configured_token.get_secret_value():
        return AuthDecision.CONFIGURATION_ERROR
    if not candidate or len(candidate) > MAX_TOKEN_LENGTH:
        return AuthDecision.DENIED
    expected = configured_token.get_secret_value()
    return (
        AuthDecision.GRANTED
        if hmac.compare_digest(_digest(candidate), _digest(expected))
        else AuthDecision.DENIED
    )
