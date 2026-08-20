"""Fail-closed registration of one immutable, already-tested M3 release definition."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass

from reviewlens.config import (
    AppSettings,
    DataMode,
    ServiceName,
    SnowflakeServiceIdentityConfig,
    load_environment_values,
    load_settings,
)
from reviewlens.providers.snowflake import SnowflakeClient
from reviewlens.warehouse.candidates import CandidateLayer
from reviewlens.warehouse.releases import (
    ReleaseContractError,
    ReleaseDefinition,
    ReleaseObjectRef,
    build_release_definition_for_tested_target,
)
from reviewlens.warehouse.replay_drill import build_approved_m3_replay_drill_plan

_EXPECTED_REF_COUNT = 28
_GOLD_SERVICE = ServiceName.GOLD_BUILD


class M3ReleaseRegistrationError(RuntimeError):
    """Sanitized failure for registration without pointer activation."""

    code = "M3_RELEASE_REGISTRATION_FAILED"

    def __init__(self) -> None:
        super().__init__(self.code)


@dataclass(frozen=True, slots=True)
class M3ReleaseRegistrationResult:
    """Safe result; physical names and source rows are deliberately omitted."""

    release_id: str
    object_ref_count: int
    pointer_mutated: bool = False


def validate_release_registration_settings(settings: AppSettings) -> None:
    """Reject unsafe runtime settings before a Snowflake connection is opened."""

    if (
        settings.data_mode is not DataMode.OLIST
        or not settings.snowflake.enabled
        or settings.snowflake.warehouse != "REVIEWLENS_WH"
        or settings.snowflake.warehouse_size != "X-SMALL"
        or settings.snowflake.auto_suspend_seconds != 60
    ):
        raise M3ReleaseRegistrationError()
    _gold_identity(settings)


def run_m3_release_registration(
    *,
    settings: AppSettings,
    credential_values: Mapping[str, str],
    connect_service: Callable[
        [AppSettings, SnowflakeServiceIdentityConfig, Mapping[str, str]], SnowflakeClient
    ],
    connect_bootstrap: Callable[[AppSettings], SnowflakeClient],
) -> M3ReleaseRegistrationResult:
    """Register a verified definition and ``CREATED`` event without moving the pointer.

    The latest state of every expected physical relation is read from the append-only
    candidate ledger before any write. All IDs are deterministic and guarded with
    ``WHERE NOT EXISTS``; the persisted header and all object references are then
    re-read exactly. No activation/rollback procedure is called from this module.
    """

    validate_release_registration_settings(settings)
    client: SnowflakeClient | None = None
    bootstrap: SnowflakeClient | None = None
    try:
        plan = build_approved_m3_replay_drill_plan()
        definition = build_release_definition_for_tested_target(plan.gold_target)
        client = connect_service(settings, _gold_identity(settings), credential_values)
        _assert_tested_candidate_pair(client, definition)
        _register_definition(client, definition)
        _assert_registered_definition(client, definition)
        return M3ReleaseRegistrationResult(
            release_id=definition.release_id,
            object_ref_count=len(definition.object_refs),
        )
    except (M3ReleaseRegistrationError, ReleaseContractError, RuntimeError, ValueError):
        raise M3ReleaseRegistrationError() from None
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
    raise M3ReleaseRegistrationError()


def _assert_tested_candidate_pair(client: SnowflakeClient, definition: ReleaseDefinition) -> None:
    result = client.execute_with_results(
        _candidate_state_sql(definition),
        operation="M3 tested candidate-pair verification",
    )
    actual = _parse_candidate_state_rows(result.rows)
    expected = {
        (
            definition.silver_candidate_id,
            CandidateLayer.SILVER.value,
            definition.silver_processing_run_id,
            item.physical_ref.database,
            item.physical_ref.schema,
            item.physical_ref.object_name,
        )
        for item in definition.object_refs
        if item.layer is CandidateLayer.SILVER
    } | {
        (
            definition.gold_candidate_id,
            CandidateLayer.GOLD.value,
            definition.gold_processing_run_id,
            item.physical_ref.database,
            item.physical_ref.schema,
            item.physical_ref.object_name,
        )
        for item in definition.object_refs
        if item.layer is CandidateLayer.GOLD
    }
    if len(expected) != _EXPECTED_REF_COUNT or actual != expected:
        raise M3ReleaseRegistrationError()


def _candidate_state_sql(definition: ReleaseDefinition) -> str:
    silver_id = _literal(definition.silver_candidate_id)
    gold_id = _literal(definition.gold_candidate_id)
    return "\n".join(
        (
            "WITH latest_ref_state AS (",
            "  SELECT CANDIDATE_ID, LAYER, PROCESS_RUN_ID, PHYSICAL_DATABASE,",
            "         PHYSICAL_SCHEMA, PHYSICAL_OBJECT, STATE,",
            "         ROW_NUMBER() OVER (",
            "           PARTITION BY CANDIDATE_ID, LAYER, PHYSICAL_DATABASE, "
            "PHYSICAL_SCHEMA, PHYSICAL_OBJECT",
            "           ORDER BY EVENT_AT DESC, REF_EVENT_ID DESC",
            "         ) AS EVENT_RANK",
            "  FROM REVIEWLENS.AUDIT.CANDIDATE_PHYSICAL_REF_EVENT",
            f"  WHERE (CANDIDATE_ID = {silver_id} AND LAYER = 'SILVER')",
            f"     OR (CANDIDATE_ID = {gold_id} AND LAYER = 'GOLD')",
            ")",
            "SELECT CANDIDATE_ID, LAYER, PROCESS_RUN_ID, PHYSICAL_DATABASE,",
            "       PHYSICAL_SCHEMA, PHYSICAL_OBJECT, STATE",
            "FROM latest_ref_state",
            "WHERE EVENT_RANK = 1 AND STATE = 'TEST_PASSED'",
            "ORDER BY CANDIDATE_ID, LAYER, PHYSICAL_DATABASE, PHYSICAL_SCHEMA, PHYSICAL_OBJECT",
        )
    )


def _parse_candidate_state_rows(
    rows: Sequence[Sequence[object]],
) -> set[tuple[str, str, str, str, str, str]]:
    parsed: set[tuple[str, str, str, str, str, str]] = set()
    try:
        for row in rows:
            if len(row) != 7 or str(row[6]) != "TEST_PASSED":
                raise M3ReleaseRegistrationError()
            candidate_id, layer, process_run_id, database, schema, object_name, _ = row
            item: tuple[str, str, str, str, str, str] = (
                str(candidate_id),
                str(layer),
                str(process_run_id),
                str(database),
                str(schema),
                str(object_name),
            )
            if not all(item) or item in parsed:
                raise M3ReleaseRegistrationError()
            parsed.add(item)
    except (TypeError, ValueError) as error:
        raise M3ReleaseRegistrationError() from error
    return parsed


def _register_definition(client: SnowflakeClient, definition: ReleaseDefinition) -> None:
    client.execute(
        _definition_insert_sql(definition),
        operation="M3 immutable release definition registration",
    )
    for item in definition.object_refs:
        client.execute(
            _object_ref_insert_sql(definition.release_id, item),
            operation="M3 immutable release object-reference registration",
        )
    client.execute(
        _created_event_insert_sql(definition),
        operation="M3 immutable release created-event registration",
    )


def _assert_registered_definition(client: SnowflakeClient, definition: ReleaseDefinition) -> None:
    header = client.execute_with_results(
        _definition_verify_sql(definition),
        operation="M3 immutable release header verification",
    )
    expected_header = (
        definition.definition_sha256,
        definition.definition_version,
        definition.source_release_id,
        definition.ingestion_batch_id,
        definition.silver_processing_run_id,
        definition.gold_processing_run_id,
        definition.silver_candidate_id,
        definition.gold_candidate_id,
        definition.semantic_contract_version,
    )
    actual_header = tuple(tuple(str(value) for value in row) for row in header.rows)
    if actual_header != (expected_header,):
        raise M3ReleaseRegistrationError()

    refs = client.execute_with_results(
        _object_ref_verify_sql(definition),
        operation="M3 immutable release object-reference verification",
    )
    expected_refs = tuple(
        (
            item.layer.value,
            item.logical_name,
            item.physical_ref.database,
            item.physical_ref.schema,
            item.physical_ref.object_name,
        )
        for item in definition.object_refs
    )
    actual_refs = tuple(tuple(str(value) for value in row) for row in refs.rows)
    if actual_refs != expected_refs or len(actual_refs) != _EXPECTED_REF_COUNT:
        raise M3ReleaseRegistrationError()


def _definition_insert_sql(definition: ReleaseDefinition) -> str:
    values = (
        _literal(definition.release_id),
        _literal(definition.definition_sha256),
        _literal(definition.definition_version),
        _literal(definition.source_release_id),
        _literal(definition.ingestion_batch_id),
        _literal(definition.silver_processing_run_id),
        _literal(definition.gold_processing_run_id),
        _literal(definition.silver_candidate_id),
        _literal(definition.gold_candidate_id),
        _literal(definition.semantic_contract_version),
        _literal(_trace_id(definition.release_id)),
    )
    return "\n".join(
        (
            "INSERT INTO REVIEWLENS.AUDIT.RELEASE_DEFINITION (",
            "  RELEASE_ID, DEFINITION_SHA256, DEFINITION_VERSION, SOURCE_RELEASE_ID, "
            "INGESTION_BATCH_ID,",
            "  SILVER_PROCESS_RUN_ID, GOLD_PROCESS_RUN_ID, SILVER_CANDIDATE_ID, GOLD_CANDIDATE_ID,",
            "  SEMANTIC_CONTRACT_VERSION, CREATED_AT, TRACE_ID",
            ")",
            "SELECT " + ", ".join(values[:10]) + f", CURRENT_TIMESTAMP(), {values[10]}",
            "WHERE NOT EXISTS (",
            "  SELECT 1 FROM REVIEWLENS.AUDIT.RELEASE_DEFINITION",
            f"  WHERE RELEASE_ID = {values[0]}",
            ")",
        )
    )


def _object_ref_insert_sql(release_id: str, item: ReleaseObjectRef) -> str:
    ref_id = _object_ref_id(release_id, item)
    values = (
        _literal(ref_id),
        _literal(release_id),
        _literal(item.layer.value),
        _literal(item.logical_name),
        _literal(item.physical_ref.database),
        _literal(item.physical_ref.schema),
        _literal(item.physical_ref.object_name),
        _literal(_trace_id(release_id)),
    )
    return "\n".join(
        (
            "INSERT INTO REVIEWLENS.AUDIT.RELEASE_OBJECT_REF (",
            "  RELEASE_OBJECT_REF_ID, RELEASE_ID, LAYER, LOGICAL_NAME, PHYSICAL_DATABASE,",
            "  PHYSICAL_SCHEMA, PHYSICAL_OBJECT, CREATED_AT, TRACE_ID",
            ")",
            "SELECT " + ", ".join(values[:7]) + f", CURRENT_TIMESTAMP(), {values[7]}",
            "WHERE NOT EXISTS (",
            "  SELECT 1 FROM REVIEWLENS.AUDIT.RELEASE_OBJECT_REF",
            f"  WHERE RELEASE_OBJECT_REF_ID = {values[0]}",
            ")",
        )
    )


def _created_event_insert_sql(definition: ReleaseDefinition) -> str:
    event_id = _created_event_id(definition.release_id)
    values = (
        _literal(event_id),
        _literal(definition.release_id),
        _literal(definition.gold_processing_run_id),
        _literal(definition.silver_candidate_id),
        _literal(definition.gold_candidate_id),
        _literal("release-owner"),
        _literal("CANDIDATE_TEST_PASSED"),
        _literal(definition.definition_sha256),
        _literal(_trace_id(definition.release_id)),
    )
    return "\n".join(
        (
            "INSERT INTO REVIEWLENS.AUDIT.RELEASE_EVENT (",
            "  EVENT_ID, LEDGER_SCHEMA_VERSION, RELEASE_ID, DATASET_RUN_ID, EVENT_TYPE,",
            "  PREVIOUS_RELEASE_ID, SILVER_VERSION, AI_VERSION, GOLD_VERSION, INDEX_VERSION,",
            "  ACTOR_SERVICE, REASON_CODE, EXPECTED_POINTER_VERSION, RESULT_POINTER_VERSION,",
            "  DEFINITION_SHA256, EVENT_AT, TRACE_ID, SANITIZED_METADATA",
            ")",
            "SELECT "
            + ", ".join(
                (
                    values[0],
                    "1",
                    values[1],
                    values[2],
                    "'CREATED'",
                    "NULL",
                    values[3],
                    "NULL",
                    values[4],
                    "NULL",
                    values[5],
                    values[6],
                    "0",
                    "0",
                    values[7],
                    "CURRENT_TIMESTAMP()",
                    values[8],
                    f"OBJECT_CONSTRUCT('definition_sha256', {values[7]})",
                )
            ),
            "WHERE NOT EXISTS (",
            "  SELECT 1 FROM REVIEWLENS.AUDIT.RELEASE_EVENT",
            f"  WHERE EVENT_ID = {values[0]}",
            ")",
        )
    )


def _definition_verify_sql(definition: ReleaseDefinition) -> str:
    return "\n".join(
        (
            "SELECT DEFINITION_SHA256, DEFINITION_VERSION, SOURCE_RELEASE_ID, INGESTION_BATCH_ID,",
            "       SILVER_PROCESS_RUN_ID, GOLD_PROCESS_RUN_ID, SILVER_CANDIDATE_ID, "
            "GOLD_CANDIDATE_ID,",
            "       SEMANTIC_CONTRACT_VERSION",
            "FROM REVIEWLENS.AUDIT.RELEASE_DEFINITION",
            f"WHERE RELEASE_ID = {_literal(definition.release_id)}",
        )
    )


def _object_ref_verify_sql(definition: ReleaseDefinition) -> str:
    return "\n".join(
        (
            "SELECT LAYER, LOGICAL_NAME, PHYSICAL_DATABASE, PHYSICAL_SCHEMA, PHYSICAL_OBJECT",
            "FROM REVIEWLENS.AUDIT.RELEASE_OBJECT_REF",
            f"WHERE RELEASE_ID = {_literal(definition.release_id)}",
            "ORDER BY LAYER, LOGICAL_NAME, PHYSICAL_DATABASE, PHYSICAL_SCHEMA, PHYSICAL_OBJECT",
        )
    )


def _object_ref_id(release_id: str, item: ReleaseObjectRef) -> str:
    return _digest("release_object_ref", "|".join((release_id, *item.canonical_key)))


def _created_event_id(release_id: str) -> str:
    return _digest("release_created_event", release_id)


def _trace_id(release_id: str) -> str:
    return f"m3-release:{release_id[:16]}"


def _digest(kind: str, value: str) -> str:
    return hashlib.sha256(f"{kind}:v1:{value}".encode("ascii")).hexdigest()


def _literal(value: str) -> str:
    if not value or "'" in value or "\n" in value or "\r" in value:
        raise M3ReleaseRegistrationError()
    return f"'{value}'"


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
    """Run only after explicit process-local registration confirmation."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="register the private release definition",
    )
    arguments = parser.parse_args(argv)
    if not arguments.execute or os.environ.get("REVIEWLENS_REGISTER_M3_RELEASE") != "CONFIRMED":
        parser.error("--execute plus REVIEWLENS_REGISTER_M3_RELEASE=CONFIRMED are required")
    result = run_m3_release_registration(
        settings=load_settings(),
        credential_values=load_environment_values(),
        connect_service=_service_connector,
        connect_bootstrap=_bootstrap_connector,
    )
    print(json.dumps(asdict(result), sort_keys=True))
