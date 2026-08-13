"""Olist source-ingestion contracts and snapshot identity helpers."""

from reviewlens.ingestion.audit import (
    IngestionAuditRepository,
    IngestionLease,
    IngestionState,
    InMemoryIngestionAuditRepository,
)
from reviewlens.ingestion.bronze import (
    BRONZE_TABLE_BY_DATASET,
    BronzeCopyReport,
    BronzeCopyService,
    BronzeLoadEvent,
    BronzeLoadStatus,
    InMemoryBronzeLoadHistoryRepository,
    SnowflakeBronzeLoadHistoryRepository,
    render_bronze_copy_sql,
)
from reviewlens.ingestion.contracts import SourceContract, load_olist_contract
from reviewlens.ingestion.csv_stream import ParsedCsvRecord, iter_csv_records
from reviewlens.ingestion.identity import (
    attempt_id,
    dataset_run_id,
    ingestion_batch_id,
    record_id,
    source_object_id,
)
from reviewlens.ingestion.preflight import (
    PrivacyPreflightEvidence,
    UploadPreflightDecision,
    materialize_approved_completion_manifest,
    run_upload_preflight,
)
from reviewlens.ingestion.processing import DatasetProcessingReport, process_dataset_file
from reviewlens.ingestion.reconciliation import (
    DatasetReconciliationInput,
    SnapshotReconciliationReport,
    reconcile_snapshot,
)
from reviewlens.ingestion.records import (
    RecordDisposition,
    RecordHashTracker,
    canonical_record_hash,
)
from reviewlens.ingestion.source import (
    CanonicalSourceManifest,
    DiscoveredSnapshot,
    build_canonical_manifest,
    discover_source_snapshot,
)
from reviewlens.ingestion.source_upload import SourceUploadReport, upload_immutable_source_snapshot

__all__ = [
    "BRONZE_TABLE_BY_DATASET",
    "BronzeCopyReport",
    "BronzeCopyService",
    "BronzeLoadEvent",
    "BronzeLoadStatus",
    "CanonicalSourceManifest",
    "DatasetProcessingReport",
    "DatasetReconciliationInput",
    "DiscoveredSnapshot",
    "InMemoryBronzeLoadHistoryRepository",
    "InMemoryIngestionAuditRepository",
    "IngestionAuditRepository",
    "IngestionLease",
    "IngestionState",
    "ParsedCsvRecord",
    "PrivacyPreflightEvidence",
    "RecordDisposition",
    "RecordHashTracker",
    "SnapshotReconciliationReport",
    "SnowflakeBronzeLoadHistoryRepository",
    "SourceContract",
    "SourceUploadReport",
    "UploadPreflightDecision",
    "attempt_id",
    "build_canonical_manifest",
    "canonical_record_hash",
    "dataset_run_id",
    "discover_source_snapshot",
    "ingestion_batch_id",
    "iter_csv_records",
    "load_olist_contract",
    "materialize_approved_completion_manifest",
    "process_dataset_file",
    "reconcile_snapshot",
    "record_id",
    "render_bronze_copy_sql",
    "run_upload_preflight",
    "source_object_id",
    "upload_immutable_source_snapshot",
]
