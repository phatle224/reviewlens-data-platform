from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

import pytest

from reviewlens.config import AppSettings, DataMode, ServiceName, load_settings
from reviewlens.providers.snowflake import SnowflakeClient, SnowflakeQueryResult
from reviewlens.warehouse.release_registration import (
    M3ReleaseRegistrationError,
    run_m3_release_registration,
    validate_release_registration_settings,
)
from reviewlens.warehouse.releases import build_release_definition_for_tested_target
from reviewlens.warehouse.replay_drill import build_approved_m3_replay_drill_plan


class FakeSnowflakeClient:
    def __init__(self, results: Sequence[Sequence[tuple[object, ...]]]) -> None:
        self._results = list(results)
        self.executed: list[str] = []
        self.suspended: list[str] = []
        self.closed = False

    def execute(self, statement: str, *, operation: str = "") -> None:
        self.executed.append(f"{operation}:{statement}")

    def execute_with_results(self, statement: str, *, operation: str = "") -> SnowflakeQueryResult:
        self.executed.append(f"{operation}:{statement}")
        return SnowflakeQueryResult(query_id="safe-query-id", rows=tuple(self._results.pop(0)))

    def suspend_warehouse(self, warehouse: str) -> None:
        self.suspended.append(warehouse)

    def close(self) -> None:
        self.closed = True


def _settings(tmp_path: Path) -> AppSettings:
    return load_settings(env_file=tmp_path / "missing.env")


def _expected_results() -> tuple[tuple[tuple[object, ...], ...], ...]:
    plan = build_approved_m3_replay_drill_plan()
    definition = build_release_definition_for_tested_target(plan.gold_target)
    candidate_rows = tuple(
        (
            definition.silver_candidate_id
            if item.layer.value == "SILVER"
            else definition.gold_candidate_id,
            item.layer.value,
            definition.silver_processing_run_id
            if item.layer.value == "SILVER"
            else definition.gold_processing_run_id,
            item.physical_ref.database,
            item.physical_ref.schema,
            item.physical_ref.object_name,
            "TEST_PASSED",
        )
        for item in definition.object_refs
    )
    header = (
        (
            definition.definition_sha256,
            definition.definition_version,
            definition.source_release_id,
            definition.ingestion_batch_id,
            definition.silver_processing_run_id,
            definition.gold_processing_run_id,
            definition.silver_candidate_id,
            definition.gold_candidate_id,
            definition.semantic_contract_version,
        ),
    )
    refs = tuple(
        (
            item.layer.value,
            item.logical_name,
            item.physical_ref.database,
            item.physical_ref.schema,
            item.physical_ref.object_name,
        )
        for item in definition.object_refs
    )
    return candidate_rows, header, refs


def test_registration_writes_only_verified_immutable_definition_and_never_mutates_pointer(
    tmp_path: Path,
) -> None:
    service = FakeSnowflakeClient(_expected_results())
    bootstrap = FakeSnowflakeClient(())

    result = run_m3_release_registration(
        settings=_settings(tmp_path),
        credential_values={"SNOWFLAKE_GOLD_BUILDER_PRIVATE_KEY_PATH": "C:/safe/gold.p8"},
        connect_service=lambda settings, identity, credentials: cast(SnowflakeClient, service),
        connect_bootstrap=lambda settings: cast(SnowflakeClient, bootstrap),
    )

    all_sql = "\n".join(service.executed).upper()
    assert result.object_ref_count == 28
    assert result.pointer_mutated is False
    assert all_sql.count("M3 IMMUTABLE RELEASE OBJECT-REFERENCE REGISTRATION") == 28
    assert all("WHERE NOT EXISTS" in statement for statement in service.executed[1:30])
    assert "ACTIVE_RELEASE_POINTER" not in all_sql
    assert "ACTIVATE_RELEASE" not in all_sql
    assert "ROLLBACK_RELEASE" not in all_sql
    assert bootstrap.suspended == ["REVIEWLENS_WH"]
    assert service.closed and bootstrap.closed


def test_registration_rejects_incomplete_tested_pair_without_writing(tmp_path: Path) -> None:
    candidate_rows, _, _ = _expected_results()
    service = FakeSnowflakeClient((candidate_rows[:-1],))
    bootstrap = FakeSnowflakeClient(())

    with pytest.raises(M3ReleaseRegistrationError) as error:
        run_m3_release_registration(
            settings=_settings(tmp_path),
            credential_values={"SNOWFLAKE_GOLD_BUILDER_PRIVATE_KEY_PATH": "C:/safe/gold.p8"},
            connect_service=lambda settings, identity, credentials: cast(SnowflakeClient, service),
            connect_bootstrap=lambda settings: cast(SnowflakeClient, bootstrap),
        )

    assert str(error.value) == M3ReleaseRegistrationError.code
    assert len(service.executed) == 1
    assert bootstrap.suspended == ["REVIEWLENS_WH"]
    assert service.closed and bootstrap.closed


def test_registration_settings_fail_closed_for_synthetic_mode(tmp_path: Path) -> None:
    settings = _settings(tmp_path).model_copy(update={"data_mode": DataMode.SYNTHETIC})

    with pytest.raises(M3ReleaseRegistrationError) as error:
        validate_release_registration_settings(settings)

    assert str(error.value) == M3ReleaseRegistrationError.code


def test_registration_uses_only_gold_builder_identity(tmp_path: Path) -> None:
    service = FakeSnowflakeClient(_expected_results())
    bootstrap = FakeSnowflakeClient(())
    identities: list[ServiceName] = []

    def connector(
        unused_settings: Any, identity: Any, unused_credentials: Mapping[str, str]
    ) -> SnowflakeClient:
        del unused_settings, unused_credentials
        identities.append(identity.service)
        return cast(SnowflakeClient, service)

    run_m3_release_registration(
        settings=_settings(tmp_path),
        credential_values={"SNOWFLAKE_GOLD_BUILDER_PRIVATE_KEY_PATH": "C:/safe/gold.p8"},
        connect_service=connector,
        connect_bootstrap=lambda settings: cast(SnowflakeClient, bootstrap),
    )

    assert identities == [ServiceName.GOLD_BUILD]
