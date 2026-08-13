"""Metadata-only M2 ingestion metrics and deterministic alert evaluation."""

from __future__ import annotations

import json
import os
from enum import StrEnum
from pathlib import Path
from tempfile import NamedTemporaryFile

from prometheus_client import CollectorRegistry, Gauge, Histogram, generate_latest
from pydantic import BaseModel, ConfigDict, Field, model_validator

from reviewlens.ingestion.contracts import load_olist_contract


class IngestionAlertCode(StrEnum):
    RECONCILIATION_FAILED = "INGESTION_RECONCILIATION_FAILED"
    QUARANTINE_RATE_HIGH = "INGESTION_QUARANTINE_RATE_HIGH"
    TASK_ERRORS_PRESENT = "INGESTION_TASK_ERRORS_PRESENT"
    WAREHOUSE_CLEANUP_REQUIRED = "INGESTION_WAREHOUSE_CLEANUP_REQUIRED"


class DatasetIngestionMetrics(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    dataset_name: str
    source_rows: int = Field(ge=0)
    accepted_rows: int = Field(ge=0)
    quarantined_rows: int = Field(ge=0)
    parse_failed_rows: int = Field(ge=0)
    bronze_rows: int = Field(ge=0)
    duration_seconds: float = Field(ge=0)

    @model_validator(mode="after")
    def require_explained_rows(self) -> DatasetIngestionMetrics:
        if self.source_rows != (
            self.accepted_rows + self.quarantined_rows + self.parse_failed_rows
        ):
            raise ValueError("dataset metrics do not explain source rows")
        return self


class IngestionOperationsSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_release_id: str = Field(pattern=r"^olist_[0-9a-f]{64}$")
    ingestion_batch_id: str = Field(pattern=r"^batch_[0-9a-f]{64}$")
    run_state: str = Field(pattern=r"^[A-Z][A-Z0-9_]{1,31}$")
    task_error_count: int = Field(ge=0)
    replayed_object_count: int = Field(ge=0)
    warehouse_suspended: bool
    datasets: tuple[DatasetIngestionMetrics, ...] = Field(min_length=9, max_length=9)

    @model_validator(mode="after")
    def require_exact_datasets(self) -> IngestionOperationsSnapshot:
        expected = {item.dataset_name for item in load_olist_contract().datasets}
        actual = [item.dataset_name for item in self.datasets]
        if len(actual) != len(set(actual)) or set(actual) != expected:
            raise ValueError("operations snapshot must contain exact Olist datasets")
        return self

    @property
    def total_source_rows(self) -> int:
        return sum(item.source_rows for item in self.datasets)

    @property
    def total_quarantined_rows(self) -> int:
        return sum(item.quarantined_rows + item.parse_failed_rows for item in self.datasets)


def evaluate_ingestion_alerts(
    snapshot: IngestionOperationsSnapshot,
    *,
    quarantine_rate_threshold: float = 0.05,
) -> tuple[IngestionAlertCode, ...]:
    if not 0 <= quarantine_rate_threshold <= 1:
        raise ValueError("quarantine rate threshold must be between zero and one")
    alerts: list[IngestionAlertCode] = []
    if snapshot.run_state != "RECONCILED" or any(
        item.accepted_rows != item.bronze_rows for item in snapshot.datasets
    ):
        alerts.append(IngestionAlertCode.RECONCILIATION_FAILED)
    quarantine_rate = (
        snapshot.total_quarantined_rows / snapshot.total_source_rows
        if snapshot.total_source_rows
        else 0.0
    )
    if quarantine_rate > quarantine_rate_threshold:
        alerts.append(IngestionAlertCode.QUARANTINE_RATE_HIGH)
    if snapshot.task_error_count:
        alerts.append(IngestionAlertCode.TASK_ERRORS_PRESENT)
    if not snapshot.warehouse_suspended:
        alerts.append(IngestionAlertCode.WAREHOUSE_CLEANUP_REQUIRED)
    return tuple(alerts)


def build_ingestion_metrics_payload(snapshot: IngestionOperationsSnapshot) -> bytes:
    """Render a bounded per-run registry without raw values or high-cardinality IDs."""

    registry = CollectorRegistry()
    rows = Gauge(
        "reviewlens_ingestion_rows",
        "M2 ingestion rows by dataset and explained outcome.",
        ("dataset", "outcome"),
        registry=registry,
    )
    duration = Histogram(
        "reviewlens_ingestion_dataset_duration_seconds",
        "M2 dataset processing duration.",
        ("dataset",),
        registry=registry,
        buckets=(0.1, 1, 5, 15, 30, 60, 300, 900),
    )
    errors = Gauge(
        "reviewlens_ingestion_task_errors",
        "Sanitized task errors in this ingestion run.",
        registry=registry,
    )
    replayed = Gauge(
        "reviewlens_ingestion_replayed_objects",
        "Objects verified as immutable replays in this run.",
        registry=registry,
    )
    reconciled = Gauge(
        "reviewlens_ingestion_reconciled",
        "Whether this run reconciled source to Bronze.",
        registry=registry,
    )
    warehouse_suspended = Gauge(
        "reviewlens_ingestion_warehouse_suspended",
        "Whether warehouse cleanup was confirmed.",
        registry=registry,
    )
    for item in snapshot.datasets:
        values = {
            "source": item.source_rows,
            "accepted": item.accepted_rows,
            "quarantined": item.quarantined_rows,
            "parse_failed": item.parse_failed_rows,
            "bronze": item.bronze_rows,
        }
        for outcome, value in values.items():
            rows.labels(dataset=item.dataset_name, outcome=outcome).set(value)
        duration.labels(dataset=item.dataset_name).observe(item.duration_seconds)
    errors.set(snapshot.task_error_count)
    replayed.set(snapshot.replayed_object_count)
    reconciled.set(
        snapshot.run_state == "RECONCILED"
        and all(item.accepted_rows == item.bronze_rows for item in snapshot.datasets)
    )
    warehouse_suspended.set(snapshot.warehouse_suspended)
    rendered = generate_latest(registry)
    stable_lines = [line for line in rendered.splitlines() if b"_created" not in line]
    return b"\n".join(stable_lines) + b"\n"


def write_ingestion_operations_artifacts(
    snapshot: IngestionOperationsSnapshot,
    *,
    output_root: Path,
) -> tuple[Path, Path]:
    """Atomically publish local metadata-only metrics and stable alert codes."""

    if output_root.is_symlink():
        raise ValueError("operations output root must not be a symlink")
    operations_root = output_root / "operations"
    operations_root.mkdir(parents=True, exist_ok=True)
    if operations_root.is_symlink():
        raise ValueError("operations output directory must not be a symlink")
    metrics_path = operations_root / "ingestion.prom"
    alerts_path = operations_root / "ingestion-alerts.json"
    alerts_payload = (
        json.dumps(
            {
                "schema_version": "reviewlens-ingestion-alerts-v1",
                "alerts": [item.value for item in evaluate_ingestion_alerts(snapshot)],
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )
    _atomic_write(metrics_path, build_ingestion_metrics_payload(snapshot))
    _atomic_write(alerts_path, alerts_payload)
    return metrics_path, alerts_path


def _atomic_write(target: Path, payload: bytes) -> None:
    temporary: Path | None = None
    try:
        with NamedTemporaryFile(dir=target.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
