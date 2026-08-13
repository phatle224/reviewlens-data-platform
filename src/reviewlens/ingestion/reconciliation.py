"""Metadata-only physical reconciliation from source through R2 and Bronze."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from reviewlens.ingestion.contracts import load_olist_contract


class ReconciliationCode(StrEnum):
    DATASET_SET_MISMATCH = "RECON_DATASET_SET_MISMATCH"
    SOURCE_DISPOSITION_MISMATCH = "RECON_SOURCE_DISPOSITION_MISMATCH"
    SOURCE_ARCHIVE_HASH_MISMATCH = "RECON_SOURCE_ARCHIVE_HASH_MISMATCH"
    RAW_ROW_MISMATCH = "RECON_RAW_ROW_MISMATCH"
    RAW_R2_BYTES_MISMATCH = "RECON_RAW_R2_BYTES_MISMATCH"
    RAW_R2_HASH_MISMATCH = "RECON_RAW_R2_HASH_MISMATCH"
    COPY_ROW_MISMATCH = "RECON_COPY_ROW_MISMATCH"
    BRONZE_ROW_MISMATCH = "RECON_BRONZE_ROW_MISMATCH"
    BRONZE_DUPLICATE_EFFECT = "RECON_BRONZE_DUPLICATE_EFFECT"


class ReconciliationInputError(ValueError):
    code = "RECONCILIATION_INPUT_INVALID"

    def __init__(self) -> None:
        super().__init__(self.code)


@dataclass(frozen=True, slots=True)
class DatasetReconciliationInput:
    dataset_name: str
    source_observed_rows: int
    source_new_rows: int
    source_replay_rows: int
    source_duplicate_rows: int
    source_rejected_rows: int
    source_parse_failed_rows: int
    local_source_sha256: str
    r2_source_sha256: str
    local_raw_rows: int
    local_raw_size_bytes: int
    local_raw_sha256: str
    r2_raw_size_bytes: int
    r2_raw_sha256: str
    copy_rows_loaded: int
    copy_replay: bool
    bronze_batch_rows: int
    bronze_distinct_record_hashes: int


@dataclass(frozen=True, slots=True)
class DatasetReconciliationResult:
    dataset_name: str
    issues: tuple[ReconciliationCode, ...]

    @property
    def reconciled(self) -> bool:
        return not self.issues


@dataclass(frozen=True, slots=True)
class SnapshotReconciliationReport:
    dataset_results: tuple[DatasetReconciliationResult, ...]
    snapshot_issues: tuple[ReconciliationCode, ...]

    @property
    def reconciled(self) -> bool:
        return not self.snapshot_issues and all(
            result.reconciled for result in self.dataset_results
        )

    @property
    def issue_count(self) -> int:
        return len(self.snapshot_issues) + sum(
            len(result.issues) for result in self.dataset_results
        )


def reconcile_snapshot(
    inputs: tuple[DatasetReconciliationInput, ...],
) -> SnapshotReconciliationReport:
    """Require one metadata-only reconciliation input for each Olist dataset."""

    contract = load_olist_contract()
    expected = {dataset.dataset_name for dataset in contract.datasets}
    actual = [item.dataset_name for item in inputs]
    snapshot_issues: list[ReconciliationCode] = []
    if len(actual) != len(set(actual)) or set(actual) != expected:
        snapshot_issues.append(ReconciliationCode.DATASET_SET_MISMATCH)
    results = tuple(
        _reconcile_dataset(item)
        for item in sorted(inputs, key=lambda item: item.dataset_name)
        if item.dataset_name in expected
    )
    return SnapshotReconciliationReport(
        dataset_results=results,
        snapshot_issues=tuple(snapshot_issues),
    )


def _reconcile_dataset(item: DatasetReconciliationInput) -> DatasetReconciliationResult:
    counts = (
        item.source_observed_rows,
        item.source_new_rows,
        item.source_replay_rows,
        item.source_duplicate_rows,
        item.source_rejected_rows,
        item.source_parse_failed_rows,
        item.local_raw_rows,
        item.local_raw_size_bytes,
        item.r2_raw_size_bytes,
        item.copy_rows_loaded,
        item.bronze_batch_rows,
        item.bronze_distinct_record_hashes,
    )
    hashes = (
        item.local_source_sha256,
        item.r2_source_sha256,
        item.local_raw_sha256,
        item.r2_raw_sha256,
    )
    if any(value < 0 for value in counts) or any(
        len(value) != 64 or any(char not in "0123456789abcdef" for char in value)
        for value in hashes
    ):
        raise ReconciliationInputError()
    issues: list[ReconciliationCode] = []
    explained = (
        item.source_new_rows
        + item.source_replay_rows
        + item.source_duplicate_rows
        + item.source_rejected_rows
        + item.source_parse_failed_rows
    )
    if item.source_observed_rows != explained:
        issues.append(ReconciliationCode.SOURCE_DISPOSITION_MISMATCH)
    if item.local_source_sha256 != item.r2_source_sha256:
        issues.append(ReconciliationCode.SOURCE_ARCHIVE_HASH_MISMATCH)
    if item.local_raw_rows != item.source_new_rows:
        issues.append(ReconciliationCode.RAW_ROW_MISMATCH)
    if item.local_raw_size_bytes != item.r2_raw_size_bytes:
        issues.append(ReconciliationCode.RAW_R2_BYTES_MISMATCH)
    if item.local_raw_sha256 != item.r2_raw_sha256:
        issues.append(ReconciliationCode.RAW_R2_HASH_MISMATCH)
    expected_copy_rows = 0 if item.copy_replay else item.local_raw_rows
    if item.copy_rows_loaded != expected_copy_rows:
        issues.append(ReconciliationCode.COPY_ROW_MISMATCH)
    if item.bronze_batch_rows != item.local_raw_rows:
        issues.append(ReconciliationCode.BRONZE_ROW_MISMATCH)
    if item.bronze_distinct_record_hashes != item.bronze_batch_rows:
        issues.append(ReconciliationCode.BRONZE_DUPLICATE_EFFECT)
    return DatasetReconciliationResult(
        dataset_name=item.dataset_name,
        issues=tuple(issues),
    )
