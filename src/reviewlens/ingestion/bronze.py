"""Allowlisted Snowflake Bronze COPY and append-only load-history services."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol

from reviewlens.clock import Clock
from reviewlens.ingestion.contracts import DatasetContract, load_olist_contract
from reviewlens.providers.snowflake import SnowflakeQueryResult

BRONZE_LOAD_LEDGER_VERSION = 1
BRONZE_TABLE_BY_DATASET = {
    "customers": "BRZ_OLIST_CUSTOMERS_RAW",
    "geolocation": "BRZ_OLIST_GEOLOCATION_RAW",
    "order_items": "BRZ_OLIST_ORDER_ITEMS_RAW",
    "order_payments": "BRZ_OLIST_ORDER_PAYMENTS_RAW",
    "order_reviews": "BRZ_OLIST_ORDER_REVIEWS_RAW",
    "orders": "BRZ_OLIST_ORDERS_RAW",
    "products": "BRZ_OLIST_PRODUCTS_RAW",
    "sellers": "BRZ_OLIST_SELLERS_RAW",
    "category_translation": "BRZ_PRODUCT_CATEGORY_TRANSLATION_RAW",
}
_IDENTIFIER = re.compile(r"^[A-Z][A-Z0-9_]*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_QUERY_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_TRACE_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_DATASET_RUN_ID = re.compile(r"^dsrun_[0-9a-f]{64}$")
_ATTEMPT_ID = re.compile(r"^attempt_[0-9a-f]{64}$")
_OBJECT_KEY = re.compile(
    r"^raw/(?P<dataset>[a-z][a-z0-9_]*)/"
    r"source_release_id=(?P<release>olist_[0-9a-f]{64})/"
    r"batch_id=(?P<batch>batch_[0-9a-f]{64})/"
    r"part-[0-9]{5}[.]parquet$"
)


class BronzeLoadStatus(StrEnum):
    LOADED = "LOADED"
    REPLAY_SKIPPED = "REPLAY_SKIPPED"


class BronzeLoadError(RuntimeError):
    code = "BRONZE_LOAD_INVALID"

    def __init__(self) -> None:
        super().__init__(self.code)


class BronzeLoadConflict(BronzeLoadError):
    code = "BRONZE_LOAD_CONFLICT"


@dataclass(frozen=True, slots=True)
class BronzeLoadEvent:
    event_id: str
    ledger_schema_version: int
    source_release_id: str
    ingestion_batch_id: str
    dataset_run_id: str
    attempt_id: str
    dataset_name: str
    target_table: str
    object_key: str
    object_sha256: str
    query_id: str
    status: BronzeLoadStatus
    rows_parsed: int
    rows_loaded: int
    error_count: int
    event_at: datetime
    trace_id: str


class BronzeCopyExecutor(Protocol):
    def execute_with_results(
        self,
        statement: str,
        *,
        operation: str = "Snowflake statement",
    ) -> SnowflakeQueryResult: ...


class BronzeLoadHistoryRepository(Protocol):
    def append(self, event: BronzeLoadEvent) -> BronzeLoadEvent: ...


class BronzeLoadLedgerExecutor(Protocol):
    def execute(self, statement: str, *, operation: str = "Snowflake statement") -> None: ...

    def query_all(
        self,
        statement: str,
        *,
        operation: str = "Snowflake query",
    ) -> list[tuple[Any, ...]]: ...


class InMemoryBronzeLoadHistoryRepository:
    """Deterministic append-only fake used by orchestration and unit tests."""

    def __init__(self) -> None:
        self._events: dict[str, BronzeLoadEvent] = {}

    @property
    def events(self) -> tuple[BronzeLoadEvent, ...]:
        return tuple(self._events.values())

    def append(self, event: BronzeLoadEvent) -> BronzeLoadEvent:
        existing = self._events.get(event.event_id)
        if existing is not None:
            if existing != event:
                raise BronzeLoadConflict()
            return existing
        self._events[event.event_id] = event
        return event


class SnowflakeBronzeLoadHistoryRepository:
    """Persist sanitized COPY facts to the append-only Snowflake audit ledger."""

    def __init__(self, executor: BronzeLoadLedgerExecutor, *, database: str = "REVIEWLENS") -> None:
        if _IDENTIFIER.fullmatch(database) is None:
            raise BronzeLoadError()
        self._executor = executor
        self._relation = f"{database}.AUDIT.BRONZE_LOAD_EVENT"

    def append(self, event: BronzeLoadEvent) -> BronzeLoadEvent:
        _validate_event(event)
        existing = self._executor.query_all(
            f"""SELECT
  EVENT_ID, LEDGER_SCHEMA_VERSION, SOURCE_RELEASE_ID, INGESTION_BATCH_ID,
  DATASET_RUN_ID, ATTEMPT_ID, DATASET_NAME, TARGET_TABLE, OBJECT_KEY,
  OBJECT_SHA256, QUERY_ID, STATUS, ROWS_PARSED, ROWS_LOADED, ERROR_COUNT,
  EVENT_AT, TRACE_ID
