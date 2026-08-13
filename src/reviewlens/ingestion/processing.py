"""Streaming validation, replay selection and private Parquet materialization."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from reviewlens.clock import Clock
from reviewlens.ingestion.audit import IngestionAuditRepository, IngestionLease
from reviewlens.ingestion.contracts import DatasetContract
from reviewlens.ingestion.csv_stream import CsvStreamError, ParsedCsvRecord, iter_csv_records
from reviewlens.ingestion.identity import record_id
from reviewlens.ingestion.parquet import (
    ParquetArtifact,
    QuarantineParquetPartitionWriter,
    QuarantineParquetRecord,
    RawParquetPartitionWriter,
    RawParquetRecord,
)
from reviewlens.ingestion.records import (
    RecordDisposition,
    RecordHashTracker,
    canonical_record_hash,
)
from reviewlens.ingestion.validation import validate_parsed_record

DUPLICATE_RECORD_CODE = "DUPLICATE_RECORD"


@dataclass(frozen=True, slots=True)
class DatasetProcessingReport:
    dataset_name: str
    source_file_name: str
    observed_rows: int
    new_rows: int
    replay_rows: int
    duplicate_rows: int
    rejected_rows: int
    parse_failed_rows: int
    file_failures: int
    raw_artifact: ParquetArtifact | None
    quarantine_artifacts: tuple[ParquetArtifact, ...]

    @property
    def reconciled(self) -> bool:
        return self.observed_rows == (
            self.new_rows
            + self.replay_rows
            + self.duplicate_rows
            + self.rejected_rows
            + self.parse_failed_rows
        )


def process_dataset_file(
    path: Path,
    *,
    dataset: DatasetContract,
    output_root: Path,
    source_release_id: str,
    ingestion_batch_id: str,
    dataset_run_id: str,
    source_object_id: str,
    source_object_sha256: str,
    clock: Clock,
    existing_record_hashes: Iterable[str] = (),
    row_group_size: int = 10_000,
    audit_repository: IngestionAuditRepository | None = None,
    audit_lease: IngestionLease | None = None,
    trace_id: str = "ingestion-local",
) -> DatasetProcessingReport:
    """Process one source file with bounded writers and exact disposition counts.

    The injected clock must represent the persisted batch timestamp and therefore
    return the same instant on retry; runtime wall-clock drift must not alter an
    immutable partition.
    """

    if path.name != dataset.file_name or not path.is_file():
        raise ValueError("dataset source file does not match contract")
    if (audit_repository is None) != (audit_lease is None):
        raise ValueError("audit repository and lease must be supplied together")
    ingested_at = clock.now()
    tracker = RecordHashTracker(existing_record_hashes)
    raw_writer = RawParquetPartitionWriter(
        dataset=dataset,
        output_root=output_root,
        source_release_id=source_release_id,
        ingestion_batch_id=ingestion_batch_id,
        row_group_size=row_group_size,
    )
    quarantine_writers: dict[str, QuarantineParquetPartitionWriter] = {}
    observed = new = replay = duplicate = rejected = parse_failed = file_failures = 0
    try:
        try:
            for parsed in iter_csv_records(path, expected_header=dataset.expected_header):
                observed += 1
                outcome = validate_parsed_record(parsed, dataset=dataset)
                if not outcome.accepted or outcome.record is None:
                    rejected += 1
                    error_codes = tuple(error.code.value for error in outcome.errors)
                    _quarantine_writer(
                        quarantine_writers,
                        primary_code=error_codes[0],
                        dataset=dataset,
                        output_root=output_root,
                        ingestion_batch_id=ingestion_batch_id,
                        row_group_size=row_group_size,
                    ).append(
                        _row_quarantine_record(
                            parsed,
                            dataset=dataset,
                            source_release_id=source_release_id,
                            ingestion_batch_id=ingestion_batch_id,
                            dataset_run_id=dataset_run_id,
                            source_object_id=source_object_id,
                            source_object_sha256=source_object_sha256,
                            ingested_at=ingested_at,
                            error_codes=error_codes,
                            error_columns=tuple(error.column_name for error in outcome.errors),
                        )
                    )
                    continue

                values = outcome.record.as_mapping()
                record_hash = canonical_record_hash(dataset=dataset, values=values)
                disposition = tracker.observe(record_hash)
                if disposition is RecordDisposition.REPLAY:
                    replay += 1
                    continue
                if disposition is RecordDisposition.DUPLICATE:
                    duplicate += 1
                    _quarantine_writer(
                        quarantine_writers,
                        primary_code=DUPLICATE_RECORD_CODE,
                        dataset=dataset,
                        output_root=output_root,
                        ingestion_batch_id=ingestion_batch_id,
                        row_group_size=row_group_size,
                    ).append(
                        _row_quarantine_record(
                            parsed,
                            dataset=dataset,
                            source_release_id=source_release_id,
                            ingestion_batch_id=ingestion_batch_id,
                            dataset_run_id=dataset_run_id,
                            source_object_id=source_object_id,
                            source_object_sha256=source_object_sha256,
                            ingested_at=ingested_at,
                            error_codes=(DUPLICATE_RECORD_CODE,),
                            error_columns=dataset.identity_fields,
                        )
                    )
                    continue

                new += 1
                raw_writer.append(
                    RawParquetRecord(
                        source_release_id=source_release_id,
                        ingestion_batch_id=ingestion_batch_id,
                        dataset_run_id=dataset_run_id,
                        source_file_name=dataset.file_name,
                        source_row_number=parsed.source_row_number,
                        source_object_sha256=source_object_sha256,
                        record_hash=record_hash,
                        ingested_at=ingested_at,
                        schema_version=dataset.dataset_name + ":olist-source-v1",
                        values=values,
                    )
                )
        except CsvStreamError as error:
            file_failures += 1
            is_data_row = error.source_row_number is not None and error.source_row_number >= 2
            if is_data_row:
                observed += 1
                parse_failed += 1
            code = error.code.value
            _quarantine_writer(
                quarantine_writers,
                primary_code=code,
                dataset=dataset,
                output_root=output_root,
                ingestion_batch_id=ingestion_batch_id,
                row_group_size=row_group_size,
            ).append(
                QuarantineParquetRecord(
                    source_release_id=source_release_id,
                    ingestion_batch_id=ingestion_batch_id,
                    dataset_run_id=dataset_run_id,
                    source_file_name=dataset.file_name,
                    source_object_sha256=source_object_sha256,
                    source_row_number=error.source_row_number,
                    raw_reference=f"{source_object_id}#row={error.source_row_number or 0}",
                    error_code=code,
                    error_codes=(code,),
                    error_columns=(),
                    ingested_at=ingested_at,
                    schema_version=dataset.dataset_name + ":olist-source-v1",
                )
            )

        raw_artifact = raw_writer.close()
        quarantine_artifacts = tuple(
            artifact
            for code in sorted(quarantine_writers)
            if (artifact := quarantine_writers[code].close()) is not None
        )
    except BaseException:
        raw_writer.abort()
        for writer in quarantine_writers.values():
            writer.abort()
        raise

    report = DatasetProcessingReport(
        dataset_name=dataset.dataset_name,
        source_file_name=dataset.file_name,
        observed_rows=observed,
        new_rows=new,
        replay_rows=replay,
        duplicate_rows=duplicate,
        rejected_rows=rejected,
        parse_failed_rows=parse_failed,
        file_failures=file_failures,
        raw_artifact=raw_artifact,
        quarantine_artifacts=quarantine_artifacts,
    )
    if not report.reconciled:
        raise RuntimeError("INGESTION_RECONCILIATION_FAILED")
    if audit_repository is not None and audit_lease is not None:
        audit_repository.record_source_file(
            audit_lease,
            idempotency_key=dataset.file_name,
            source_release_id=source_release_id,
            ingestion_batch_id=ingestion_batch_id,
            source_file_name=dataset.file_name,
            source_object_sha256=source_object_sha256,
            source_size_bytes=path.stat().st_size,
            physical_row_count=observed,
            accepted_row_count=new + replay,
            rejected_row_count=rejected + duplicate,
            parse_failed_row_count=parse_failed,
            status="QUARANTINED"
            if rejected + duplicate + parse_failed + file_failures
            else "VALIDATED",
            trace_id=trace_id,
        )
    return report


def _quarantine_writer(
    writers: dict[str, QuarantineParquetPartitionWriter],
    *,
    primary_code: str,
    dataset: DatasetContract,
    output_root: Path,
    ingestion_batch_id: str,
    row_group_size: int,
) -> QuarantineParquetPartitionWriter:
    writer = writers.get(primary_code)
    if writer is None:
        writer = QuarantineParquetPartitionWriter(
            dataset_name=dataset.dataset_name,
            output_root=output_root,
            ingestion_batch_id=ingestion_batch_id,
            error_code=primary_code,
            row_group_size=row_group_size,
        )
        writers[primary_code] = writer
    return writer


def _row_quarantine_record(
    parsed: ParsedCsvRecord,
    *,
    dataset: DatasetContract,
    source_release_id: str,
    ingestion_batch_id: str,
    dataset_run_id: str,
    source_object_id: str,
    source_object_sha256: str,
    ingested_at: datetime,
    error_codes: tuple[str, ...],
    error_columns: tuple[str, ...],
) -> QuarantineParquetRecord:
    payload = json.dumps(
        dict(zip(dataset.expected_header, parsed.values, strict=True)),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    current_record_id = (
        record_id(
            source_object_id=source_object_id,
            source_row_number=parsed.source_row_number,
            byte_start=parsed.byte_start,
            byte_end=parsed.byte_end,
        )
        if parsed.byte_end > parsed.byte_start
        else None
    )
    return QuarantineParquetRecord(
        source_release_id=source_release_id,
        ingestion_batch_id=ingestion_batch_id,
        dataset_run_id=dataset_run_id,
        source_file_name=dataset.file_name,
        source_object_sha256=source_object_sha256,
        source_row_number=parsed.source_row_number,
        byte_start=parsed.byte_start,
        byte_end=parsed.byte_end,
        record_id=current_record_id,
        raw_reference=f"{source_object_id}#bytes={parsed.byte_start}:{parsed.byte_end}",
        error_code=error_codes[0],
        error_codes=error_codes,
        error_columns=error_columns,
        ingested_at=ingested_at,
        schema_version=dataset.dataset_name + ":olist-source-v1",
        raw_payload=payload,
    )
