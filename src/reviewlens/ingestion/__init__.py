"""Olist source-ingestion contracts and snapshot identity helpers."""

from reviewlens.ingestion.contracts import SourceContract, load_olist_contract
from reviewlens.ingestion.csv_stream import ParsedCsvRecord, iter_csv_records
from reviewlens.ingestion.identity import (
    attempt_id,
    dataset_run_id,
    ingestion_batch_id,
    record_id,
    source_object_id,
)
from reviewlens.ingestion.source import (
    CanonicalSourceManifest,
    DiscoveredSnapshot,
    build_canonical_manifest,
    discover_source_snapshot,
)

__all__ = [
    "CanonicalSourceManifest",
    "DiscoveredSnapshot",
    "ParsedCsvRecord",
    "SourceContract",
    "attempt_id",
    "build_canonical_manifest",
    "dataset_run_id",
    "discover_source_snapshot",
    "ingestion_batch_id",
    "iter_csv_records",
    "load_olist_contract",
    "record_id",
    "source_object_id",
]
