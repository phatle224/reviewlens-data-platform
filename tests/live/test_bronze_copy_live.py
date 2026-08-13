from __future__ import annotations

import hashlib
import os
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from reviewlens.clock import SystemClock
from reviewlens.config import ServiceName, load_environment_values, load_settings
from reviewlens.ingestion.bronze import (
    BronzeCopyService,
    BronzeLoadStatus,
    SnowflakeBronzeLoadHistoryRepository,
)
from reviewlens.ingestion.contracts import load_olist_contract
from reviewlens.ingestion.parquet import RawParquetRecord, write_raw_partition
from reviewlens.providers.r2 import R2Client, R2RuntimePurpose
from reviewlens.providers.snowflake import SnowflakeClient, SnowflakeProviderError

pytestmark = pytest.mark.live


@pytest.mark.skipif(
    os.environ.get("REVIEWLENS_RUN_LIVE_BRONZE_COPY") != "1",
    reason="set REVIEWLENS_RUN_LIVE_BRONZE_COPY=1 for the synthetic Bronze COPY smoke test",
)
def test_synthetic_parquet_r2_to_bronze_copy_and_replay() -> None:
    settings = load_settings()
    credentials = load_environment_values()
    identity = next(
        item
        for item in settings.identities.snowflake_services
        if item.service is ServiceName.INGESTION
    )
    r2 = R2Client.from_runtime_identity(
        settings.r2,
        settings.identities,
        R2RuntimePurpose.INGESTION,
        credential_values=credentials,
    )
    bootstrap: SnowflakeClient | None = None
    runtime: SnowflakeClient | None = None
    nonce = uuid4().hex
    source_release_id = f"olist_{_digest(f'release:{nonce}')}"
    ingestion_batch_id = f"batch_{_digest(f'batch:{nonce}')}"
    dataset_run_id = f"dsrun_{_digest(f'dataset:{nonce}')}"
    attempt_id = f"attempt_{_digest(f'attempt:{nonce}')}"
    source_sha256 = _digest(f"source:{nonce}")
    record_hash = _digest(f"record:{nonce}")
    dataset = load_olist_contract().by_file_name["olist_customers_dataset.csv"]
    ingested_at = datetime.now(UTC)
    artifact = write_raw_partition(
        [
            RawParquetRecord(
                source_release_id=source_release_id,
                ingestion_batch_id=ingestion_batch_id,
                dataset_run_id=dataset_run_id,
                source_file_name=dataset.file_name,
                source_row_number=1,
                source_object_sha256=source_sha256,
                record_hash=record_hash,
                ingested_at=ingested_at,
                schema_version=f"{dataset.dataset_name}:olist-source-v1",
                values={
                    "customer_id": f"synthetic-customer-{nonce}",
                    "customer_unique_id": f"synthetic-unique-{nonce}",
                    "customer_zip_code_prefix": "00000",
                    "customer_city": "synthetic-city",
                    "customer_state": "ZZ",
                },
            )
        ],
        dataset=dataset,
        output_root=Path("data"),
        source_release_id=source_release_id,
        ingestion_batch_id=ingestion_batch_id,
    )
    assert artifact is not None
    local_path = _windows_long_path(Path("data") / Path(artifact.object_key))
    local_manifest_path = _windows_long_path(Path("data") / Path(artifact.manifest_key))

    try:
        bootstrap = SnowflakeClient.connect_bootstrap(settings.snowflake)
        uploaded = r2.put_file_create_only(
            artifact.object_key,
            local_path,
            content_type="application/vnd.apache.parquet",
            metadata={
                "data-class": "synthetic",
                "sha256": artifact.sha256,
                "row-count": str(artifact.row_count),
            },
        )
        assert uploaded.size == artifact.size_bytes
        assert uploaded.metadata["sha256"] == artifact.sha256

        bootstrap.apply_foundation(Path("infra/snowflake/001_foundation.sql"))
        bootstrap.create_or_replace_r2_runtime_stage(
            snowflake=settings.snowflake,
            r2=settings.r2,
            identities=settings.identities,
            credential_values=credentials,
        )
        bootstrap.apply_sql_file(
            Path("infra/snowflake/005_bronze.sql"),
            operation="Bronze migration",
        )
        bootstrap.apply_sql_file(
            Path("infra/snowflake/005_bronze.sql"),
            operation="Bronze migration replay",
        )
        runtime = SnowflakeClient.connect_service(
            settings.snowflake,
            identity,
            credential_values=credentials,
        )
        service = BronzeCopyService(
            runtime,
            SnowflakeBronzeLoadHistoryRepository(runtime),
            clock=SystemClock(),
        )

        loaded = service.copy(
            dataset=dataset,
            object_key=artifact.object_key,
            object_sha256=artifact.sha256,
            source_release_id=source_release_id,
            ingestion_batch_id=ingestion_batch_id,
            dataset_run_id=dataset_run_id,
            attempt_id=attempt_id,
            trace_id=f"live-bronze-{nonce}",
        )
        replay = service.copy(
            dataset=dataset,
            object_key=artifact.object_key,
            object_sha256=artifact.sha256,
            source_release_id=source_release_id,
            ingestion_batch_id=ingestion_batch_id,
            dataset_run_id=dataset_run_id,
            attempt_id=f"attempt_{_digest(f'replay:{nonce}')}",
            trace_id=f"live-bronze-replay-{nonce}",
        )
        with pytest.raises(SnowflakeProviderError):
            runtime.query_all(
                f"""SELECT COUNT(*)
FROM {settings.snowflake.database}.BRONZE.BRZ_OLIST_CUSTOMERS_RAW
WHERE INGESTION_BATCH_ID = '{ingestion_batch_id}'""",  # noqa: S608 -- generated ID
                operation="ingestion Bronze read denial",
            )
        bootstrap.execute(
            f"USE WAREHOUSE {settings.snowflake.warehouse}",
            operation="Bronze reconciliation warehouse selection",
        )
        rows = bootstrap.query_all(
            f"""SELECT COUNT(*), COUNT(DISTINCT RECORD_HASH)
FROM {settings.snowflake.database}.BRONZE.BRZ_OLIST_CUSTOMERS_RAW
WHERE INGESTION_BATCH_ID = '{ingestion_batch_id}'""",  # noqa: S608 -- generated ID
            operation="Bronze synthetic reconciliation",
        )

        assert loaded.status is BronzeLoadStatus.LOADED
        assert loaded.rows_loaded == 1
        assert replay.status is BronzeLoadStatus.REPLAY_SKIPPED
        assert replay.rows_loaded == 0
        assert rows == [(1, 1)]
    finally:
        if runtime is not None:
            runtime.close()
        if bootstrap is not None:
            with suppress(Exception):
                bootstrap.execute(
                    f"""DELETE FROM {settings.snowflake.database}.AUDIT.BRONZE_LOAD_EVENT
WHERE INGESTION_BATCH_ID = '{ingestion_batch_id}'""",  # noqa: S608 -- generated ID
                    operation="Bronze smoke audit cleanup",
                )
            with suppress(Exception):
                bootstrap.execute(
                    f"""DELETE FROM {settings.snowflake.database}.BRONZE.BRZ_OLIST_CUSTOMERS_RAW
WHERE INGESTION_BATCH_ID = '{ingestion_batch_id}'""",  # noqa: S608 -- generated ID
                    operation="Bronze smoke row cleanup",
                )
            try:
                bootstrap.suspend_warehouse(settings.snowflake.warehouse)
            finally:
                bootstrap.close()
        with suppress(Exception):
            r2.delete(artifact.object_key)
        local_path.unlink(missing_ok=True)
        local_manifest_path.unlink(missing_ok=True)

    assert not r2.exists(artifact.object_key)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _windows_long_path(path: Path) -> Path:
    resolved = path.resolve()
    if os.name != "nt":
        return resolved
    return Path(f"\\\\?\\{resolved}")
