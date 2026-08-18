"""Fail-closed local executor for the private M3 candidate-pair replay drill."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Protocol

from reviewlens.config import (
    AppSettings,
    DataMode,
    ServiceName,
    SnowflakeServiceIdentityConfig,
    load_environment_values,
    load_settings,
)
from reviewlens.providers.snowflake import SnowflakeClient
from reviewlens.warehouse.candidates import (
    CandidateLayer,
    PhysicalRelationRef,
    ProcessingRunDefinition,
)
from reviewlens.warehouse.equivalence import (
    CandidateBuildMode,
    CandidateEquivalenceSnapshot,
    EquivalenceReport,
    compare_full_refresh_to_deterministic_replay,
)
from reviewlens.warehouse.replay_drill import (
    DbtBuildPlan,
    M3ReplayDrillPlan,
    build_approved_m3_replay_drill_plan,
    snapshot_from_fingerprint_rows,
)


class M3LiveDrillError(RuntimeError):
    """Sanitized error for an operator-visible live-drill failure."""

    code = "M3_LIVE_DRILL_FAILED"

    def __init__(self) -> None:
        super().__init__(self.code)


class DrillObservation(StrEnum):
    FULL_REFRESH = "full_refresh"
    DETERMINISTIC_REPLAY = "deterministic_replay"

    @property
    def build_mode(self) -> CandidateBuildMode:
        if self is DrillObservation.FULL_REFRESH:
            return CandidateBuildMode.FULL_REFRESH
        return CandidateBuildMode.DETERMINISTIC_REPLAY


class CommandRunner(Protocol):
    """Minimal subprocess boundary that deliberately does not return command output."""

    def __call__(self, argv: Sequence[str], environment: Mapping[str, str]) -> int: ...


@dataclass(frozen=True, slots=True)
class M3LiveDrillResult:
    """Aggregate-only result that is safe to put in a local operator log."""

    equivalent: bool
    fingerprint_query_count: int
    silver_candidate_id: str
    gold_candidate_id: str


def validate_live_drill_settings(settings: AppSettings) -> None:
    """Reject unsafe runtime mode before any dbt process or provider connection."""

    if (
        settings.data_mode is not DataMode.OLIST
        or not settings.snowflake.enabled
        or settings.snowflake.warehouse != "REVIEWLENS_WH"
        or settings.snowflake.warehouse_size != "X-SMALL"
        or settings.snowflake.auto_suspend_seconds != 60
    ):
        raise M3LiveDrillError()
    for service in (ServiceName.TRANSFORM, ServiceName.GOLD_BUILD):
        _identity_for(settings, service)


def build_m3_live_drill_commands(plan: M3ReplayDrillPlan) -> tuple[DbtBuildPlan, ...]:
    """Return the only dbt commands used in each replay observation."""

    if not isinstance(plan, M3ReplayDrillPlan):
        raise M3LiveDrillError()
    return (plan.silver_build, plan.gold_build)


def run_live_m3_drill(
    *,
    settings: AppSettings,
    credential_values: Mapping[str, str],
    command_runner: CommandRunner,
    connect_service: Callable[
        [AppSettings, SnowflakeServiceIdentityConfig, Mapping[str, str]], SnowflakeClient
    ],
    connect_bootstrap: Callable[[AppSettings], SnowflakeClient],
) -> M3LiveDrillResult:
    """Build/replay one immutable pair, record aggregate evidence and always suspend.

    The function never reads source rows, never changes the active pointer and returns
    only the equivalence decision plus candidate identities.  It is dependency-injected
    so every branch can be proven with fakes before an opt-in managed-provider run.
    """

    validate_live_drill_settings(settings)
    plan = build_approved_m3_replay_drill_plan()
    transform: SnowflakeClient | None = None
    gold: SnowflakeClient | None = None
    bootstrap: SnowflakeClient | None = None
    snapshots: list[CandidateEquivalenceSnapshot] = []
    try:
        transform = _connect_service(
            settings, ServiceName.TRANSFORM, credential_values, connect_service
        )
        gold = _connect_service(
            settings, ServiceName.GOLD_BUILD, credential_values, connect_service
        )
        _run_bronze_preflight(
            command_runner=command_runner,
            settings=settings,
            credential_values=credential_values,
        )
        for observation in DrillObservation:
            _record_processing_lineage(transform, plan.silver_run, observation)
            _record_candidate_state(
                transform,
                plan.silver_run,
                plan.silver_candidate.candidate_id,
                CandidateLayer.SILVER,
                tuple(plan.silver_candidate.relation(name) for name in _silver_names(plan)),
                "BUILDING",
                observation,
            )
            try:
                _run_dbt(
                    command_runner,
                    plan.silver_build,
                    _dbt_environment(
                        settings, credential_values, ServiceName.TRANSFORM, observation, "silver"
                    ),
                )
                _run_argv(
                    command_runner,
                    _critical_gate_argv(plan),
                    _dbt_environment(
                        settings,
                        credential_values,
                        ServiceName.TRANSFORM,
                        observation,
                        "silver-critical",
                    ),
                )
            except M3LiveDrillError:
                _record_candidate_state(
                    transform,
                    plan.silver_run,
                    plan.silver_candidate.candidate_id,
                    CandidateLayer.SILVER,
                    tuple(plan.silver_candidate.relation(name) for name in _silver_names(plan)),
                    "FAILED",
                    observation,
                )
                raise
            _record_candidate_state(
                transform,
                plan.silver_run,
                plan.silver_candidate.candidate_id,
                CandidateLayer.SILVER,
                tuple(plan.silver_candidate.relation(name) for name in _silver_names(plan)),
                "TEST_PASSED",
                observation,
            )
            transform.execute_all(plan.gold_read_grants, operation="M3 exact Silver-to-Gold grant")

            _record_processing_lineage(gold, plan.gold_target.gold_run, observation)
            _record_candidate_state(
                gold,
                plan.gold_target.gold_run,
                plan.gold_target.gold_candidate.candidate_id,
                CandidateLayer.GOLD,
                plan.gold_target.output_relations,
                "BUILDING",
                observation,
            )
            try:
                _run_dbt(
                    command_runner,
                    plan.gold_build,
                    _dbt_environment(
                        settings, credential_values, ServiceName.GOLD_BUILD, observation, "gold"
                    ),
                )
            except M3LiveDrillError:
                _record_candidate_state(
                    gold,
                    plan.gold_target.gold_run,
                    plan.gold_target.gold_candidate.candidate_id,
                    CandidateLayer.GOLD,
                    plan.gold_target.output_relations,
                    "FAILED",
                    observation,
                )
                raise
            _record_candidate_state(
                gold,
                plan.gold_target.gold_run,
                plan.gold_target.gold_candidate.candidate_id,
                CandidateLayer.GOLD,
                plan.gold_target.output_relations,
                "TEST_PASSED",
                observation,
            )
            fingerprint = gold.execute_with_results(
                plan.fingerprint_sql,
                operation="M3 aggregate-only candidate-pair fingerprint",
            )
            snapshots.append(
                snapshot_from_fingerprint_rows(
                    plan=plan,
                    mode=observation.build_mode,
                    rows=fingerprint.rows,
                )
            )
        report = compare_full_refresh_to_deterministic_replay(
            full_refresh=snapshots[0], replay=snapshots[1]
        )
        if not report.equivalent:
            _record_candidate_state(
                transform,
                plan.silver_run,
                plan.silver_candidate.candidate_id,
                CandidateLayer.SILVER,
                tuple(plan.silver_candidate.relation(name) for name in _silver_names(plan)),
                "FAILED",
                DrillObservation.DETERMINISTIC_REPLAY,
            )
            _record_candidate_state(
                gold,
                plan.gold_target.gold_run,
                plan.gold_target.gold_candidate.candidate_id,
                CandidateLayer.GOLD,
                plan.gold_target.output_relations,
                "FAILED",
                DrillObservation.DETERMINISTIC_REPLAY,
            )
            raise M3LiveDrillError()
        return _safe_result(plan, report)
    except (M3LiveDrillError, ValueError, RuntimeError, subprocess.SubprocessError):
        raise M3LiveDrillError() from None
    finally:
        try:
            bootstrap = connect_bootstrap(settings)
            bootstrap.suspend_warehouse(settings.snowflake.warehouse)
        except (ValueError, RuntimeError):
            pass
        finally:
            if bootstrap is not None:
                bootstrap.close()
            if transform is not None:
                transform.close()
            if gold is not None:
                gold.close()


def _run_bronze_preflight(
    *,
    command_runner: CommandRunner,
    settings: AppSettings,
    credential_values: Mapping[str, str],
) -> None:
    environment = _dbt_environment(
        settings, credential_values, ServiceName.TRANSFORM, DrillObservation.FULL_REFRESH, "bronze"
    )
    for argv in (
        (
            "dbt",
            "test",
            "--project-dir",
            "dbt",
            "--profiles-dir",
            "dbt",
            "--selector",
            "m3_bronze_contract",
            "--no-partial-parse",
        ),
        (
            "dbt",
            "source",
            "freshness",
            "--project-dir",
            "dbt",
            "--profiles-dir",
            "dbt",
            "--selector",
            "m3_bronze_contract",
            "--no-partial-parse",
        ),
    ):
        if command_runner(argv, environment) != 0:
            raise M3LiveDrillError()


def _run_dbt(
    command_runner: CommandRunner, command: DbtBuildPlan, environment: Mapping[str, str]
) -> None:
    if command_runner(command.argv(), environment) != 0:
        raise M3LiveDrillError()


def _run_argv(
    command_runner: CommandRunner, argv: Sequence[str], environment: Mapping[str, str]
) -> None:
    if command_runner(argv, environment) != 0:
        raise M3LiveDrillError()


def _critical_gate_argv(plan: M3ReplayDrillPlan) -> tuple[str, ...]:
    return (
        "dbt",
        "test",
        "--project-dir",
        "dbt",
        "--profiles-dir",
        "dbt",
        "--selector",
        "m3_silver_critical",
        "--vars",
        plan.silver_build.vars_json,
    )


def _dbt_environment(
    settings: AppSettings,
    credential_values: Mapping[str, str],
    service: ServiceName,
    observation: DrillObservation,
    stage: str,
) -> dict[str, str]:
    identity = _identity_for(settings, service)
    key_path = credential_values.get(identity.private_key_path_env)
    if not key_path:
        raise M3LiveDrillError()
    environment = dict(os.environ)
    environment.update(
        {
            "DBT_SNOWFLAKE_USER": identity.user,
            "DBT_SNOWFLAKE_ROLE": identity.role,
            "DBT_SNOWFLAKE_PRIVATE_KEY_PATH": key_path,
            "DBT_SNOWFLAKE_QUERY_TAG": f"reviewlens:m3:{stage}:{observation.value}",
        }
    )
    passphrase = credential_values.get(identity.private_key_passphrase_env)
    if passphrase:
        environment["DBT_SNOWFLAKE_PRIVATE_KEY_PASSPHRASE"] = passphrase
    return environment


def _connect_service(
    settings: AppSettings,
    service: ServiceName,
    credential_values: Mapping[str, str],
    connect_service: Callable[
        [AppSettings, SnowflakeServiceIdentityConfig, Mapping[str, str]], SnowflakeClient
    ],
) -> SnowflakeClient:
    identity = _identity_for(settings, service)
    return connect_service(settings, identity, credential_values)


def _identity_for(settings: AppSettings, service: ServiceName) -> SnowflakeServiceIdentityConfig:
    for identity in settings.identities.snowflake_services:
        if identity.service is service:
            return identity
    raise M3LiveDrillError()


def _record_processing_lineage(
    client: SnowflakeClient, run: ProcessingRunDefinition, observation: DrillObservation
) -> None:
    trace_id = f"m3-drill-{observation.value}"
    values = (
        _literal(run.processing_run_id),
        _literal(run.contract_version),
        _literal(run.phase.value),
        _literal(run.source_release_id),
        _literal(run.ingestion_batch_id),
        str(len(run.inputs)),
        _literal(trace_id),
    )
    statement = (
        "INSERT INTO REVIEWLENS.AUDIT.PROCESSING_RUN "  # noqa: S608 - validated planner values
        "(PROCESS_RUN_ID, PROCESSING_CONTRACT_VERSION, PHASE, SOURCE_RELEASE_ID, "
        "INGESTION_BATCH_ID, INPUT_COUNT, CREATED_AT, TRACE_ID) "
        f"SELECT {', '.join(values[:6])}, CURRENT_TIMESTAMP(), {values[6]} "
        "WHERE NOT EXISTS (SELECT 1 FROM REVIEWLENS.AUDIT.PROCESSING_RUN "
        f"WHERE PROCESS_RUN_ID = {values[0]})"
    )
    client.execute(
        statement,
        operation="M3 processing lineage",
    )
    for reference in run.inputs:
        item = reference.input
        input_values = (
            _literal(reference.input_ref_id),
            _literal(run.processing_run_id),
            str(reference.input_ordinal),
            _literal(item.kind.value),
            _literal(item.logical_name),
            _literal(item.version_id),
            _literal(item.physical_ref.database),
            _literal(item.physical_ref.schema),
            _literal(item.physical_ref.object_name),
            "NULL" if item.content_sha256 is None else _literal(item.content_sha256),
            _literal(trace_id),
        )
        statement = (
            "INSERT INTO REVIEWLENS.AUDIT.PROCESSING_INPUT_REF "  # noqa: S608 - validated planner values
            "(INPUT_REF_ID, PROCESS_RUN_ID, INPUT_ORDINAL, INPUT_KIND, INPUT_LOGICAL_NAME, "
            "INPUT_VERSION_ID, PHYSICAL_DATABASE, PHYSICAL_SCHEMA, PHYSICAL_OBJECT, "
            "CONTENT_SHA256, CREATED_AT, TRACE_ID) "
            f"SELECT {', '.join(input_values[:10])}, CURRENT_TIMESTAMP(), {input_values[10]} "
            "WHERE NOT EXISTS (SELECT 1 FROM REVIEWLENS.AUDIT.PROCESSING_INPUT_REF "
            f"WHERE INPUT_REF_ID = {input_values[0]})"
        )
        client.execute(
            statement,
            operation="M3 processing input lineage",
        )


def _record_candidate_state(
    client: SnowflakeClient,
    run: ProcessingRunDefinition,
    candidate_id: str,
    layer: CandidateLayer,
    relations: Sequence[PhysicalRelationRef],
    state: str,
    observation: DrillObservation,
) -> None:
    if state not in {"BUILDING", "TEST_PASSED", "FAILED"}:
        raise M3LiveDrillError()
    for relation in relations:
        database = relation.database
        schema = relation.schema
        object_name = relation.object_name
        event_id = _event_id(candidate_id, state, observation, object_name)
        event_values = (
            _literal(event_id),
            _literal(candidate_id),
            _literal(run.processing_run_id),
            _literal(layer.value),
            _literal(run.contract_version),
            _literal(object_name.rsplit("__", maxsplit=1)[-1]),
            _literal(database),
            _literal(schema),
            _literal(object_name),
            _literal(state),
            _literal(f"m3-drill-{observation.value}"),
        )
        statement = (
            "INSERT INTO REVIEWLENS.AUDIT.CANDIDATE_PHYSICAL_REF_EVENT "  # noqa: S608 - validated planner values
            "(REF_EVENT_ID, CANDIDATE_ID, PROCESS_RUN_ID, LAYER, STRATEGY_VERSION, "
            "LOGICAL_NAME, PHYSICAL_DATABASE, PHYSICAL_SCHEMA, PHYSICAL_OBJECT, STATE, "
            "EVENT_AT, TRACE_ID) "
            f"SELECT {', '.join(event_values[:10])}, CURRENT_TIMESTAMP(), {event_values[10]} "
            "WHERE NOT EXISTS (SELECT 1 FROM REVIEWLENS.AUDIT.CANDIDATE_PHYSICAL_REF_EVENT "
            f"WHERE REF_EVENT_ID = {event_values[0]})"
        )
        client.execute(
            statement,
            operation="M3 candidate lifecycle evidence",
        )


def _silver_names(plan: M3ReplayDrillPlan) -> tuple[str, ...]:
    return tuple(reference.input.logical_name for reference in plan.gold_target.gold_run.inputs)


def _event_id(
    candidate_id: str, state: str, observation: DrillObservation, object_name: str
) -> str:
    return hashlib.sha256(
        f"m3-event-v1:{candidate_id}:{state}:{observation.value}:{object_name}".encode("ascii")
    ).hexdigest()


def _literal(value: str) -> str:
    if not value or "'" in value or "\n" in value or "\r" in value:
        raise M3LiveDrillError()
    return f"'{value}'"


def _safe_result(plan: M3ReplayDrillPlan, report: EquivalenceReport) -> M3LiveDrillResult:
    return M3LiveDrillResult(
        equivalent=report.equivalent,
        fingerprint_query_count=2,
        silver_candidate_id=plan.candidate_pair.silver_candidate_id,
        gold_candidate_id=plan.candidate_pair.gold_candidate_id,
    )


def _subprocess_runner(argv: Sequence[str], environment: Mapping[str, str]) -> int:
    try:
        completed = subprocess.run(  # noqa: S603 - fixed local dbt argv from typed planner
            list(argv),
            check=False,
            cwd=".",
            env=dict(environment),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        return 1
    return completed.returncode


def _service_connector(
    settings: AppSettings,
    identity: SnowflakeServiceIdentityConfig,
    credential_values: Mapping[str, str],
) -> SnowflakeClient:
    return SnowflakeClient.connect_service(
        settings.snowflake, identity, credential_values=credential_values
    )


def _bootstrap_connector(settings: AppSettings) -> SnowflakeClient:
    return SnowflakeClient.connect_bootstrap(settings.snowflake)


def main(argv: Sequence[str] | None = None) -> None:
    """Execute only after an explicit process-local operator confirmation."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="run the private bounded drill")
    arguments = parser.parse_args(argv)
    if not arguments.execute or os.environ.get("REVIEWLENS_RUN_M3_DRILL") != "CONFIRMED":
        parser.error("--execute plus REVIEWLENS_RUN_M3_DRILL=CONFIRMED are required")
    settings = load_settings()
    result = run_live_m3_drill(
        settings=settings,
        credential_values=load_environment_values(),
        command_runner=_subprocess_runner,
        connect_service=_service_connector,
        connect_bootstrap=_bootstrap_connector,
    )
    print(json.dumps(asdict(result), sort_keys=True))
