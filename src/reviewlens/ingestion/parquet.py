"""Typed, create-only Parquet artifacts for private raw and quarantine zones."""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import TracebackType
from typing import Any
from uuid import uuid4

import pyarrow as pa
import pyarrow.parquet as pq

from reviewlens.ingestion.contracts import DatasetContract, LogicalType
from reviewlens.ingestion.validation import ValidatedValue

PARQUET_ARTIFACT_VERSION = "olist-parquet-v1"
PARQUET_COMPRESSION = "snappy"
DECIMAL_PRECISION = 38
DECIMAL_SCALE = 18
_SAFE_PARTITION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class ParquetArtifactError(RuntimeError):
    """Sanitized local artifact failure."""

    code = "PARQUET_ARTIFACT_INVALID"

    def __init__(self) -> None:
        super().__init__(self.code)


@dataclass(frozen=True, slots=True)
class RawParquetRecord:
    source_release_id: str
    ingestion_batch_id: str
    dataset_run_id: str
    source_file_name: str
    source_row_number: int
    source_object_sha256: str
    record_hash: str
    ingested_at: datetime
    schema_version: str
    values: Mapping[str, ValidatedValue] = field(repr=False)


@dataclass(frozen=True, slots=True)
class QuarantineParquetRecord:
    source_release_id: str
    ingestion_batch_id: str
    dataset_run_id: str
    source_file_name: str
    source_object_sha256: str
    error_code: str
    error_codes: tuple[str, ...]
    error_columns: tuple[str, ...]
    ingested_at: datetime
    schema_version: str
    source_row_number: int | None = None
    byte_start: int | None = None
    byte_end: int | None = None
    record_id: str | None = None
    raw_reference: str | None = None
    raw_payload: str | None = field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class ParquetArtifact:
    object_key: str
    manifest_key: str
    row_count: int
    size_bytes: int
    sha256: str
    schema_sha256: str
    replayed: bool


class RawParquetPartitionWriter:
    """Incremental raw writer that keeps at most one configured row group in memory."""

    def __init__(
        self,
        *,
        dataset: DatasetContract,
        output_root: Path,
        source_release_id: str,
        ingestion_batch_id: str,
        part_number: int = 0,
        row_group_size: int = 10_000,
    ) -> None:
        _validate_partition_inputs(dataset.dataset_name, source_release_id, ingestion_batch_id)
        if part_number < 0:
            raise ParquetArtifactError()
        object_key = (
            f"raw/{dataset.dataset_name}/source_release_id={source_release_id}/"
            f"batch_id={ingestion_batch_id}/part-{part_number:05d}.parquet"
        )
        self._dataset = dataset
        self._writer = _StreamingArtifactWriter(
            schema=raw_schema(dataset),
            output_root=output_root,
            object_key=object_key,
            row_group_size=row_group_size,
        )

    def append(self, record: RawParquetRecord) -> None:
        self._writer.append(_raw_row(record, dataset=self._dataset))

    def close(self) -> ParquetArtifact | None:
        return self._writer.close()

    def abort(self) -> None:
        self._writer.abort()

    def __enter__(self) -> RawParquetPartitionWriter:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if exc_type is None:
            self.close()
        else:
            self._writer.abort()


class QuarantineParquetPartitionWriter:
    """Incremental quarantine writer for one stable primary error-code partition."""

    def __init__(
        self,
        *,
        dataset_name: str,
        output_root: Path,
        ingestion_batch_id: str,
        error_code: str,
        part_number: int = 0,
        row_group_size: int = 10_000,
    ) -> None:
        _validate_partition_inputs(dataset_name, "placeholder", ingestion_batch_id)
        if _SAFE_PARTITION.fullmatch(error_code) is None or part_number < 0:
            raise ParquetArtifactError()
        object_key = (
            f"quarantine/{dataset_name}/batch_id={ingestion_batch_id}/"
            f"error_code={error_code}/part-{part_number:05d}.parquet"
        )
        self._error_code = error_code
        self._writer = _StreamingArtifactWriter(
            schema=quarantine_schema(),
            output_root=output_root,
            object_key=object_key,
            row_group_size=row_group_size,
        )

    def append(self, record: QuarantineParquetRecord) -> None:
        self._writer.append(_quarantine_row(record, expected_error_code=self._error_code))

    def close(self) -> ParquetArtifact | None:
        return self._writer.close()

    def abort(self) -> None:
        self._writer.abort()


