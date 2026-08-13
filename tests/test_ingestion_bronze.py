from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import pytest

from reviewlens.clock import FrozenClock
from reviewlens.ingestion.bronze import (
    BRONZE_TABLE_BY_DATASET,
    BronzeCopyReport,
    BronzeCopyService,
    BronzeLoadConflict,
    BronzeLoadError,
    BronzeLoadStatus,
    InMemoryBronzeLoadHistoryRepository,
    SnowflakeBronzeLoadHistoryRepository,
    render_bronze_copy_sql,
)
from reviewlens.ingestion.contracts import load_olist_contract
from reviewlens.providers.snowflake import SnowflakeQueryResult

SOURCE_RELEASE_ID = f"olist_{'0' * 64}"
BATCH_ID = f"batch_{'1' * 64}"
DATASET_RUN_ID = f"dsrun_{'2' * 64}"
ATTEMPT_ID = f"attempt_{'3' * 64}"
OBJECT_SHA256 = "4" * 64
OBJECT_KEY = (
    f"raw/customers/source_release_id={SOURCE_RELEASE_ID}/batch_id={BATCH_ID}/part-00000.parquet"
)
INSTANT = datetime(2026, 8, 13, 6, 0, tzinfo=UTC)


class FakeCopyExecutor:
    def __init__(self, result: SnowflakeQueryResult) -> None:
        self.result = result
        self.statements: list[tuple[str, str]] = []

    def execute_with_results(
        self,
        statement: str,
        *,
        operation: str = "Snowflake statement",
    ) -> SnowflakeQueryResult:
        self.statements.append((statement, operation))
        return self.result


class FakeLedgerExecutor:
    def __init__(self) -> None:
        self.queries: list[str] = []
        self.statements: list[str] = []
        self.rows: list[tuple[Any, ...]] = []

    def execute(self, statement: str, *, operation: str = "Snowflake statement") -> None:
        self.statements.append(statement)

    def query_all(
        self,
        statement: str,
        *,
        operation: str = "Snowflake query",
    ) -> list[tuple[Any, ...]]:
        self.queries.append(statement)
        return self.rows


def _service(
    result: SnowflakeQueryResult,
) -> tuple[
    BronzeCopyService,
    FakeCopyExecutor,
    InMemoryBronzeLoadHistoryRepository,
]:
    executor = FakeCopyExecutor(result)
    history = InMemoryBronzeLoadHistoryRepository()
    return (
        BronzeCopyService(executor, history, clock=FrozenClock(INSTANT)),
        executor,
        history,
    )


def _copy(service: BronzeCopyService) -> BronzeCopyReport:
    dataset = load_olist_contract().by_file_name["olist_customers_dataset.csv"]
    return service.copy(
        dataset=dataset,
        object_key=OBJECT_KEY,
        object_sha256=OBJECT_SHA256,
        source_release_id=SOURCE_RELEASE_ID,
        ingestion_batch_id=BATCH_ID,
        dataset_run_id=DATASET_RUN_ID,
        attempt_id=ATTEMPT_ID,
        trace_id="trace-m2-copy",
    )


def test_copy_service_loads_exact_file_and_records_sanitized_history() -> None:
    result = SnowflakeQueryResult(
        query_id="01bc-copy-query",
        rows=((OBJECT_KEY, "LOADED", 2, 2, 1, 0, None, None, None, None),),
    )
    service, executor, history = _service(result)

    report = _copy(service)

    assert report.status is BronzeLoadStatus.LOADED
    assert (report.rows_parsed, report.rows_loaded, report.error_count) == (2, 2, 0)
    assert len(history.events) == 1
    event = history.events[0]
    assert event.object_key == OBJECT_KEY
    assert event.object_sha256 == OBJECT_SHA256
    assert event.event_at == INSTANT
    statement, operation = executor.statements[0]
    assert operation == "Bronze immutable COPY INTO"
    assert "COPY INTO REVIEWLENS.BRONZE.BRZ_OLIST_CUSTOMERS_RAW" in statement
    assert f"FILES = ('{OBJECT_KEY}')" in statement
    assert "MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE" in statement
    assert "ON_ERROR = ABORT_STATEMENT" in statement
    assert "FORCE = FALSE" in statement
    assert "PURGE = FALSE" in statement
    assert "AWS_KEY" not in statement
    assert "SECRET" not in statement


