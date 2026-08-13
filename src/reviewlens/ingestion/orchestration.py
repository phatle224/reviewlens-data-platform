"""Airflow task boundary for the private Olist-to-Bronze ingestion slice."""

from __future__ import annotations

import hashlib
import os
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from pathlib import Path
from time import monotonic
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from reviewlens.clock import FrozenClock
from reviewlens.config import DataMode, ServiceName, load_environment_values, load_settings
from reviewlens.ingestion.bronze import (
    BRONZE_TABLE_BY_DATASET,
    BronzeCopyService,
    BronzeLoadStatus,
    SnowflakeBronzeLoadHistoryRepository,
)
from reviewlens.ingestion.contracts import DataClass, load_olist_contract
from reviewlens.ingestion.identity import (
    attempt_id,
    dataset_run_id,
    ingestion_batch_id,
    source_object_id,
)
from reviewlens.ingestion.parquet import ParquetArtifact
from reviewlens.ingestion.preflight import (
    PrivacyPreflightEvidence,
    load_approved_olist_snapshot,
    run_upload_preflight,
)
from reviewlens.ingestion.processing import process_dataset_file
from reviewlens.ingestion.reconciliation import DatasetReconciliationInput, reconcile_snapshot
from reviewlens.ingestion.source import (
    DiscoveredFile,
    build_canonical_manifest,
    discover_source_snapshot,
)
from reviewlens.ingestion.source_upload import upload_immutable_source_snapshot
from reviewlens.observability.ingestion import (
    DatasetIngestionMetrics,
    IngestionOperationsSnapshot,
    write_ingestion_operations_artifacts,
)
from reviewlens.providers.r2 import (
    R2Client,
    R2ObjectAlreadyExistsError,
    R2RuntimePurpose,
)
from reviewlens.providers.snowflake import SnowflakeClient


class IngestionTask(StrEnum):
    VALIDATE_SOURCE = "validate_source"
    UPLOAD_TO_R2 = "upload_to_r2"
    COPY_TO_BRONZE = "copy_to_bronze"


class AirflowIngestionTaskError(RuntimeError):
    """Stable task error that never echoes source rows, paths or provider responses."""

    code = "AIRFLOW_INGESTION_TASK_FAILED"

    def __init__(self) -> None:
        super().__init__(self.code)


class DatasetValidationContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    dataset_name: str
    file_name: str
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_size_bytes: int = Field(gt=0)
    source_rows: int = Field(ge=0)
    source_object_id: str = Field(pattern=r"^srcobj_[0-9a-f]{64}$")
    dataset_run_id: str = Field(pattern=r"^dsrun_[0-9a-f]{64}$")
    attempt_id: str = Field(pattern=r"^attempt_[0-9a-f]{64}$")

    @model_validator(mode="after")
    def require_contract_mapping(self) -> DatasetValidationContext:
        dataset = load_olist_contract().by_file_name.get(self.file_name)
        if dataset is None or dataset.dataset_name != self.dataset_name:
            raise ValueError("dataset context does not match the source contract")
        return self


class ValidatedIngestionContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    context_version: Literal["olist-airflow-context-v1"] = "olist-airflow-context-v1"
    source_release_id: str = Field(pattern=r"^olist_[0-9a-f]{64}$")
    ingestion_batch_id: str = Field(pattern=r"^batch_[0-9a-f]{64}$")
    source_snapshot_date: date
    ingested_at: datetime
    attempt_number: int = Field(ge=1, le=2_147_483_647)
    trace_id: str = Field(pattern=r"^[a-z0-9_.:-]{1,128}$")
    datasets: tuple[DatasetValidationContext, ...] = Field(min_length=9, max_length=9)

    @field_validator("ingested_at")
    @classmethod
    def require_aware_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("ingested_at must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def require_exact_datasets(self) -> ValidatedIngestionContext:
        contract = load_olist_contract()
        expected = {item.dataset_name for item in contract.datasets}
        actual = [item.dataset_name for item in self.datasets]
        if (
            len(actual) != len(set(actual))
            or set(actual) != expected
            or self.ingestion_batch_id
            != ingestion_batch_id(source_release_id=self.source_release_id)
        ):
            raise ValueError("validated context must contain the exact Olist dataset set")
        for item in self.datasets:
            expected_object = source_object_id(
                source_release_id=self.source_release_id,
                file_name=item.file_name,
                source_object_sha256=item.source_sha256,
            )
            expected_run = dataset_run_id(
                ingestion_batch_id=self.ingestion_batch_id,
                source_object_id=expected_object,
                dataset_name=item.dataset_name,
                contract_version=contract.contract_version,
            )
            if (
                item.source_object_id != expected_object
                or item.dataset_run_id != expected_run
                or item.attempt_id
                != attempt_id(
                    dataset_run_id=expected_run,
                    attempt_number=self.attempt_number,
                )
            ):
                raise ValueError("dataset lineage identifiers are not canonical")
        return self


class ArtifactContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    object_key: str
    manifest_key: str
    row_count: int = Field(ge=0)
    size_bytes: int = Field(gt=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    replayed: bool


class DatasetUploadContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    validation: DatasetValidationContext
    observed_rows: int = Field(ge=0)
    new_rows: int = Field(ge=0)
    replay_rows: int = Field(ge=0)
    duplicate_rows: int = Field(ge=0)
    rejected_rows: int = Field(ge=0)
    parse_failed_rows: int = Field(ge=0)
    raw_artifact: ArtifactContext
    quarantine_artifacts: tuple[ArtifactContext, ...]

    @model_validator(mode="after")
    def require_reconciled_dispositions(self) -> DatasetUploadContext:
        explained = (
            self.new_rows
            + self.replay_rows
            + self.duplicate_rows
            + self.rejected_rows
            + self.parse_failed_rows
        )
        if self.observed_rows != explained or self.raw_artifact.row_count != self.new_rows:
            raise ValueError("uploaded dataset dispositions do not reconcile")
        return self


class UploadedIngestionContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    validation: ValidatedIngestionContext
    source_objects_uploaded: int = Field(ge=0)
    source_objects_replayed: int = Field(ge=0)
    source_objects_verified: int = Field(ge=0)
    datasets: tuple[DatasetUploadContext, ...] = Field(min_length=9, max_length=9)

    @model_validator(mode="after")
    def require_matching_datasets(self) -> UploadedIngestionContext:
        planned = {item.dataset_name for item in self.validation.datasets}
        actual = [item.validation.dataset_name for item in self.datasets]
        if (
            len(actual) != len(set(actual))
            or set(actual) != planned
            or self.source_objects_verified != 10
            or self.source_objects_uploaded + self.source_objects_replayed != 10
        ):
            raise ValueError("uploaded context must match validated datasets")
        for item in self.datasets:
            expected_prefix = (
                f"raw/{item.validation.dataset_name}/"
                f"source_release_id={self.validation.source_release_id}/"
                f"batch_id={self.validation.ingestion_batch_id}/"
            )
            if not item.raw_artifact.object_key.startswith(expected_prefix):
                raise ValueError("raw artifact does not match validated lineage")
        return self


class BronzeDatasetResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    dataset_name: str
    copy_status: BronzeLoadStatus
    query_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,128}$")
    rows_loaded: int = Field(ge=0)
    bronze_rows: int = Field(ge=0)
    distinct_record_hashes: int = Field(ge=0)


class BronzeIngestionResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_release_id: str = Field(pattern=r"^olist_[0-9a-f]{64}$")
    ingestion_batch_id: str = Field(pattern=r"^batch_[0-9a-f]{64}$")
    reconciled: bool
    issue_count: int = Field(ge=0)
    datasets: tuple[BronzeDatasetResult, ...] = Field(min_length=9, max_length=9)

    @model_validator(mode="after")
    def require_reconciled_result(self) -> BronzeIngestionResult:
        expected = {item.dataset_name for item in load_olist_contract().datasets}
        actual = [item.dataset_name for item in self.datasets]
        if (
            len(actual) != len(set(actual))
            or set(actual) != expected
            or self.reconciled != (self.issue_count == 0)
            or any(item.distinct_record_hashes != item.bronze_rows for item in self.datasets)
        ):
            raise ValueError("Bronze result does not reconcile")
        return self


class IngestionTaskRunner(Protocol):
    def validate_source(self) -> ValidatedIngestionContext: ...

    def upload_to_r2(self, context: ValidatedIngestionContext) -> UploadedIngestionContext: ...

    def copy_to_bronze(self, context: UploadedIngestionContext) -> BronzeIngestionResult: ...


@dataclass(frozen=True, slots=True)
class AirflowTaskRouter:
    """Typed dispatcher used by Airflow and deterministic orchestration tests."""

    runner: IngestionTaskRunner

    def execute(
        self,
        task_name: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            task = IngestionTask(task_name)
            if task is IngestionTask.VALIDATE_SOURCE:
                if payload is not None:
                    raise AirflowIngestionTaskError()
                result: BaseModel = self.runner.validate_source()
            elif task is IngestionTask.UPLOAD_TO_R2:
                if payload is None:
                    raise AirflowIngestionTaskError()
                result = self.runner.upload_to_r2(ValidatedIngestionContext.model_validate(payload))
            else:
                if payload is None:
                    raise AirflowIngestionTaskError()
                result = self.runner.copy_to_bronze(
                    UploadedIngestionContext.model_validate(payload)
                )
            return result.model_dump(mode="json")
        except AirflowIngestionTaskError:
            raise
        except Exception:
            raise AirflowIngestionTaskError() from None


class LocalAirflowIngestionRunner:
    """Runtime-only provider composition; construction is forbidden during DAG import."""

    def __init__(
        self,
        *,
        source_root: Path,
        output_root: Path,
        attempt_number: int = 1,
    ) -> None:
        if not 1 <= attempt_number <= 2_147_483_647:
            raise AirflowIngestionTaskError()
        self._source_root = source_root
        self._output_root = output_root
        self._attempt_number = attempt_number

    @classmethod
    def from_environment(cls) -> LocalAirflowIngestionRunner:
        if os.environ.get("REVIEWLENS_ENABLE_OLIST_PIPELINE") != "1":
            raise AirflowIngestionTaskError()
        source = os.environ.get("REVIEWLENS_SOURCE_DIR")
        output = os.environ.get("REVIEWLENS_OUTPUT_DIR")
        if not source or not output:
            raise AirflowIngestionTaskError()
        try:
            attempt_number = int(os.environ.get("REVIEWLENS_BACKFILL_ATTEMPT_NUMBER", "1"))
        except ValueError:
            raise AirflowIngestionTaskError() from None
        return cls(
            source_root=Path(source),
            output_root=Path(output),
            attempt_number=attempt_number,
        )

    def validate_source(self) -> ValidatedIngestionContext:
        try:
            approved = load_approved_olist_snapshot()
            snapshot = discover_source_snapshot(self._source_root)
            ingested_at = datetime.combine(approved.source_snapshot_date, datetime.min.time(), UTC)
            manifest = build_canonical_manifest(
                snapshot,
                source_snapshot_date=approved.source_snapshot_date,
                created_at=ingested_at,
            )
            batch_id = ingestion_batch_id(source_release_id=manifest.source_release_id)
            dataset_contexts = tuple(
                _dataset_validation_context(
                    item,
                    source_release_id=manifest.source_release_id,
                    batch_id=batch_id,
                    contract_version=manifest.contract_version,
                    attempt_number=self._attempt_number,
                )
                for item in snapshot.files
            )
            return ValidatedIngestionContext(
                source_release_id=manifest.source_release_id,
                ingestion_batch_id=batch_id,
                source_snapshot_date=approved.source_snapshot_date,
                ingested_at=ingested_at,
                attempt_number=self._attempt_number,
                trace_id=f"m2-ingestion:{manifest.source_release_id[6:22]}",
                datasets=dataset_contexts,
            )
        except AirflowIngestionTaskError:
            raise
        except Exception:
            raise AirflowIngestionTaskError() from None

    def upload_to_r2(self, context: ValidatedIngestionContext) -> UploadedIngestionContext:
        try:
            settings = load_settings().model_copy(update={"data_mode": DataMode.OLIST})
            credentials = load_environment_values()
            snapshot = discover_source_snapshot(self._source_root)
            approved = load_approved_olist_snapshot()
            manifest = build_canonical_manifest(
                snapshot,
                source_snapshot_date=approved.source_snapshot_date,
                created_at=context.ingested_at,
            )
            _require_matching_validation(context, manifest.source_release_id)
            contract = load_olist_contract()
            preflight = run_upload_preflight(
                settings=settings,
                manifest=manifest,
                privacy_evidence=_privacy_evidence(),
                attribution_text=(settings_path() / "docs" / "DATA_ATTRIBUTION.md").read_text(
                    encoding="utf-8"
                ),
                approved_snapshot=approved,
            )
            r2 = R2Client.from_runtime_identity(
                settings.r2,
                settings.identities,
                R2RuntimePurpose.INGESTION,
                credential_values=credentials,
            )
            source_report = upload_immutable_source_snapshot(
                client=r2,
                snapshot=snapshot,
                manifest=manifest,
                preflight=preflight,
            )
            validation_by_file = {item.file_name: item for item in context.datasets}
            uploaded_datasets: list[DatasetUploadContext] = []
            for source in snapshot.files:
                planned = validation_by_file[source.file_name]
                report = process_dataset_file(
                    source.path,
                    dataset=contract.by_file_name[source.file_name],
                    output_root=self._output_root,
                    source_release_id=context.source_release_id,
                    ingestion_batch_id=context.ingestion_batch_id,
                    dataset_run_id=planned.dataset_run_id,
                    source_object_id=planned.source_object_id,
                    source_object_sha256=source.sha256,
                    clock=FrozenClock(context.ingested_at),
                    trace_id=context.trace_id,
                )
                if report.raw_artifact is None:
                    raise AirflowIngestionTaskError()
                raw = _upload_artifact(r2, report.raw_artifact, output_root=self._output_root)
                quarantine = tuple(
                    _upload_artifact(r2, artifact, output_root=self._output_root)
                    for artifact in report.quarantine_artifacts
                )
                uploaded_datasets.append(
                    DatasetUploadContext(
                        validation=planned,
                        observed_rows=report.observed_rows,
                        new_rows=report.new_rows,
                        replay_rows=report.replay_rows,
                        duplicate_rows=report.duplicate_rows,
                        rejected_rows=report.rejected_rows,
                        parse_failed_rows=report.parse_failed_rows,
                        raw_artifact=raw,
                        quarantine_artifacts=quarantine,
                    )
                )
            return UploadedIngestionContext(
                validation=context,
                source_objects_uploaded=source_report.uploaded_objects,
                source_objects_replayed=source_report.replayed_objects,
                source_objects_verified=source_report.verified_objects,
                datasets=tuple(uploaded_datasets),
            )
        except AirflowIngestionTaskError:
            raise
        except Exception:
            raise AirflowIngestionTaskError() from None

    def copy_to_bronze(self, context: UploadedIngestionContext) -> BronzeIngestionResult:
        settings = load_settings()
        credentials = load_environment_values()
        ingestion_identity = next(
            item
            for item in settings.identities.snowflake_services
            if item.service is ServiceName.INGESTION
        )
        transform_identity = next(
            item
            for item in settings.identities.snowflake_services
            if item.service is ServiceName.TRANSFORM
        )
        ingest: SnowflakeClient | None = None
        transform: SnowflakeClient | None = None
        warehouse_suspended = False
        try:
            ingest = SnowflakeClient.connect_service(
                settings.snowflake,
                ingestion_identity,
                credential_values=credentials,
            )
            transform = SnowflakeClient.connect_service(
                settings.snowflake,
                transform_identity,
                credential_values=credentials,
            )
            r2 = R2Client.from_runtime_identity(
                settings.r2,
                settings.identities,
                R2RuntimePurpose.INGESTION,
                credential_values=credentials,
            )
            history = SnowflakeBronzeLoadHistoryRepository(ingest)
            copier = BronzeCopyService(
                ingest, history, clock=FrozenClock(context.validation.ingested_at)
            )
            contract = load_olist_contract()
            inputs: list[DatasetReconciliationInput] = []
            results: list[BronzeDatasetResult] = []
            durations: dict[str, float] = {}
            for item in context.datasets:
                started_at = monotonic()
                dataset = contract.by_file_name[item.validation.file_name]
                copied = copier.copy(
                    dataset=dataset,
                    object_key=item.raw_artifact.object_key,
                    object_sha256=item.raw_artifact.sha256,
                    source_release_id=context.validation.source_release_id,
                    ingestion_batch_id=context.validation.ingestion_batch_id,
                    dataset_run_id=item.validation.dataset_run_id,
                    attempt_id=item.validation.attempt_id,
                    trace_id=context.validation.trace_id,
                )
                bronze_rows, distinct_hashes = _bronze_counts(
                    transform,
                    database=settings.snowflake.database,
                    dataset_name=item.validation.dataset_name,
                    batch_id=context.validation.ingestion_batch_id,
                )
                raw_hash, raw_bytes = r2.download_sha256(item.raw_artifact.object_key)
                source_key = (
                    f"source/olist/{context.validation.source_release_id}/"
                    f"{item.validation.file_name}"
                )
                source_hash, _ = r2.download_sha256(source_key)
                inputs.append(
                    DatasetReconciliationInput(
                        dataset_name=item.validation.dataset_name,
                        source_observed_rows=item.observed_rows,
                        source_new_rows=item.new_rows,
                        source_replay_rows=item.replay_rows,
                        source_duplicate_rows=item.duplicate_rows,
                        source_rejected_rows=item.rejected_rows,
                        source_parse_failed_rows=item.parse_failed_rows,
                        local_source_sha256=item.validation.source_sha256,
                        r2_source_sha256=source_hash,
                        local_raw_rows=item.raw_artifact.row_count,
                        local_raw_size_bytes=item.raw_artifact.size_bytes,
                        local_raw_sha256=item.raw_artifact.sha256,
                        r2_raw_size_bytes=raw_bytes,
                        r2_raw_sha256=raw_hash,
                        copy_rows_loaded=copied.rows_loaded,
                        copy_replay=copied.status is BronzeLoadStatus.REPLAY_SKIPPED,
                        bronze_batch_rows=bronze_rows,
                        bronze_distinct_record_hashes=distinct_hashes,
                    )
                )
                results.append(
                    BronzeDatasetResult(
                        dataset_name=item.validation.dataset_name,
                        copy_status=copied.status,
                        query_id=copied.query_id,
                        rows_loaded=copied.rows_loaded,
                        bronze_rows=bronze_rows,
                        distinct_record_hashes=distinct_hashes,
                    )
                )
                durations[item.validation.dataset_name] = monotonic() - started_at
            reconciliation = reconcile_snapshot(tuple(inputs))
            if not reconciliation.reconciled:
                raise AirflowIngestionTaskError()
            result = BronzeIngestionResult(
                source_release_id=context.validation.source_release_id,
                ingestion_batch_id=context.validation.ingestion_batch_id,
                reconciled=True,
                issue_count=0,
                datasets=tuple(results),
            )
            ingest.suspend_warehouse(settings.snowflake.warehouse)
            warehouse_suspended = True
            result_by_dataset = {item.dataset_name: item for item in result.datasets}
            snapshot = IngestionOperationsSnapshot(
                source_release_id=context.validation.source_release_id,
                ingestion_batch_id=context.validation.ingestion_batch_id,
                run_state="RECONCILED",
                task_error_count=0,
                replayed_object_count=(
                    context.source_objects_replayed
                    + sum(
                        item.copy_status is BronzeLoadStatus.REPLAY_SKIPPED
                        for item in result.datasets
                    )
                ),
                warehouse_suspended=True,
                datasets=tuple(
                    DatasetIngestionMetrics(
                        dataset_name=item.validation.dataset_name,
                        source_rows=item.observed_rows,
                        accepted_rows=item.new_rows + item.replay_rows,
                        quarantined_rows=item.duplicate_rows + item.rejected_rows,
                        parse_failed_rows=item.parse_failed_rows,
                        bronze_rows=result_by_dataset[item.validation.dataset_name].bronze_rows,
                        duration_seconds=durations[item.validation.dataset_name],
                    )
                    for item in context.datasets
                ),
            )
            write_ingestion_operations_artifacts(snapshot, output_root=self._output_root)
            return result
        except AirflowIngestionTaskError:
            raise
        except Exception:
            raise AirflowIngestionTaskError() from None
        finally:
            if transform is not None:
                transform.close()
            if ingest is not None:
                if not warehouse_suspended:
                    with suppress(Exception):
                        ingest.suspend_warehouse(settings.snowflake.warehouse)
                ingest.close()


def execute_airflow_task(
    task_name: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Runtime entrypoint imported only while an Airflow task is executing."""

    return AirflowTaskRouter(LocalAirflowIngestionRunner.from_environment()).execute(
        task_name,
        payload,
    )


def settings_path() -> Path:
    from reviewlens.config import project_root

    return project_root()


def _dataset_validation_context(
    source: DiscoveredFile,
    *,
    source_release_id: str,
    batch_id: str,
    contract_version: str,
    attempt_number: int,
) -> DatasetValidationContext:
    current_source_object_id = source_object_id(
        source_release_id=source_release_id,
        file_name=source.file_name,
        source_object_sha256=source.sha256,
    )
    current_dataset_run_id = dataset_run_id(
        ingestion_batch_id=batch_id,
        source_object_id=current_source_object_id,
        dataset_name=source.dataset_name,
        contract_version=contract_version,
    )
    return DatasetValidationContext(
        dataset_name=source.dataset_name,
        file_name=source.file_name,
        source_sha256=source.sha256,
        source_size_bytes=source.bytes,
        source_rows=source.observed_rows,
        source_object_id=current_source_object_id,
        dataset_run_id=current_dataset_run_id,
        attempt_id=attempt_id(
            dataset_run_id=current_dataset_run_id,
            attempt_number=attempt_number,
        ),
    )


def _privacy_evidence() -> PrivacyPreflightEvidence:
    contract = load_olist_contract()
    return PrivacyPreflightEvidence(
        policy_version="m0-security-privacy-v1",
        raw_data_outside_git=True,
        private_processing_only=True,
        external_ai_transfer_disabled=True,
        public_row_level_evidence_disabled=True,
        restricted_reviews_classified=(
            contract.by_file_name["olist_order_reviews_dataset.csv"].data_class
            is DataClass.RESTRICTED
        ),
        source_privacy_scan_passed=True,
        non_commercial_confirmed=True,
        share_alike_confirmed=True,
        change_notice_confirmed=True,
        no_endorsement_confirmed=True,
    )


def _require_matching_validation(context: ValidatedIngestionContext, release_id: str) -> None:
    expected_names = {dataset.dataset_name for dataset in load_olist_contract().datasets}
    if (
        context.source_release_id != release_id
        or context.ingestion_batch_id != ingestion_batch_id(source_release_id=release_id)
        or {item.dataset_name for item in context.datasets} != expected_names
    ):
        raise AirflowIngestionTaskError()


def _upload_artifact(
    r2: R2Client,
    artifact: ParquetArtifact,
    *,
    output_root: Path,
) -> ArtifactContext:
    path = output_root / Path(artifact.object_key)
    metadata = {
        "artifact-version": "olist-parquet-v1",
        "data-class": "private-derived",
        "immutable": "true",
        "row-count": str(artifact.row_count),
        "sha256": artifact.sha256,
    }
    replayed = r2.exists(artifact.object_key)
    if not replayed:
        try:
            r2.put_file_create_only(
                artifact.object_key,
                path,
                content_type="application/vnd.apache.parquet",
                metadata=metadata,
            )
        except R2ObjectAlreadyExistsError:
            replayed = True
    observed_hash, observed_bytes = r2.download_sha256(artifact.object_key)
    head = r2.head(artifact.object_key)
    if (
        observed_hash != artifact.sha256
        or observed_bytes != artifact.size_bytes
        or any(head.metadata.get(key) != value for key, value in metadata.items())
    ):
        raise AirflowIngestionTaskError()
    manifest_path = output_root / Path(artifact.manifest_key)
    manifest_body = manifest_path.read_bytes()
    manifest_sha = hashlib.sha256(manifest_body).hexdigest()
    if not r2.exists(artifact.manifest_key):
        with suppress(R2ObjectAlreadyExistsError):
            r2.put_bytes_create_only(
                artifact.manifest_key,
                manifest_body,
                content_type="application/json",
                metadata={"data-class": "derived-metadata", "sha256": manifest_sha},
            )
    existing_manifest = r2.get_bytes(artifact.manifest_key)
    if hashlib.sha256(existing_manifest).hexdigest() != manifest_sha:
        raise AirflowIngestionTaskError()
    return ArtifactContext(
        object_key=artifact.object_key,
        manifest_key=artifact.manifest_key,
        row_count=artifact.row_count,
        size_bytes=artifact.size_bytes,
        sha256=artifact.sha256,
        replayed=replayed or artifact.replayed,
    )


def _bronze_counts(
    client: SnowflakeClient,
    *,
    database: str,
    dataset_name: str,
    batch_id: str,
) -> tuple[int, int]:
    table = BRONZE_TABLE_BY_DATASET[dataset_name]
    rows = client.query_all(
        f"""SELECT COUNT(*), COUNT(DISTINCT RECORD_HASH)
FROM {database}.BRONZE.{table}
WHERE INGESTION_BATCH_ID = '{batch_id}'""",  # noqa: S608 -- validated identifiers
        operation="Bronze batch reconciliation",
    )
    if len(rows) != 1 or len(rows[0]) != 2:
        raise AirflowIngestionTaskError()
    return int(rows[0][0]), int(rows[0][1])
