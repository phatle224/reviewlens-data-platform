"""Offline release-quality gate contracts for the M4 enrichment candidate."""

from __future__ import annotations

from decimal import Decimal

import pytest

from reviewlens.ai.evaluation import EnrichmentEvaluationReport
from reviewlens.ai.quality import (
    AIEnrichmentCandidate,
    AIQualityGateError,
    AIQualityGateStatus,
    evaluate_ai_quality_gate,
    guarded_publish_ai_candidate,
)

CANDIDATE_ID = "a" * 64
VERSION = "b" * 64


def _candidate() -> AIEnrichmentCandidate:
    return AIEnrichmentCandidate(
        candidate_id=CANDIDATE_ID,
        source_release_id="synthetic-source-release",
        enrichment_version=VERSION,
    )


def _report(
    *,
    enrichment_version: str = VERSION,
    sentiment: Decimal = Decimal("0.90"),
    aspect: Decimal = Decimal("0.80"),
    topic: Decimal = Decimal("0.80"),
    schema: Decimal = Decimal("1"),
) -> EnrichmentEvaluationReport:
    return EnrichmentEvaluationReport(
        dataset_sha256="c" * 64,
        split_sha256="d" * 64,
        enrichment_version=enrichment_version,
        evaluated_count=40,
        macro_sentiment_f1=sentiment,
        macro_aspect_sentiment_f1=aspect,
        micro_topic_f1=topic,
        schema_pass_rate=schema,
    )


def test_m4_quality_gate_passes_only_exact_passing_candidate_and_allows_publish() -> None:
    candidate = _candidate()
    gate = evaluate_ai_quality_gate(candidate=candidate, report=_report())
    published: list[str] = []

    guarded_publish_ai_candidate(
        candidate=candidate,
        gate=gate,
        publish=lambda: published.append("synthetic-published"),
    )

    assert gate.status is AIQualityGateStatus.PASSED
    assert gate.can_publish
    assert gate.reason_codes == ("AI_QUALITY_GATE_PASSED",)
    assert published == ["synthetic-published"]
    assert evaluate_ai_quality_gate(candidate=candidate, report=_report()) == gate


def test_m4_quality_gate_blocks_low_metrics_or_version_mismatch_before_publish() -> None:
    candidate = _candidate()
    failing = evaluate_ai_quality_gate(
        candidate=candidate,
        report=_report(sentiment=Decimal("0.84"), schema=Decimal("0.99")),
    )
    wrong_version = evaluate_ai_quality_gate(
        candidate=candidate,
        report=_report(enrichment_version="e" * 64),
    )
    published: list[str] = []

    for gate in (failing, wrong_version):
        with pytest.raises(AIQualityGateError, match="AI_ENRICHMENT_PUBLISH_BLOCKED"):
            guarded_publish_ai_candidate(
                candidate=candidate,
                gate=gate,
                publish=lambda: published.append("must-not-run"),
            )

    assert failing.status is AIQualityGateStatus.BLOCKED
    assert failing.reason_codes == (
        "AI_SCHEMA_PASS_RATE_BELOW_GATE",
        "AI_SENTIMENT_MACRO_F1_BELOW_GATE",
    )
    assert wrong_version.reason_codes == ("AI_ENRICHMENT_VERSION_MISMATCH",)
    assert published == []


def test_m4_quality_gate_is_pending_without_real_evaluation_and_candidate_bound() -> None:
    candidate = _candidate()
    pending = evaluate_ai_quality_gate(candidate=candidate, report=None)
    different = AIEnrichmentCandidate(
        candidate_id="f" * 64,
        source_release_id="synthetic-source-release",
        enrichment_version=VERSION,
    )

    assert pending.status is AIQualityGateStatus.PENDING
    assert pending.reason_codes == ("AI_GOLDEN_EVALUATION_MISSING",)
    with pytest.raises(AIQualityGateError, match="AI_ENRICHMENT_PUBLISH_BLOCKED"):
        guarded_publish_ai_candidate(candidate=different, gate=pending, publish=lambda: None)
