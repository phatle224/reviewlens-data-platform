"""Fail-closed, version-bound quality gate for private AI enrichment candidates."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from reviewlens.ai.evaluation import EnrichmentEvaluationReport

_SHA256 = frozenset("0123456789abcdef")
AI_QUALITY_GATE_VERSION = "reviewlens-ai-quality-gate-v1"


class AIQualityGateError(ValueError):
    """Sanitized quality-gate failure; no labels, outputs, or release rows leak."""

    def __init__(self, code: str = "AI_ENRICHMENT_QUALITY_GATE_INVALID") -> None:
        super().__init__(code)


class AIQualityGateStatus(StrEnum):
    PASSED = "passed"
    BLOCKED = "blocked"
    PENDING = "pending"


@dataclass(frozen=True, slots=True)
class AIEnrichmentCandidate:
    """Private AI candidate reference, never an active-release mutation."""

    candidate_id: str
    source_release_id: str
    enrichment_version: str

    def __post_init__(self) -> None:
        if (
            not _is_hash(self.candidate_id)
            or not _is_hash(self.enrichment_version)
            or not self.source_release_id
            or len(self.source_release_id) > 80
        ):
            raise AIQualityGateError()


@dataclass(frozen=True, slots=True)
class AIQualityGateResult:
    candidate_id: str
    enrichment_version: str
    status: AIQualityGateStatus
    reason_codes: tuple[str, ...]
    fingerprint: str
    report: EnrichmentEvaluationReport | None = field(default=None, repr=False)
    gate_version: str = AI_QUALITY_GATE_VERSION

    def __post_init__(self) -> None:
        if (
            not _is_hash(self.candidate_id)
            or not _is_hash(self.enrichment_version)
            or not isinstance(self.status, AIQualityGateStatus)
            or not self.reason_codes
            or tuple(sorted(set(self.reason_codes))) != self.reason_codes
            or any(not code.startswith("AI_") or len(code) > 128 for code in self.reason_codes)
            or not _is_hash(self.fingerprint)
            or self.gate_version != AI_QUALITY_GATE_VERSION
            or (
                self.status is AIQualityGateStatus.PASSED
                and self.reason_codes != ("AI_QUALITY_GATE_PASSED",)
            )
            or (
                self.status is not AIQualityGateStatus.PASSED
                and self.reason_codes == ("AI_QUALITY_GATE_PASSED",)
            )
            or self.fingerprint
            != _fingerprint(
                candidate_id=self.candidate_id,
                enrichment_version=self.enrichment_version,
                status=self.status,
                reason_codes=self.reason_codes,
                report=self.report,
            )
        ):
            raise AIQualityGateError()

    @property
    def can_publish(self) -> bool:
        return self.status is AIQualityGateStatus.PASSED


def evaluate_ai_quality_gate(
    *,
    candidate: AIEnrichmentCandidate,
    report: EnrichmentEvaluationReport | None,
) -> AIQualityGateResult:
    """Evaluate required M0 thresholds without publishing or altering a release pointer."""

    if report is None:
        return _result(
            candidate, AIQualityGateStatus.PENDING, ("AI_GOLDEN_EVALUATION_MISSING",), None
        )
    if report.enrichment_version != candidate.enrichment_version:
        return _result(
            candidate,
            AIQualityGateStatus.BLOCKED,
            ("AI_ENRICHMENT_VERSION_MISMATCH",),
            report,
        )
    reason_codes = tuple(
        sorted(
            code
            for code, passed in (
                (
                    "AI_SENTIMENT_MACRO_F1_BELOW_GATE",
                    report.macro_sentiment_f1 >= Decimal("0.85"),
                ),
                (
                    "AI_ASPECT_SENTIMENT_MACRO_F1_BELOW_GATE",
                    report.macro_aspect_sentiment_f1 >= Decimal("0.75"),
                ),
                ("AI_TOPIC_MICRO_F1_BELOW_GATE", report.micro_topic_f1 >= Decimal("0.75")),
                ("AI_SCHEMA_PASS_RATE_BELOW_GATE", report.schema_pass_rate == Decimal("1")),
            )
            if not passed
        )
    )
    return _result(
        candidate,
        AIQualityGateStatus.BLOCKED if reason_codes else AIQualityGateStatus.PASSED,
        reason_codes or ("AI_QUALITY_GATE_PASSED",),
        report,
    )


def guarded_publish_ai_candidate(
    *,
    candidate: AIEnrichmentCandidate,
    gate: AIQualityGateResult,
    publish: Callable[[], None],
) -> None:
    """Invoke a publish callback only for the exact, passing candidate gate."""

    if (
        gate.candidate_id != candidate.candidate_id
        or gate.enrichment_version != candidate.enrichment_version
        or not gate.can_publish
    ):
        raise AIQualityGateError("AI_ENRICHMENT_PUBLISH_BLOCKED")
    publish()


def _result(
    candidate: AIEnrichmentCandidate,
    status: AIQualityGateStatus,
    reason_codes: tuple[str, ...],
    report: EnrichmentEvaluationReport | None,
) -> AIQualityGateResult:
    return AIQualityGateResult(
        candidate_id=candidate.candidate_id,
        enrichment_version=candidate.enrichment_version,
        status=status,
        reason_codes=reason_codes,
        fingerprint=_fingerprint(
            candidate_id=candidate.candidate_id,
            enrichment_version=candidate.enrichment_version,
            status=status,
            reason_codes=reason_codes,
            report=report,
        ),
        report=report,
    )


def _fingerprint(
    *,
    candidate_id: str,
    enrichment_version: str,
    status: AIQualityGateStatus,
    reason_codes: tuple[str, ...],
    report: EnrichmentEvaluationReport | None,
) -> str:
    payload = {
        "candidate_id": candidate_id,
        "enrichment_version": enrichment_version,
        "gate_version": AI_QUALITY_GATE_VERSION,
        "report": None
        if report is None
        else {
            "dataset_sha256": report.dataset_sha256,
            "split_sha256": report.split_sha256,
            "enrichment_version": report.enrichment_version,
            "evaluated_count": report.evaluated_count,
            "macro_sentiment_f1": str(report.macro_sentiment_f1),
            "macro_aspect_sentiment_f1": str(report.macro_aspect_sentiment_f1),
            "micro_topic_f1": str(report.micro_topic_f1),
            "schema_pass_rate": str(report.schema_pass_rate),
        },
        "reason_codes": reason_codes,
        "status": status.value,
    }
    return hashlib.sha256(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()


def _is_hash(value: str) -> bool:
    return len(value) == 64 and all(character in _SHA256 for character in value)
