from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest

from reviewlens.config import AppSettings, DataMode, ServiceName, load_settings
from reviewlens.providers.snowflake import SnowflakeClient, SnowflakeQueryResult
from reviewlens.warehouse.release_transition import (
    M3ReleaseTransitionError,
    M3ReleaseTransitionResult,
    ReleaseTransitionAction,
    run_m3_release_transition,
    validate_release_transition_settings,
)

TARGET_RELEASE_ID = "a" * 64


class FakeSnowflakeClient:
    def __init__(self, results: Sequence[Sequence[tuple[object, ...]]]) -> None:
        self._results = list(results)
        self.executed: list[str] = []
        self.suspended: list[str] = []
        self.closed = False

    def execute_with_results(self, statement: str, *, operation: str = "") -> SnowflakeQueryResult:
        self.executed.append(f"{operation}:{statement}")
        return SnowflakeQueryResult(query_id="safe-query-id", rows=tuple(self._results.pop(0)))

    def suspend_warehouse(self, warehouse: str) -> None:
        self.suspended.append(warehouse)

    def close(self) -> None:
        self.closed = True


def _settings(tmp_path: Path) -> AppSettings:
    return load_settings(env_file=tmp_path / "missing.env")


def _run(
    *,
    tmp_path: Path,
    action: ReleaseTransitionAction,
    response: object,
    expected_pointer_version: int,
) -> tuple[M3ReleaseTransitionResult, FakeSnowflakeClient, FakeSnowflakeClient]:
    service = FakeSnowflakeClient(
        (
            ((response,),),
            ((TARGET_RELEASE_ID, Decimal(expected_pointer_version + 1)),),
        )
    )
    bootstrap = FakeSnowflakeClient(())
    result = run_m3_release_transition(
        settings=_settings(tmp_path),
        credential_values={"SNOWFLAKE_GOLD_BUILDER_PRIVATE_KEY_PATH": "C:/safe/gold.p8"},
        action=action,
        target_release_id=TARGET_RELEASE_ID,
        expected_pointer_version=expected_pointer_version,
        connect_service=lambda settings, identity, credentials: cast(SnowflakeClient, service),
        connect_bootstrap=lambda settings: cast(SnowflakeClient, bootstrap),
    )
    return result, service, bootstrap


def test_activation_calls_only_guarded_procedure_and_verifies_pointer(tmp_path: Path) -> None:
    result, service, bootstrap = _run(
        tmp_path=tmp_path,
        action=ReleaseTransitionAction.ACTIVATE,
        response={"status": "ACTIVATED", "pointer_version": 1},
        expected_pointer_version=0,
    )

    sql = "\n".join(service.executed).upper()
    assert result.action is ReleaseTransitionAction.ACTIVATE
    assert result.pointer_version == 1
    assert result.replayed is False
    assert "SELECT REVIEWLENS.AUDIT.ACTIVATE_RELEASE_V1(0" in sql
    assert "ACTIVE_RELEASE_POINTER" in sql
    assert "UPDATE ACTIVE_RELEASE_POINTER" not in sql
    assert "ROLLBACK_RELEASE_V1" not in sql
    assert bootstrap.suspended == ["REVIEWLENS_WH"]
    assert service.closed and bootstrap.closed


def test_rollback_replay_is_safe_and_uses_explicit_compare_and_set_version(tmp_path: Path) -> None:
    result, service, bootstrap = _run(
        tmp_path=tmp_path,
        action=ReleaseTransitionAction.ROLLBACK,
        response='{"status": "REPLAY", "pointer_version": 3}',
        expected_pointer_version=2,
    )

    assert result.action is ReleaseTransitionAction.ROLLBACK
    assert result.pointer_version == 3
    assert result.replayed is True
    assert "ROLLBACK_RELEASE_V1(2" in service.executed[0]
    assert bootstrap.suspended == ["REVIEWLENS_WH"]


def test_transition_denial_is_sanitized_and_still_suspends(tmp_path: Path) -> None:
    service = FakeSnowflakeClient(((({"status": "CAS_DENIED", "pointer_version": 1},),),))
    bootstrap = FakeSnowflakeClient(())

    with pytest.raises(M3ReleaseTransitionError) as error:
        run_m3_release_transition(
            settings=_settings(tmp_path),
            credential_values={"SNOWFLAKE_GOLD_BUILDER_PRIVATE_KEY_PATH": "C:/safe/gold.p8"},
            action=ReleaseTransitionAction.ACTIVATE,
            target_release_id=TARGET_RELEASE_ID,
            expected_pointer_version=0,
            connect_service=lambda settings, identity, credentials: cast(SnowflakeClient, service),
            connect_bootstrap=lambda settings: cast(SnowflakeClient, bootstrap),
        )

    assert str(error.value) == M3ReleaseTransitionError.code
    assert bootstrap.suspended == ["REVIEWLENS_WH"]
    assert service.closed and bootstrap.closed


def test_transition_fails_closed_for_synthetic_mode(tmp_path: Path) -> None:
    settings = _settings(tmp_path).model_copy(update={"data_mode": DataMode.SYNTHETIC})

    with pytest.raises(M3ReleaseTransitionError):
        validate_release_transition_settings(settings)


def test_transition_uses_only_gold_builder_identity(tmp_path: Path) -> None:
    service = FakeSnowflakeClient(
        (
            (({"status": "ACTIVATED", "pointer_version": 1},),),
            ((TARGET_RELEASE_ID, 1),),
        )
    )
    bootstrap = FakeSnowflakeClient(())
    identities: list[ServiceName] = []

    def connector(
        unused_settings: Any, identity: Any, unused_credentials: Mapping[str, str]
    ) -> SnowflakeClient:
        del unused_settings, unused_credentials
        identities.append(identity.service)
        return cast(SnowflakeClient, service)

    run_m3_release_transition(
        settings=_settings(tmp_path),
        credential_values={"SNOWFLAKE_GOLD_BUILDER_PRIVATE_KEY_PATH": "C:/safe/gold.p8"},
        action=ReleaseTransitionAction.ACTIVATE,
        target_release_id=TARGET_RELEASE_ID,
        expected_pointer_version=0,
        connect_service=connector,
        connect_bootstrap=lambda settings: cast(SnowflakeClient, bootstrap),
    )

    assert identities == [ServiceName.GOLD_BUILD]