class _StreamingArtifactWriter:
    def __init__(
        self,
        *,
        schema: pa.Schema,
        output_root: Path,
        object_key: str,
        row_group_size: int,
    ) -> None:
        if row_group_size < 1 or output_root.is_symlink():
            raise ParquetArtifactError()
        self._schema = schema
        self._output_root = output_root
        self._object_key = object_key
        self._target = _windows_long_path(output_root / Path(object_key))
        self._target.parent.mkdir(parents=True, exist_ok=True)
        self._temporary = self._target.with_name(f".{self._target.name}.{uuid4().hex}.tmp")
        self._row_group_size = row_group_size
        self._rows: list[dict[str, Any]] = []
        self._parquet_writer: pq.ParquetWriter | None = None
        self._row_count = 0
        self._closed = False

    def append(self, row: dict[str, Any]) -> None:
        if self._closed:
            raise ParquetArtifactError()
        try:
            self._rows.append(row)
            if len(self._rows) >= self._row_group_size:
                self._flush()
        except (ArrowException, OSError, ValueError, TypeError):
            self.abort()
            raise ParquetArtifactError() from None

    def close(self) -> ParquetArtifact | None:
        if self._closed:
            raise ParquetArtifactError()
        self._closed = True
        try:
            self._flush()
            if self._parquet_writer is None:
                return None
            self._parquet_writer.close()  # type: ignore[no-untyped-call]
            self._parquet_writer = None
            digest = _file_sha256(self._temporary)
            replayed = _commit_create_only(self._temporary, self._target, digest=digest)
            size_bytes = self._target.stat().st_size
            schema_digest = hashlib.sha256(self._schema.serialize().to_pybytes()).hexdigest()
            manifest_key = f"{self._object_key}.manifest.json"
            manifest = {
                "artifact_version": PARQUET_ARTIFACT_VERSION,
                "compression": PARQUET_COMPRESSION,
                "format": "parquet",
                "object_key": self._object_key,
                "row_count": self._row_count,
                "schema_sha256": schema_digest,
                "sha256": digest,
                "size_bytes": size_bytes,
            }
            _write_manifest_create_only(
                _windows_long_path(self._output_root / Path(manifest_key)),
                manifest,
            )
            return ParquetArtifact(
                object_key=self._object_key,
                manifest_key=manifest_key,
                row_count=self._row_count,
                size_bytes=size_bytes,
                sha256=digest,
                schema_sha256=schema_digest,
                replayed=replayed,
            )
        except (ArrowException, OSError, ValueError, TypeError):
            raise ParquetArtifactError() from None
        finally:
            self._temporary.unlink(missing_ok=True)

    def abort(self) -> None:
        if self._parquet_writer is not None:
            self._parquet_writer.close()  # type: ignore[no-untyped-call]
            self._parquet_writer = None
        self._closed = True
        self._temporary.unlink(missing_ok=True)

    def _flush(self) -> None:
        if not self._rows:
            return
        self._parquet_writer = _write_batch(
            self._temporary,
            schema=self._schema,
            rows=self._rows,
            writer=self._parquet_writer,
        )
        self._row_count += len(self._rows)
        self._rows.clear()


