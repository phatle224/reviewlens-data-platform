from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest

from reviewlens.config import AppSettings, DataMode, ServiceName, load_settings
from reviewlens.providers.snowflake import SnowflakeClient, SnowflakeQueryResult
from reviewlens.warehouse.live_drill import (
    M3LiveDrillError,
    build_m3_live_drill_commands,
    run_live_m3_drill,
    validate_live_drill_settings,
)
from reviewlens.warehouse.releases import SILVER_RELEASE_LOGICAL_NAMES
from reviewlens.warehouse.replay_drill import (
    build_approved_m3_replay_drill_plan,
    build_approved_m3_rollback_proof_plan,
)


class FakeSnowflakeClient:
    def __init__(self, fingerprint_rows: tuple[tuple[object, ...], ...] = ()) -> None:
        self.executed: list[str] = []
        self.executed_all: list[tuple[str, ...]] = []
        self.suspended: list[str] = []
        self.closed = False
        self._fingerprint_rows = fingerprint_rows

    def execute(self, statement: str, *, operation: str = "") -> None:
        self.executed.append(f"{operation}:{statement}")

    def execute_all(self, statements: Sequence[str], *, operation: str = "") -> None:
        self.executed_all.append(tuple(statements))

    def execute_with_results(self, statement: str, *, operation: str = "") -> SnowflakeQueryResult:
        self.executed.append(f"{operation}:{statement}")
        return SnowflakeQueryResult(query_id="safe-query-id", rows=self._fingerprint_rows)

    def suspend_warehouse(self, warehouse: str) -> None:
        self.suspended.append(warehouse)

    def close(self) -> None:
        self.closed = True


def _settings(tmp_path: Path) -> AppSettings:
    return load_settings(env_file=tmp_path / "missing.env")


def _fingerprint_rows() -> tuple[tuple[object, ...], ...]:
    plan = build_approved_m3_replay_drill_plan()
    rows: list[tuple[object, ...]] = []
    for layer, names in (
        ("SILVER", sorted(SILVER_RELEASE_LOGICAL_NAMES)),
        ("GOLD", plan.gold_target_output_names),
    ):
        for logical_name in names:
            rows.append(
                (
                    layer,
                    logical_name,
                    Decimal(len(logical_name)),
                    hashlib.sha256(f"{layer}:{logical_name}".encode()).hexdigest(),
                )
            )
    return tuple(rows)


def test_live_settings_fail_closed_when_data_mode_is_not_olist(tmp_path: Path) -> None:
    settings = _settings(tmp_path).model_copy(update={"data_mode": DataMode.SYNTHETIC})

    with pytest.raises(M3LiveDrillError) as error:
        validate_live_drill_settings(settings)

    assert str(error.value) == M3LiveDrillError.code


def test_live_drill_replays_same_pair_records_lineage_and_always_suspends(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    plan = build_approved_m3_rollback_proof_plan()
    rows = _fingerprint_rows()
    transform = FakeSnowflakeClient()
    gold = FakeSnowflakeClient(rows)
    bootstrap = FakeSnowflakeClient()
    commands: list[tuple[str, ...]] = []

    def runner(argv: Sequence[str], environment: Mapping[str, str]) -> int:
        commands.append(tuple(argv))
        assert environment["DBT_SNOWFLAKE_QUERY_TAG"].startswith("reviewlens:m3:")
        assert "DBT_SNOWFLAKE_PRIVATE_KEY_PATH" in environment
        return 0

    def service_connector(
        unused_settings: Any, identity: Any, unused_credentials: Mapping[str, str]
    ) -> SnowflakeClient:
        del unused_settings, unused_credentials
        client = transform if identity.service is ServiceName.TRANSFORM else gold
        return cast(SnowflakeClient, client)

    def bootstrap_connector(unused_settings: Any) -> SnowflakeClient:
        del unused_settings
        return cast(SnowflakeClient, bootstrap)

    credentials = {
        "SNOWFLAKE_TRANSFORM_PRIVATE_KEY_PATH": "C:/safe/transform.p8",
        "SNOWFLAKE_GOLD_BUILDER_PRIVATE_KEY_PATH": "C:/safe/gold.p8",
    }
    result = run_live_m3_drill(
        settings=settings,
        credential_values=credentials,
        command_runner=runner,
        connect_service=service_connector,
        connect_bootstrap=bootstrap_connector,
        plan=plan,
    )

    assert result.equivalent is True
    assert result.fingerprint_query_count == 2
    assert result.silver_candidate_id == plan.silver_candidate.candidate_id
    assert result.gold_candidate_id == plan.gold_target.gold_candidate.candidate_id
    assert len(commands) == 8
    assert commands[0][1:3] == ("test", "--project-dir")
    assert commands[1][1:4] == ("source", "freshness", "--project-dir")
    assert sum("M3 processing lineage" in statement for statement in transform.executed) == 2
    assert sum("M3 processing lineage" in statement for statement in gold.executed) == 2
    assert len(transform.executed_all) == 2
    assert all(len(grants) == 10 for grants in transform.executed_all)
    assert bootstrap.suspended == ["REVIEWLENS_WH"]
    assert transform.closed and gold.closed and bootstrap.closed


def test_live_drill_failure_still_suspends_and_never_reaches_gold(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    transform = FakeSnowflakeClient()
    gold = FakeSnowflakeClient(_fingerprint_rows())
    bootstrap = FakeSnowflakeClient()

    attempts = 0

    def failing_runner(argv: Sequence[str], environment: Mapping[str, str]) -> int:
        nonlocal attempts
        del argv, environment
        attempts += 1
        return 1 if attempts == 3 else 0

    def service_connector(
        unused_settings: Any, identity: Any, unused_credentials: Mapping[str, str]
    ) -> SnowflakeClient:
        del unused_settings, unused_credentials
        return cast(
            SnowflakeClient,
            transform if identity.service is ServiceName.TRANSFORM else gold,
        )

    with pytest.raises(M3LiveDrillError) as error:
        run_live_m3_drill(
            settings=settings,
            credential_values={
                "SNOWFLAKE_TRANSFORM_PRIVATE_KEY_PATH": "C:/safe/transform.p8",
                "SNOWFLAKE_GOLD_BUILDER_PRIVATE_KEY_PATH": "C:/safe/gold.p8",
            },
            command_runner=failing_runner,
            connect_service=service_connector,
            connect_bootstrap=lambda unused_settings: cast(SnowflakeClient, bootstrap),
        )

    assert str(error.value) == M3LiveDrillError.code
    assert gold.executed == []
    assert any("'FAILED'" in statement for statement in transform.executed)
    assert bootstrap.suspended == ["REVIEWLENS_WH"]


def test_live_command_inventory_exposes_only_planned_silver_and_gold_builds() -> None:
    commands = build_m3_live_drill_commands(build_approved_m3_replay_drill_plan())

    assert [command.selector for command in commands] == [
        "m3_silver_candidate",
        "m3_gold_candidate",
    ]