FROM {self._relation}
WHERE EVENT_ID = '{event.event_id}'""",  # noqa: S608 -- relation and event ID are validated
            operation="Bronze load event replay check",
        )
        if existing:
            if len(existing) != 1 or existing[0] != _event_row(event):
                raise BronzeLoadConflict()
            return event
        timestamp = event.event_at.isoformat()
        self._executor.execute(
            f"""INSERT INTO {self._relation} (
  EVENT_ID, LEDGER_SCHEMA_VERSION, SOURCE_RELEASE_ID, INGESTION_BATCH_ID,
  DATASET_RUN_ID, ATTEMPT_ID, DATASET_NAME, TARGET_TABLE, OBJECT_KEY,
  OBJECT_SHA256, QUERY_ID, STATUS, ROWS_PARSED, ROWS_LOADED, ERROR_COUNT,
  EVENT_AT, TRACE_ID
) SELECT
  '{event.event_id}', {event.ledger_schema_version}, '{event.source_release_id}',
  '{event.ingestion_batch_id}', '{event.dataset_run_id}', '{event.attempt_id}',
  '{event.dataset_name}', '{event.target_table}', '{event.object_key}',
  '{event.object_sha256}', '{event.query_id}', '{event.status.value}',
  {event.rows_parsed}, {event.rows_loaded}, {event.error_count},
  TO_TIMESTAMP_TZ('{timestamp}'), '{event.trace_id}'
WHERE NOT EXISTS (
  SELECT 1 FROM {self._relation} WHERE EVENT_ID = '{event.event_id}'
)""",  # noqa: S608 -- every interpolated value is validated metadata
            operation="Bronze load event append",
        )
        return event


@dataclass(frozen=True, slots=True)
class BronzeCopyReport:
    query_id: str
    status: BronzeLoadStatus
    rows_parsed: int
    rows_loaded: int
    error_count: int
    event_id: str


class BronzeCopyService:
    """Run one exact-file COPY; the future Airflow task owns this service call."""

    def __init__(
        self,
        executor: BronzeCopyExecutor,
        history: BronzeLoadHistoryRepository,
        *,
        clock: Clock,
        database: str = "REVIEWLENS",
    ) -> None:
        if _IDENTIFIER.fullmatch(database) is None:
            raise BronzeLoadError()
        self._executor = executor
        self._history = history
        self._clock = clock
        self._database = database

    def copy(
        self,
        *,
        dataset: DatasetContract,
        object_key: str,
        object_sha256: str,
        source_release_id: str,
        ingestion_batch_id: str,
        dataset_run_id: str,
        attempt_id: str,
        trace_id: str,
    ) -> BronzeCopyReport:
        _validate_load_inputs(
            dataset=dataset,
            object_key=object_key,
            object_sha256=object_sha256,
            source_release_id=source_release_id,
            ingestion_batch_id=ingestion_batch_id,
            trace_id=trace_id,
        )
        if (
            _DATASET_RUN_ID.fullmatch(dataset_run_id) is None
            or _ATTEMPT_ID.fullmatch(attempt_id) is None
        ):
            raise BronzeLoadError()
        statement = render_bronze_copy_sql(
            dataset=dataset,
            object_key=object_key,
            database=self._database,
        )
        result = self._executor.execute_with_results(
            statement,
            operation="Bronze immutable COPY INTO",
        )
        status, rows_parsed, rows_loaded, errors = _parse_copy_result(result)
        event = BronzeLoadEvent(
            event_id=_load_event_id(
                attempt_id=attempt_id,
                object_key=object_key,
                object_sha256=object_sha256,
                query_id=result.query_id,
            ),
            ledger_schema_version=BRONZE_LOAD_LEDGER_VERSION,
            source_release_id=source_release_id,
            ingestion_batch_id=ingestion_batch_id,
            dataset_run_id=dataset_run_id,
            attempt_id=attempt_id,
            dataset_name=dataset.dataset_name,
            target_table=BRONZE_TABLE_BY_DATASET[dataset.dataset_name],
            object_key=object_key,
            object_sha256=object_sha256,
            query_id=result.query_id,
            status=status,
            rows_parsed=rows_parsed,
            rows_loaded=rows_loaded,
            error_count=errors,
            event_at=self._clock.now(),
            trace_id=trace_id,
        )
        self._history.append(event)
        return BronzeCopyReport(
            query_id=event.query_id,
            status=event.status,
            rows_parsed=event.rows_parsed,
            rows_loaded=event.rows_loaded,
            error_count=event.error_count,
            event_id=event.event_id,
        )


def render_bronze_copy_sql(
    *,
    dataset: DatasetContract,
    object_key: str,
    database: str = "REVIEWLENS",
) -> str:
    """Render exact-file, replay-safe COPY with no credentials or user SQL."""

    if _IDENTIFIER.fullmatch(database) is None:
        raise BronzeLoadError()
    if dataset.dataset_name not in BRONZE_TABLE_BY_DATASET:
        raise BronzeLoadError()
    matched = _OBJECT_KEY.fullmatch(object_key)
    if matched is None or matched.group("dataset") != dataset.dataset_name:
        raise BronzeLoadError()
    table = BRONZE_TABLE_BY_DATASET[dataset.dataset_name]
    return f"""COPY INTO {database}.BRONZE.{table}
