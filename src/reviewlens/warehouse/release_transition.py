"""Guarded, opt-in client for one M3 release activation or rollback procedure call."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from decimal import Decimal
from enum import StrEnum

from reviewlens.config import (
    AppSettings,
    DataMode,
    ServiceName,
    SnowflakeServiceIdentityConfig,
    load_environment_values,
    load_settings,
)
from reviewlens.providers.snowflake import SnowflakeClient

_HASH = re.compile(r"^[0-9a-f]{64}$")
_GOLD_SERVICE = ServiceName.GOLD_BUILD


class M3ReleaseTransitionError(RuntimeError):
    """Sanitized failure for a guarded release-pointer transition."""

    code = "M3_RELEASE_TRANSITION_FAILED"

    def __init__(self) -> None:
        super().__init__(self.code)


class ReleaseTransitionAction(StrEnum):
    """The only two owner-procedure transitions exposed to the local runtime."""

    ACTIVATE = "activate"
    ROLLBACK = "rollback"

    @property
    def procedure_name(self) -> str:
        if self is ReleaseTransitionAction.ACTIVATE:
            return "ACTIVATE_RELEASE_V1"
        return "ROLLBACK_RELEASE_V1"

    @property
    def accepted_statuses(self) -> frozenset[str]:
        if self is ReleaseTransitionAction.ACTIVATE:
            return frozenset({"ACTIVATED", "REPLAY"})
        return frozenset({"ROLLED_BACK", "REPLAY"})


@dataclass(frozen=True, slots=True)
class M3ReleaseTransitionResult:
    """Safe procedure outcome, intentionally excluding physical release refs."""

    action: ReleaseTransitionAction
    release_id: str
    pointer_version: int
    replayed: bool


def validate_release_transition_settings(settings: AppSettings) -> None:
    """Reject unsafe runtime settings before any provider call."""

    if (
        settings.data_mode is not DataMode.OLIST
        or not settings.snowflake.enabled
        or settings.snowflake.warehouse != "REVIEWLENS_WH"
        or settings.snowflake.warehouse_size != "X-SMALL"
        or settings.snowflake.auto_suspend_seconds != 60
    ):
        raise M3ReleaseTransitionError()
    _gold_identity(settings)


def run_m3_release_transition(
    *,
    settings: AppSettings,
    credential_values: Mapping[str, str],
    action: ReleaseTransitionAction,
    target_release_id: str,
    expected_pointer_version: int,
    connect_service: Callable[
        [AppSettings, SnowflakeServiceIdentityConfig, Mapping[str, str]], SnowflakeClient
    ],
    connect_bootstrap: Callable[[AppSettings], SnowflakeClient],
) -> M3ReleaseTransitionResult:
    """Call exactly one guarded server procedure and verify its resulting pointer.

    The caller must provide the expected pointer version explicitly; it is never
    fetched-and-reused client-side. This preserves the procedure's compare-and-set
    semantics under concurrent requests. A denied/stale response remains a failure
    and cannot silently retry with a newer version.
    """

    validate_release_transition_settings(settings)
    if (
        not isinstance(action, ReleaseTransitionAction)
        or _HASH.fullmatch(target_release_id) is None
        or type(expected_pointer_version) is not int
        or expected_pointer_version < 0
    ):
        raise M3ReleaseTransitionError()

    client: SnowflakeClient | None = None
    bootstrap: SnowflakeClient | None = None
    try:
        client = connect_service(settings, _gold_identity(settings), credential_values)
        response = client.execute_with_results(
            _procedure_call_sql(action, target_release_id, expected_pointer_version),
            operation="M3 guarded release transition",
        )
        pointer_version, replayed = _parse_procedure_response(response.rows, action)
        if pointer_version != expected_pointer_version + 1:
            raise M3ReleaseTransitionError()
        _assert_active_pointer(client, target_release_id, pointer_version)
        return M3ReleaseTransitionResult(
            action=action,
            release_id=target_release_id,
            pointer_version=pointer_version,
            replayed=replayed,
        )
    except (M3ReleaseTransitionError, RuntimeError, ValueError, TypeError):
        raise M3ReleaseTransitionError() from None
    finally:
        try:
            bootstrap = connect_bootstrap(settings)
            bootstrap.suspend_warehouse(settings.snowflake.warehouse)
        except (RuntimeError, ValueError):
            pass
        finally:
            if bootstrap is not None:
                bootstrap.close()
            if client is not None:
                client.close()


def _gold_identity(settings: AppSettings) -> SnowflakeServiceIdentityConfig:
    for identity in settings.identities.snowflake_services:
        if identity.service is _GOLD_SERVICE:
            return identity
    raise M3ReleaseTransitionError()


def _procedure_call_sql(
    action: ReleaseTransitionAction,
    target_release_id: str,
    expected_pointer_version: int,
) -> str:
    event_id = _transition_event_id(action, target_release_id, expected_pointer_version)
    return (
        f"SELECT REVIEWLENS.AUDIT.{action.procedure_name}("
        f"{expected_pointer_version}, '{target_release_id}', '{event_id}', 'release-owner')"
    )


def _parse_procedure_response(
    rows: Sequence[Sequence[object]], action: ReleaseTransitionAction
) -> tuple[int, bool]:
    if len(rows) != 1 or len(rows[0]) != 1:
        raise M3ReleaseTransitionError()
    value = rows[0][0]
    if isinstance(value, str):
        try:
            payload = json.loads(value)
        except json.JSONDecodeError as error:
            raise M3ReleaseTransitionError() from error
    elif isinstance(value, Mapping):
        payload = dict(value)
    else:
        raise M3ReleaseTransitionError()
    status = payload.get("status")
    pointer_version = _pointer_version(payload.get("pointer_version"))
    if not isinstance(status, str) or status not in action.accepted_statuses:
        raise M3ReleaseTransitionError()
    return pointer_version, status == "REPLAY"


def _assert_active_pointer(
    client: SnowflakeClient,
    target_release_id: str,
    pointer_version: int,
) -> None:
    result = client.execute_with_results(
        "SELECT RELEASE_ID, POINTER_VERSION "
        "FROM REVIEWLENS.AUDIT.ACTIVE_RELEASE_POINTER "
        "WHERE POINTER_NAME = 'ACTIVE_DATA_RELEASE'",
        operation="M3 release-pointer verification",
    )
    if len(result.rows) != 1 or len(result.rows[0]) != 2:
        raise M3ReleaseTransitionError()
    release_id, version = result.rows[0]
    if str(release_id) != target_release_id or _pointer_version(version) != pointer_version:
        raise M3ReleaseTransitionError()


def _pointer_version(value: object) -> int:
    if isinstance(value, bool):
        raise M3ReleaseTransitionError()
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, Decimal) and value == value.to_integral_value():
        parsed = int(value)
    else:
        raise M3ReleaseTransitionError()
    if parsed < 1:
        raise M3ReleaseTransitionError()
    return parsed


def _transition_event_id(
    action: ReleaseTransitionAction,
    target_release_id: str,
    expected_pointer_version: int,
) -> str:
    return hashlib.sha256(
        f"m3-release-transition-v1:{action.value}:{target_release_id}:{expected_pointer_version}".encode(
            "ascii"
        )
    ).hexdigest()


def _service_connector(
    settings: AppSettings,
    identity: SnowflakeServiceIdentityConfig,
    credential_values: Mapping[str, str],
) -> SnowflakeClient:
    return SnowflakeClient.connect_service(
        settings.snowflake,
        identity,
        credential_values=credential_values,
    )


def _bootstrap_connector(settings: AppSettings) -> SnowflakeClient:
    return SnowflakeClient.connect_bootstrap(settings.snowflake)


def main(argv: Sequence[str] | None = None) -> None:
    """Run only after an explicit process-local pointer-mutation confirmation."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="call one guarded release procedure")
    parser.add_argument(
        "--action", choices=tuple(action.value for action in ReleaseTransitionAction)
    )
    parser.add_argument("--target-release-id")
    parser.add_argument("--expected-pointer-version", type=int)
    arguments = parser.parse_args(argv)
    if not arguments.execute or os.environ.get("REVIEWLENS_TRANSITION_M3_RELEASE") != "CONFIRMED":
        parser.error("--execute plus REVIEWLENS_TRANSITION_M3_RELEASE=CONFIRMED are required")
    if (
        arguments.action is None
        or arguments.target_release_id is None
        or arguments.expected_pointer_version is None
    ):
        parser.error("--action, --target-release-id and --expected-pointer-version are required")
    result = run_m3_release_transition(
        settings=load_settings(),
        credential_values=load_environment_values(),
        action=ReleaseTransitionAction(arguments.action),
        target_release_id=arguments.target_release_id,
        expected_pointer_version=arguments.expected_pointer_version,
        connect_service=_service_connector,
        connect_bootstrap=_bootstrap_connector,
    )
    print(json.dumps(asdict(result), sort_keys=True))