def raw_schema(dataset: DatasetContract) -> pa.Schema:
    fields = [
        pa.field(column.name, _arrow_type(column.logical_type), nullable=column.nullable)
        for column in dataset.columns
    ]
    fields.extend(
        [
            pa.field("source_release_id", pa.string(), nullable=False),
            pa.field("ingestion_batch_id", pa.string(), nullable=False),
            pa.field("dataset_run_id", pa.string(), nullable=False),
            pa.field("source_file_name", pa.string(), nullable=False),
            pa.field("source_row_number", pa.int64(), nullable=False),
            pa.field("source_object_sha256", pa.string(), nullable=False),
            pa.field("record_hash", pa.string(), nullable=False),
            pa.field("ingested_at", pa.timestamp("us", tz="UTC"), nullable=False),
            pa.field("schema_version", pa.string(), nullable=False),
            pa.field("raw_payload", pa.large_string(), nullable=False),
        ]
    )
    return pa.schema(fields, metadata={b"artifact_version": PARQUET_ARTIFACT_VERSION.encode()})


def quarantine_schema() -> pa.Schema:
    return pa.schema(
        [
            pa.field("source_release_id", pa.string(), nullable=False),
            pa.field("ingestion_batch_id", pa.string(), nullable=False),
            pa.field("dataset_run_id", pa.string(), nullable=False),
            pa.field("source_file_name", pa.string(), nullable=False),
            pa.field("source_object_sha256", pa.string(), nullable=False),
            pa.field("source_row_number", pa.int64()),
            pa.field("byte_start", pa.int64()),
            pa.field("byte_end", pa.int64()),
            pa.field("record_id", pa.string()),
            pa.field("raw_reference", pa.string()),
            pa.field("error_code", pa.string(), nullable=False),
            pa.field("error_codes", pa.list_(pa.string()), nullable=False),
            pa.field("error_columns", pa.list_(pa.string()), nullable=False),
            pa.field("ingested_at", pa.timestamp("us", tz="UTC"), nullable=False),
            pa.field("schema_version", pa.string(), nullable=False),
            pa.field("raw_payload", pa.large_string()),
        ],
        metadata={b"artifact_version": PARQUET_ARTIFACT_VERSION.encode()},
    )


def write_raw_partition(
    records: Iterable[RawParquetRecord],
    *,
    dataset: DatasetContract,
    output_root: Path,
    source_release_id: str,
    ingestion_batch_id: str,
    part_number: int = 0,
    row_group_size: int = 10_000,
) -> ParquetArtifact | None:
    """Write one typed raw partition using bounded row groups and create-only commit."""

    writer = RawParquetPartitionWriter(
        dataset=dataset,
        output_root=output_root,
        source_release_id=source_release_id,
        ingestion_batch_id=ingestion_batch_id,
        part_number=part_number,
        row_group_size=row_group_size,
    )
    try:
        for record in records:
            writer.append(record)
        return writer.close()
    except BaseException:
        writer.abort()
        raise


def write_quarantine_partition(
    records: Iterable[QuarantineParquetRecord],
    *,
    dataset_name: str,
    output_root: Path,
    ingestion_batch_id: str,
    error_code: str,
    part_number: int = 0,
    row_group_size: int = 10_000,
) -> ParquetArtifact | None:
    """Write one error-code partition; callers group failures before invoking it."""

    writer = QuarantineParquetPartitionWriter(
        dataset_name=dataset_name,
        output_root=output_root,
        ingestion_batch_id=ingestion_batch_id,
        error_code=error_code,
        part_number=part_number,
        row_group_size=row_group_size,
    )
    try:
        for record in records:
            writer.append(record)
        return writer.close()
    except BaseException:
        writer.abort()
        raise


def _raw_row(record: RawParquetRecord, *, dataset: DatasetContract) -> dict[str, Any]:
    if set(record.values) != set(dataset.expected_header):
        raise ParquetArtifactError()
    row = {column: record.values[column] for column in dataset.expected_header}
    row.update(
        {
            "source_release_id": record.source_release_id,
            "ingestion_batch_id": record.ingestion_batch_id,
            "dataset_run_id": record.dataset_run_id,
            "source_file_name": record.source_file_name,
            "source_row_number": record.source_row_number,
            "source_object_sha256": record.source_object_sha256,
            "record_hash": record.record_hash,
            "ingested_at": _utc(record.ingested_at),
            "schema_version": record.schema_version,
            "raw_payload": _canonical_payload(record.values),
        }
    )
    return row