FROM @{database}.BRONZE.R2_STAGE
FILES = ('{object_key}')
FILE_FORMAT = (FORMAT_NAME = {database}.BRONZE.OLIST_PARQUET_FORMAT)
MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
ON_ERROR = ABORT_STATEMENT
FORCE = FALSE
PURGE = FALSE"""


def _parse_copy_result(
    result: SnowflakeQueryResult,
) -> tuple[BronzeLoadStatus, int, int, int]:
    if _QUERY_ID.fullmatch(result.query_id) is None:
        raise BronzeLoadError()
    if not result.rows:
        return BronzeLoadStatus.REPLAY_SKIPPED, 0, 0, 0
    if len(result.rows) != 1:
        raise BronzeLoadError()
    row = result.rows[0]
    if len(row) == 1 and "0 files processed" in str(row[0]).lower():
        return BronzeLoadStatus.REPLAY_SKIPPED, 0, 0, 0
    if len(row) >= 4 and str(row[1]).upper() == "LOAD_SKIPPED":
        try:
            parsed = int(row[2])
            loaded = int(row[3])
        except (TypeError, ValueError):
            raise BronzeLoadError() from None
        if parsed != 0 or loaded != 0:
            raise BronzeLoadError()
        return BronzeLoadStatus.REPLAY_SKIPPED, 0, 0, 0
    if len(row) < 6 or str(row[1]).upper() != "LOADED":
        raise BronzeLoadError()
    try:
        parsed = int(row[2])
        loaded = int(row[3])
        errors = int(row[5])
    except (TypeError, ValueError):
        raise BronzeLoadError() from None
    if min(parsed, loaded, errors) < 0 or loaded > parsed or errors > parsed:
        raise BronzeLoadError()
    return BronzeLoadStatus.LOADED, parsed, loaded, errors


def _validate_load_inputs(
    *,
    dataset: DatasetContract,
    object_key: str,
    object_sha256: str,
    source_release_id: str,
    ingestion_batch_id: str,
    trace_id: str,
) -> None:
    contract = load_olist_contract()
    if dataset != contract.by_file_name.get(dataset.file_name):
        raise BronzeLoadError()
    matched = _OBJECT_KEY.fullmatch(object_key)
    if (
        matched is None
        or matched.group("dataset") != dataset.dataset_name
        or matched.group("release") != source_release_id
        or matched.group("batch") != ingestion_batch_id
        or _SHA256.fullmatch(object_sha256) is None
        or _TRACE_ID.fullmatch(trace_id) is None
    ):
        raise BronzeLoadError()


def _load_event_id(
    *,
    attempt_id: str,
    object_key: str,
    object_sha256: str,
    query_id: str,
) -> str:
    payload = json.dumps(
        {
            "attempt_id": attempt_id,
            "object_key": object_key,
            "object_sha256": object_sha256,
            "query_id": query_id,
            "version": BRONZE_LOAD_LEDGER_VERSION,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _validate_event(event: BronzeLoadEvent) -> None:
    matched = _OBJECT_KEY.fullmatch(event.object_key)
    if (
        _SHA256.fullmatch(event.event_id) is None
        or event.ledger_schema_version != BRONZE_LOAD_LEDGER_VERSION
        or matched is None
        or matched.group("dataset") != event.dataset_name
        or matched.group("release") != event.source_release_id
        or matched.group("batch") != event.ingestion_batch_id
        or _DATASET_RUN_ID.fullmatch(event.dataset_run_id) is None
        or _ATTEMPT_ID.fullmatch(event.attempt_id) is None
        or BRONZE_TABLE_BY_DATASET.get(event.dataset_name) != event.target_table
        or _SHA256.fullmatch(event.object_sha256) is None
        or _QUERY_ID.fullmatch(event.query_id) is None
        or _TRACE_ID.fullmatch(event.trace_id) is None
        or min(event.rows_parsed, event.rows_loaded, event.error_count) < 0
        or event.rows_loaded > event.rows_parsed
        or event.error_count > event.rows_parsed
        or event.event_at.tzinfo is None
        or event.event_at.utcoffset() is None
    ):
        raise BronzeLoadError()


def _event_row(event: BronzeLoadEvent) -> tuple[Any, ...]:
    return (
        event.event_id,
        event.ledger_schema_version,
        event.source_release_id,
        event.ingestion_batch_id,
        event.dataset_run_id,
        event.attempt_id,
        event.dataset_name,
        event.target_table,
        event.object_key,
        event.object_sha256,
        event.query_id,
        event.status.value,
        event.rows_parsed,
        event.rows_loaded,
        event.error_count,
        event.event_at,
        event.trace_id,
    )
