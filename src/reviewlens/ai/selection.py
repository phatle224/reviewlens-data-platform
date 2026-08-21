"""Deterministic, private-only selection for new, changed and reused reviews."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum

from reviewlens.ai.enrichment import DLPDecision, DLPProjection

_SHA256 = frozenset("0123456789abcdef")


class SelectionDisposition(StrEnum):
    NEW = "new"
    CHANGED = "changed"
    REUSED = "reused"
    EXCLUDED_INELIGIBLE = "excluded_ineligible"
    EXCLUDED_DLP = "excluded_dlp"


class EnrichmentSelectionError(ValueError):
    """Fail-closed selection error with no review body or natural ID."""


@dataclass(frozen=True, slots=True)
class ReviewSelectionCandidate:
    review_lineage_sha256: str
    source_record_hash: str
    dlp_projection: DLPProjection
    ai_eligible: bool


@dataclass(frozen=True, slots=True)
class CommittedEnrichment:
    review_lineage_sha256: str
    enrichment_version: str
    source_record_hash: str
    input_sha256: str


@dataclass(frozen=True, slots=True)
class ReviewSelection:
    review_lineage_sha256: str
    opaque_review_reference: str
    source_record_hash: str
    input_sha256: str | None
    disposition: SelectionDisposition


@dataclass(frozen=True, slots=True)
class EnrichmentSelectionPlan:
    enrichment_version: str
    selections: tuple[ReviewSelection, ...]
    selection_sha256: str

    @property
    def to_submit(self) -> tuple[ReviewSelection, ...]:
        return tuple(
            selection
            for selection in self.selections
            if selection.disposition in {SelectionDisposition.NEW, SelectionDisposition.CHANGED}
        )

    @property
    def reused(self) -> tuple[ReviewSelection, ...]:
        return tuple(
            selection
            for selection in self.selections
            if selection.disposition is SelectionDisposition.REUSED
        )


def select_enrichment_reviews(
    *,
    candidates: tuple[ReviewSelectionCandidate, ...],
    committed: tuple[CommittedEnrichment, ...],
    enrichment_version: str,
) -> EnrichmentSelectionPlan:
    """Return a deterministic plan without exposing restricted review content."""

    if not enrichment_version or len(enrichment_version) > 128:
        raise EnrichmentSelectionError("AI_ENRICHMENT_SELECTION_INVALID")
    previous = _index_committed(committed, enrichment_version)
    by_lineage: dict[str, ReviewSelectionCandidate] = {}
    for candidate in candidates:
        _require_hash(candidate.review_lineage_sha256)
        _require_hash(candidate.source_record_hash)
        existing = by_lineage.get(candidate.review_lineage_sha256)
        if existing is not None and existing != candidate:
            raise EnrichmentSelectionError("AI_ENRICHMENT_SELECTION_CONFLICT")
        by_lineage[candidate.review_lineage_sha256] = candidate

    selections: list[ReviewSelection] = []
    for lineage, candidate in sorted(by_lineage.items()):
        projection = candidate.dlp_projection
        if not candidate.ai_eligible:
            disposition = SelectionDisposition.EXCLUDED_INELIGIBLE
            input_sha256 = None
        elif projection.decision is not DLPDecision.APPROVED:
            disposition = SelectionDisposition.EXCLUDED_DLP
            input_sha256 = None
        elif projection.content_sha256 is None:
            raise EnrichmentSelectionError("AI_ENRICHMENT_SELECTION_INVALID")
        else:
            input_sha256 = projection.content_sha256
            prior = previous.get(lineage)
            if prior is None:
                disposition = SelectionDisposition.NEW
            elif prior.input_sha256 == input_sha256:
                disposition = SelectionDisposition.REUSED
            else:
                disposition = SelectionDisposition.CHANGED
        selections.append(
            ReviewSelection(
                review_lineage_sha256=lineage,
                opaque_review_reference=projection.opaque_review_reference,
                source_record_hash=candidate.source_record_hash,
                input_sha256=input_sha256,
                disposition=disposition,
            )
        )
    canonical = "\n".join(
        "|".join(
            (
                selection.review_lineage_sha256,
                selection.source_record_hash,
                selection.input_sha256 or "",
                selection.disposition.value,
            )
        )
        for selection in selections
    )
    return EnrichmentSelectionPlan(
        enrichment_version=enrichment_version,
        selections=tuple(selections),
        selection_sha256=hashlib.sha256(canonical.encode()).hexdigest(),
    )


def _index_committed(
    committed: tuple[CommittedEnrichment, ...], enrichment_version: str
) -> dict[str, CommittedEnrichment]:
    indexed: dict[str, CommittedEnrichment] = {}
    for item in committed:
        _require_hash(item.review_lineage_sha256)
        _require_hash(item.source_record_hash)
        _require_hash(item.input_sha256)
        if item.enrichment_version != enrichment_version:
            continue
        prior = indexed.get(item.review_lineage_sha256)
        if prior is not None and prior != item:
            raise EnrichmentSelectionError("AI_ENRICHMENT_SELECTION_CONFLICT")
        indexed[item.review_lineage_sha256] = item
    return indexed


def _require_hash(value: str) -> None:
    if len(value) != 64 or any(character not in _SHA256 for character in value):
        raise EnrichmentSelectionError("AI_ENRICHMENT_SELECTION_INVALID")
