"""Private commit and aggregate coverage contracts for validated enrichment only."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from reviewlens.ai.ledger import EnrichmentResultMap
from reviewlens.ai.selection import CommittedEnrichment
from reviewlens.ai.validation import ValidatedEnrichment

_SHA256 = frozenset("0123456789abcdef")


class EnrichmentCommitError(ValueError):
    """Sanitized commit or coverage failure; it never includes private fields."""


class EnrichmentCommitDisposition(StrEnum):
    INSERTED = "inserted"
    REUSED = "reused"
    REPLACED = "replaced"


@dataclass(frozen=True, slots=True)
class ValidatedEnrichmentCommit:
    """One private current result at the ``review_id + order_id + version`` grain."""

    review_id: str = field(repr=False)
    order_id: str = field(repr=False)
    source_record_hash: str
    enrichment_version: str
    input_sha256: str
    result_map: EnrichmentResultMap
    model_slug: str
    prompt_version: str
    schema_version: str
    taxonomy_version: str
    dlp_policy_version: str
    result: ValidatedEnrichment = field(repr=False)

    def __post_init__(self) -> None:
        if not self.review_id or not self.order_id:
            raise EnrichmentCommitError("AI_ENRICHMENT_COMMIT_INVALID")
        for value in (self.source_record_hash, self.input_sha256):
            _require_hash(value)
        if not all(
            value and len(value) <= 256
            for value in (
                self.enrichment_version,
                self.model_slug,
                self.prompt_version,
                self.schema_version,
                self.taxonomy_version,
                self.dlp_policy_version,
            )
        ):
            raise EnrichmentCommitError("AI_ENRICHMENT_COMMIT_INVALID")
        if not isinstance(self.result, ValidatedEnrichment):
            raise EnrichmentCommitError("AI_ENRICHMENT_RESULT_NOT_VALIDATED")
        if (
            self.result_map.enrichment_version != self.enrichment_version
            or self.result_map.source_record_hash != self.source_record_hash
            or self.result_map.result_sha256 != self.result_sha256
        ):
            raise EnrichmentCommitError("AI_ENRICHMENT_RESULT_NOT_VALIDATED")

    @property
    def review_lineage_sha256(self) -> str:
        return hashlib.sha256(f"{self.review_id}\x1f{self.order_id}".encode()).hexdigest()

    @property
    def result_sha256(self) -> str:
        canonical = json.dumps(
            self.result.model_dump(mode="json"), separators=(",", ":"), sort_keys=True
        )
        return hashlib.sha256(canonical.encode()).hexdigest()

    def to_selection_committed(self) -> CommittedEnrichment:
        """Return only hashes/version for the deterministic selector boundary."""

        return CommittedEnrichment(
            review_lineage_sha256=self.review_lineage_sha256,
            enrichment_version=self.enrichment_version,
            source_record_hash=self.source_record_hash,
            input_sha256=self.input_sha256,
        )


@dataclass(frozen=True, slots=True)
class CommittedEnrichmentOutcome:
    disposition: EnrichmentCommitDisposition
    commit: ValidatedEnrichmentCommit = field(repr=False)


class InMemoryValidatedEnrichmentStore:
    """Atomic current-result semantics; only validated objects cross this boundary."""

    def __init__(self) -> None:
        self._commits: dict[tuple[str, str, str], ValidatedEnrichmentCommit] = {}

    @property
    def commits(self) -> tuple[ValidatedEnrichmentCommit, ...]:
        return tuple(self._commits.values())

    def commit(self, candidate: ValidatedEnrichmentCommit) -> CommittedEnrichmentOutcome:
        key = (candidate.review_id, candidate.order_id, candidate.enrichment_version)
        existing = self._commits.get(key)
        if existing is None:
            self._commits[key] = candidate
            return CommittedEnrichmentOutcome(EnrichmentCommitDisposition.INSERTED, candidate)
        if existing == candidate:
            return CommittedEnrichmentOutcome(EnrichmentCommitDisposition.REUSED, existing)
        if existing.input_sha256 == candidate.input_sha256:
            raise EnrichmentCommitError("AI_ENRICHMENT_IDEMPOTENCY_CONFLICT")
        self._commits[key] = candidate
        return CommittedEnrichmentOutcome(EnrichmentCommitDisposition.REPLACED, candidate)


@dataclass(frozen=True, slots=True)
class BaseReviewCoverageInput:
    """Private base-fact reference required for an aggregate coverage projection."""

    review_lineage_sha256: str
    source_record_hash: str
    ai_eligible: bool

    def __post_init__(self) -> None:
        _require_hash(self.review_lineage_sha256)
        _require_hash(self.source_record_hash)


@dataclass(frozen=True, slots=True)
class EnrichmentCoverageProjection:
    """Aggregate-only availability state; no identifiers or generated text leak."""

    enrichment_version: str
    base_review_count: int
    eligible_review_count: int
    valid_enrichment_count: int
    missing_eligible_review_count: int
    coverage_ratio: Decimal


def build_enrichment_coverage_projection(
    *,
    base_reviews: tuple[BaseReviewCoverageInput, ...],
    commits: tuple[ValidatedEnrichmentCommit, ...],
    enrichment_version: str,
) -> EnrichmentCoverageProjection:
    """Reconcile valid results to the base fact without filtering the base fact."""

    if not enrichment_version or len(enrichment_version) > 256:
        raise EnrichmentCommitError("AI_ENRICHMENT_COVERAGE_INVALID")
    base_by_lineage: dict[str, BaseReviewCoverageInput] = {}
    for base in base_reviews:
        existing = base_by_lineage.get(base.review_lineage_sha256)
        if existing is not None and existing != base:
            raise EnrichmentCommitError("AI_ENRICHMENT_COVERAGE_CONFLICT")
        base_by_lineage[base.review_lineage_sha256] = base

    committed_lineages: set[str] = set()
    for commit in commits:
        if commit.enrichment_version != enrichment_version:
            continue
        matched_base = base_by_lineage.get(commit.review_lineage_sha256)
        if (
            matched_base is None
            or not matched_base.ai_eligible
            or matched_base.source_record_hash != commit.source_record_hash
            or commit.review_lineage_sha256 in committed_lineages
        ):
            raise EnrichmentCommitError("AI_ENRICHMENT_COVERAGE_CONFLICT")
        committed_lineages.add(commit.review_lineage_sha256)

    base_count = len(base_by_lineage)
    eligible_count = sum(base.ai_eligible for base in base_by_lineage.values())
    valid_count = len(committed_lineages)
    return EnrichmentCoverageProjection(
        enrichment_version=enrichment_version,
        base_review_count=base_count,
        eligible_review_count=eligible_count,
        valid_enrichment_count=valid_count,
        missing_eligible_review_count=eligible_count - valid_count,
        coverage_ratio=(Decimal(valid_count) / Decimal(eligible_count))
        if eligible_count
        else Decimal("0"),
    )


def _require_hash(value: str) -> None:
    if len(value) != 64 or any(character not in _SHA256 for character in value):
        raise EnrichmentCommitError("AI_ENRICHMENT_COMMIT_INVALID")
