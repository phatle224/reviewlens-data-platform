"""Olist source-ingestion contracts and snapshot identity helpers."""

from reviewlens.ingestion.contracts import SourceContract, load_olist_contract
from reviewlens.ingestion.source import (
    CanonicalSourceManifest,
    DiscoveredSnapshot,
    build_canonical_manifest,
    discover_source_snapshot,
)

__all__ = [
    "CanonicalSourceManifest",
    "DiscoveredSnapshot",
    "SourceContract",
    "build_canonical_manifest",
    "discover_source_snapshot",
    "load_olist_contract",
]
