"""Fail-closed M3 full-refresh versus incremental-equivalence evidence."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import StrEnum

from reviewlens.warehouse.candidates import CandidateLayer
from reviewlens.warehouse.gold_candidate import GOLD_CANDIDATE_OUTPUT_LOGICAL_NAMES
from reviewlens.warehouse.releases import SILVER_RELEASE_LOGICAL_NAMES
from reviewlens.warehouse.semantic import SEMANTIC_CATALOG_VERSION

EQUIVALENCE_CONTRACT_VERSION = "reviewlens-m3-equivalence-v1"

_HASH = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Z][A-Z0-9_]{0,254}$")
_PHYSICAL_NAMESPACE = re.compile(r"^C_[A-F0-9]{64}__")
_SOURCE_RELEASE = re.compile(r"^olist_[0-9a-f]{64}$")
_INGESTION_BATCH = re.compile(r"^batch_[0-9a-f]{64}$")
_SENSITIVE = re.compile(r"(?:SECRET|TOKEN|PASSWORD|PRIVATE_KEY|API_KEY)", re.IGNORECASE)


class WarehouseEquivalenceError(ValueError):
    """Sanitized equivalence error with no relation, count or hash disclosure."""

    code = "WAREHOUSE_EQUIVALENCE_INVALID"

    def __init__(self) -> None:
        super().__init__(self.code)


class CandidateBuildMode(StrEnum):
    FULL_REFRESH = "FULL_REFRESH"
    INCREMENTAL = "INCREMENTAL"


class EquivalenceMismatchKind(StrEnum):
    ROW_COUNT = "ROW_COUNT"
    CONTENT_HASH = "CONTENT_HASH"


@dataclass(frozen=True, slots=True, order=True)
class RelationFingerprint:
    """One aggregate-only, no-row-content fingerprint for a candidate relation."""

    layer: CandidateLayer
    logical_name: str
    row_count: int
    content_sha256: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.layer, CandidateLayer)
            or _IDENTIFIER.fullmatch(self.logical_name) is None
            or _PHYSICAL_NAMESPACE.match(self.logical_name) is not None
            or _SENSITIVE.search(self.logical_name) is not None
            or type(self.row_count) is not int
            or self.row_count < 0
            or _HASH.fullmatch(self.content_sha256) is None
        ):
            raise WarehouseEquivalenceError()

    @property
    def key(self) -> tuple[str, str]:
        return (self.layer.value, self.logical_name)


@dataclass(frozen=True, slots=True)
class CandidateEquivalenceSnapshot:
    """Aggregate-only evidence from one isolated candidate build."""

    candidate_id: str
    build_mode: CandidateBuildMode
    source_release_id: str
    ingestion_batch_id: str
    semantic_contract_version: str
    relation_fingerprints: tuple[RelationFingerprint, ...]
    contract_version: str = EQUIVALENCE_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if (
            _HASH.fullmatch(self.candidate_id) is None
            or not isinstance(self.build_mode, CandidateBuildMode)
            or _SOURCE_RELEASE.fullmatch(self.source_release_id) is None
            or _INGESTION_BATCH.fullmatch(self.ingestion_batch_id) is None
            or self.semantic_contract_version != SEMANTIC_CATALOG_VERSION
            or self.contract_version != EQUIVALENCE_CONTRACT_VERSION
            or not self.relation_fingerprints
            or tuple(sorted(self.relation_fingerprints)) != self.relation_fingerprints
            or len({item.key for item in self.relation_fingerprints})
            != len(self.relation_fingerprints)
            or {item.key for item in self.relation_fingerprints} != _EXPECTED_RELATION_KEYS
        ):
            raise WarehouseEquivalenceError()


@dataclass(frozen=True, slots=True, order=True)
class EquivalenceMismatch:
    """A relation-level mismatch that intentionally excludes source values."""

    layer: CandidateLayer
    logical_name: str
    kind: EquivalenceMismatchKind

    def __post_init__(self) -> None:
        if (
            not isinstance(self.layer, CandidateLayer)
            or _IDENTIFIER.fullmatch(self.logical_name) is None
            or _SENSITIVE.search(self.logical_name) is not None
            or not isinstance(self.kind, EquivalenceMismatchKind)
        ):
            raise WarehouseEquivalenceError()


@dataclass(frozen=True, slots=True)
class EquivalenceReport:
    """Deterministic full-versus-incremental comparison result."""

    report_id: str
    full_refresh_candidate_id: str
    incremental_candidate_id: str
    source_release_id: str
    ingestion_batch_id: str
    semantic_contract_version: str
    mismatches: tuple[EquivalenceMismatch, ...]
    contract_version: str = EQUIVALENCE_CONTRACT_VERSION

    def __post_init__(self) -> None:
        expected = _report_digest(
            full_refresh_candidate_id=self.full_refresh_candidate_id,
            incremental_candidate_id=self.incremental_candidate_id,
            source_release_id=self.source_release_id,
            ingestion_batch_id=self.ingestion_batch_id,
            semantic_contract_version=self.semantic_contract_version,
            mismatches=self.mismatches,
        )
        if (
            _HASH.fullmatch(self.report_id) is None
            or self.report_id != expected
            or _HASH.fullmatch(self.full_refresh_candidate_id) is None
            or _HASH.fullmatch(self.incremental_candidate_id) is None
            or self.full_refresh_candidate_id == self.incremental_candidate_id
            or _SOURCE_RELEASE.fullmatch(self.source_release_id) is None
            or _INGESTION_BATCH.fullmatch(self.ingestion_batch_id) is None
            or self.semantic_contract_version != SEMANTIC_CATALOG_VERSION
            or self.contract_version != EQUIVALENCE_CONTRACT_VERSION
            or tuple(sorted(self.mismatches)) != self.mismatches
            or len(set(self.mismatches)) != len(self.mismatches)
        ):
            raise WarehouseEquivalenceError()

    @property
    def equivalent(self) -> bool:
        return not self.mismatches


_EXPECTED_RELATION_KEYS = frozenset(
    {(CandidateLayer.SILVER.value, logical_name) for logical_name in SILVER_RELEASE_LOGICAL_NAMES}
    | {
        (CandidateLayer.GOLD.value, logical_name)
        for logical_name in GOLD_CANDIDATE_OUTPUT_LOGICAL_NAMES
    }
)


def compare_full_refresh_to_incremental(
    *,
    full_refresh: CandidateEquivalenceSnapshot,
    incremental: CandidateEquivalenceSnapshot,
) -> EquivalenceReport:
    """Compare the exact M3 release relation set without exposing row content."""

    if (
        not isinstance(full_refresh, CandidateEquivalenceSnapshot)
        or not isinstance(incremental, CandidateEquivalenceSnapshot)
        or full_refresh.build_mode is not CandidateBuildMode.FULL_REFRESH
        or incremental.build_mode is not CandidateBuildMode.INCREMENTAL
        or full_refresh.candidate_id == incremental.candidate_id
        or full_refresh.source_release_id != incremental.source_release_id
        or full_refresh.ingestion_batch_id != incremental.ingestion_batch_id
        or full_refresh.semantic_contract_version != incremental.semantic_contract_version
    ):
        raise WarehouseEquivalenceError()

    full_by_key = {item.key: item for item in full_refresh.relation_fingerprints}
    incremental_by_key = {item.key: item for item in incremental.relation_fingerprints}
    mismatches: list[EquivalenceMismatch] = []
    for layer_name, logical_name in sorted(_EXPECTED_RELATION_KEYS):
        full_relation = full_by_key[(layer_name, logical_name)]
        incremental_relation = incremental_by_key[(layer_name, logical_name)]
        if full_relation.row_count != incremental_relation.row_count:
            mismatches.append(
                EquivalenceMismatch(
                    layer=CandidateLayer(layer_name),
                    logical_name=logical_name,
                    kind=EquivalenceMismatchKind.ROW_COUNT,
                )
            )
        if full_relation.content_sha256 != incremental_relation.content_sha256:
            mismatches.append(
                EquivalenceMismatch(
                    layer=CandidateLayer(layer_name),
                    logical_name=logical_name,
                    kind=EquivalenceMismatchKind.CONTENT_HASH,
                )
            )
    ordered_mismatches = tuple(sorted(mismatches))
    return EquivalenceReport(
        report_id=_report_digest(
            full_refresh_candidate_id=full_refresh.candidate_id,
            incremental_candidate_id=incremental.candidate_id,
            source_release_id=full_refresh.source_release_id,
            ingestion_batch_id=full_refresh.ingestion_batch_id,
            semantic_contract_version=full_refresh.semantic_contract_version,
            mismatches=ordered_mismatches,
        ),
        full_refresh_candidate_id=full_refresh.candidate_id,
        incremental_candidate_id=incremental.candidate_id,
        source_release_id=full_refresh.source_release_id,
        ingestion_batch_id=full_refresh.ingestion_batch_id,
        semantic_contract_version=full_refresh.semantic_contract_version,
        mismatches=ordered_mismatches,
    )


def _report_digest(
    *,
    full_refresh_candidate_id: str,
    incremental_candidate_id: str,
    source_release_id: str,
    ingestion_batch_id: str,
    semantic_contract_version: str,
    mismatches: tuple[EquivalenceMismatch, ...],
) -> str:
    payload = {
        "contract_version": EQUIVALENCE_CONTRACT_VERSION,
        "full_refresh_candidate_id": full_refresh_candidate_id,
        "incremental_candidate_id": incremental_candidate_id,
        "ingestion_batch_id": ingestion_batch_id,
        "mismatches": [
            {"kind": item.kind.value, "layer": item.layer.value, "logical_name": item.logical_name}
            for item in mismatches
        ],
        "semantic_contract_version": semantic_contract_version,
        "source_release_id": source_release_id,
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode(
            "ascii"
        )
    ).hexdigest()