@pytest.mark.parametrize(
    "rows",
    [
        (),
        (("Copy executed with 0 files processed.",),),
        ((OBJECT_KEY, "LOAD_SKIPPED", 0, 0, None, 1, "File was loaded before."),),
    ],
)
def test_copy_replay_has_zero_committed_effect(rows: tuple[tuple[Any, ...], ...]) -> None:
    service, _, history = _service(SnowflakeQueryResult(query_id="01bc-replay-query", rows=rows))

    report = _copy(service)

    assert report.status is BronzeLoadStatus.REPLAY_SKIPPED
    assert (report.rows_parsed, report.rows_loaded, report.error_count) == (0, 0, 0)
    assert history.events[0].status is BronzeLoadStatus.REPLAY_SKIPPED


def test_copy_renderer_covers_all_nine_allowlisted_targets() -> None:
    contract = load_olist_contract()
    for ordinal, dataset in enumerate(contract.datasets):
        object_key = (
            f"raw/{dataset.dataset_name}/source_release_id={SOURCE_RELEASE_ID}/"
            f"batch_id={BATCH_ID}/part-{ordinal:05d}.parquet"
        )
        statement = render_bronze_copy_sql(dataset=dataset, object_key=object_key)
        assert BRONZE_TABLE_BY_DATASET[dataset.dataset_name] in statement
        assert object_key in statement


@pytest.mark.parametrize(
    "object_key",
    [
        "raw/customers/source_release_id=bad/batch_id=bad/part-00000.parquet",
        OBJECT_KEY + "' FORCE=TRUE --",
        OBJECT_KEY.replace("raw/customers/", "raw/orders/"),
        "../private.parquet",
    ],
)
def test_copy_rejects_untrusted_paths_before_provider_call(object_key: str) -> None:
    dataset = load_olist_contract().by_file_name["olist_customers_dataset.csv"]
    executor = FakeCopyExecutor(SnowflakeQueryResult(query_id="unused", rows=()))
    service = BronzeCopyService(
        executor,
        InMemoryBronzeLoadHistoryRepository(),
        clock=FrozenClock(INSTANT),
    )

    with pytest.raises(BronzeLoadError, match="BRONZE_LOAD_INVALID"):
        service.copy(
            dataset=dataset,
            object_key=object_key,
            object_sha256=OBJECT_SHA256,
            source_release_id=SOURCE_RELEASE_ID,
            ingestion_batch_id=BATCH_ID,
            dataset_run_id=DATASET_RUN_ID,
            attempt_id=ATTEMPT_ID,
            trace_id="trace-m2-copy",
        )

    assert executor.statements == []


def test_invalid_copy_result_fails_closed_without_source_content() -> None:
    canary = "seeded-private-review-canary"
    service, _, history = _service(
        SnowflakeQueryResult(query_id="01bc-failed-query", rows=((canary, "FAILED"),))
    )

    with pytest.raises(BronzeLoadError) as captured:
        _copy(service)

    assert str(captured.value) == "BRONZE_LOAD_INVALID"
    assert canary not in str(captured.value)
    assert history.events == ()


def test_in_memory_history_is_idempotent_and_detects_event_drift() -> None:
    service, _, history = _service(
        SnowflakeQueryResult(
            query_id="01bc-copy-query",
            rows=((OBJECT_KEY, "LOADED", 1, 1, 1, 0),),
        )
    )
    _copy(service)
    event = history.events[0]

    assert history.append(event) is event
    changed = replace(event, rows_loaded=0)
    with pytest.raises(BronzeLoadConflict, match="BRONZE_LOAD_CONFLICT"):
        history.append(changed)


def test_snowflake_history_repository_uses_append_only_metadata_sql() -> None:
    service, _, history = _service(
        SnowflakeQueryResult(
            query_id="01bc-copy-query",
            rows=((OBJECT_KEY, "LOADED", 1, 1, 1, 0),),
        )
    )
    _copy(service)
    event = history.events[0]
    executor = FakeLedgerExecutor()
    repository = SnowflakeBronzeLoadHistoryRepository(executor)

    repository.append(event)

    assert len(executor.queries) == 1
    assert len(executor.statements) == 1
    statement = executor.statements[0]
    assert "INSERT INTO REVIEWLENS.AUDIT.BRONZE_LOAD_EVENT" in statement
    assert "WHERE NOT EXISTS" in statement
    assert OBJECT_KEY in statement
    assert "seeded-private-review-canary" not in statement
    assert "UPDATE " not in statement
    assert "DELETE " not in statement

    executor.rows = [
        (
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
    ]
    repository.append(event)
    assert len(executor.statements) == 1

    executor.rows[0] = (*executor.rows[0][:13], 0, *executor.rows[0][14:])
    with pytest.raises(BronzeLoadConflict, match="BRONZE_LOAD_CONFLICT"):
        repository.append(event)