def _quarantine_row(
    record: QuarantineParquetRecord,
    *,
    expected_error_code: str,
) -> dict[str, Any]:
    if record.error_code != expected_error_code or expected_error_code not in record.error_codes:
        raise ParquetArtifactError()
    return {
        "source_release_id": record.source_release_id,
        "ingestion_batch_id": record.ingestion_batch_id,
        "dataset_run_id": record.dataset_run_id,
        "source_file_name": record.source_file_name,
        "source_object_sha256": record.source_object_sha256,
        "source_row_number": record.source_row_number,
        "byte_start": record.byte_start,
        "byte_end": record.byte_end,
        "record_id": record.record_id,
        "raw_reference": record.raw_reference,
        "error_code": record.error_code,
        "error_codes": list(record.error_codes),
        "error_columns": list(record.error_columns),
        "ingested_at": _utc(record.ingested_at),
        "schema_version": record.schema_version,
        "raw_payload": record.raw_payload,
    }


def _write_batch(
    temporary: Path,
    *,
    schema: pa.Schema,
    rows: list[dict[str, Any]],
    writer: pq.ParquetWriter | None,
) -> pq.ParquetWriter:
    current = writer or pq.ParquetWriter(  # type: ignore[no-untyped-call]
        temporary,
        schema,
        compression=PARQUET_COMPRESSION,
        use_dictionary=True,
        write_statistics=True,
    )
    current.write_table(  # type: ignore[no-untyped-call]
        pa.Table.from_pylist(rows, schema=schema)
    )
    return current


def _write_manifest_create_only(target: Path, payload: dict[str, Any]) -> None:
    encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if target.read_bytes() != encoded:
            raise ParquetArtifactError()
        return
    temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_bytes(encoded)
        try:
            os.link(temporary, target)
        except FileExistsError:
            if target.read_bytes() != encoded:
                raise ParquetArtifactError() from None
    finally:
        temporary.unlink(missing_ok=True)


def _commit_create_only(temporary: Path, target: Path, *, digest: str) -> bool:
    if target.exists():
        if _file_sha256(target) != digest:
            raise ParquetArtifactError()
        temporary.unlink()
        return True
    try:
        os.link(temporary, target)
    except FileExistsError:
        if _file_sha256(target) != digest:
            raise ParquetArtifactError() from None
        temporary.unlink()
        return True
    temporary.unlink()
    return False


def _arrow_type(logical_type: LogicalType) -> pa.DataType:
    if logical_type is LogicalType.STRING:
        return pa.string()
    if logical_type is LogicalType.INTEGER:
        return pa.int64()
    if logical_type is LogicalType.DECIMAL:
        return pa.decimal128(DECIMAL_PRECISION, DECIMAL_SCALE)
    return pa.timestamp("us")


def _canonical_payload(values: Mapping[str, ValidatedValue]) -> str:
    return json.dumps(
        values,
        default=_json_default,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _json_default(value: object) -> str:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    raise TypeError


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ParquetArtifactError()
    return value.astimezone(UTC)


def _validate_partition_inputs(
    dataset_name: str,
    source_release_id: str,
    ingestion_batch_id: str,
) -> None:
    if any(
        _SAFE_PARTITION.fullmatch(value) is None
        for value in (dataset_name, source_release_id, ingestion_batch_id)
    ):
        raise ParquetArtifactError()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _windows_long_path(path: Path) -> Path:
    """Use the Win32 extended prefix for canonical IDs that exceed MAX_PATH."""

    if os.name != "nt":
        return path
    resolved = path.resolve()
    value = str(resolved)
    if value.startswith("\\\\?\\"):
        return resolved
    return Path(f"\\\\?\\{value}")


try:
    from pyarrow import ArrowException
except ImportError:  # pragma: no cover - compatibility boundary for future Arrow releases
    ArrowException = Exception
