"""Synthetic regression tests for private M4 golden/holdout evaluation."""

from __future__ import annotations

from collections import Counter
from decimal import Decimal

import pytest

from reviewlens.ai.evaluation import (
    EnrichmentEvaluationError,
    GoldenDeliveryOutcome,
    GoldenEnrichmentLabel,
    GoldenLengthBucket,
    evaluate_holdout_enrichment,
    stratified_golden_holdout_split,
)
from reviewlens.ai.validation import AspectSentiment, ValidatedEnrichment


def _labels() -> tuple[GoldenEnrichmentLabel, ...]:
    return tuple(
        GoldenEnrichmentLabel(
            opaque_example_id=f"{index:064x}",
            review_score=(index % 4) + 1,
            length_bucket=(
                GoldenLengthBucket.SHORT
                if index % 4 == 0
                else GoldenLengthBucket.MEDIUM
                if index % 4 == 1
                else GoldenLengthBucket.LONG
            ),
            category_bucket=f"synthetic-category-{index % 4}",
            delivery_outcome=(
                GoldenDeliveryOutcome.ON_TIME
                if index % 4 in {0, 1}
                else GoldenDeliveryOutcome.DELAYED
            ),
            sentiment="positive",
            aspect_sentiments=(
                AspectSentiment(aspect="delivery", sentiment="positive", confidence=1.0),
            ),
            topics=("delivery_speed",),
        )
        for index in range(20)
    )


def _prediction(*, sentiment: str = "positive") -> ValidatedEnrichment:
    return ValidatedEnrichment.model_validate(
        {
            "sentiment": sentiment,
            "confidence": 0.9,
            "aspect_sentiments": [
                {"aspect": "delivery", "sentiment": sentiment, "confidence": 0.8}
            ],
            "topics": ["delivery_speed"],
            "summary": "Synthetic evaluation summary.",
            "highlights": ["Synthetic evaluation highlight."],
        }
    )


def test_m4_stratified_holdout_is_reproducible_and_at_least_twenty_percent() -> None:
    labels = _labels()
    first = stratified_golden_holdout_split(labels=labels, split_seed="m4-eval-v1")
    replay = stratified_golden_holdout_split(
        labels=tuple(reversed(labels)), split_seed="m4-eval-v1"
    )
    by_id = {label.opaque_example_id: label for label in labels}
    holdout_strata = Counter(by_id[example_id].stratum for example_id in first.holdout_ids)

    assert first == replay
    assert len(first.holdout_ids) == 4
    assert len(first.train_ids) == 16
    assert first.holdout_fraction >= Decimal("0.20")
    assert set(holdout_strata.values()) == {1}


def test_m4_holdout_evaluation_is_aggregate_reproducible_and_passes_initial_gates() -> None:
    labels = _labels()
    split = stratified_golden_holdout_split(labels=labels, split_seed="m4-eval-v1")
    predictions = {example_id: _prediction() for example_id in split.holdout_ids}

    report = evaluate_holdout_enrichment(labels=labels, split=split, predictions=predictions)
    replay = evaluate_holdout_enrichment(
        labels=tuple(reversed(labels)), split=split, predictions=dict(reversed(predictions.items()))
    )

    assert report == replay
    assert report.evaluated_count == 4
    assert report.macro_sentiment_f1 == 1
    assert report.macro_aspect_sentiment_f1 == 1
    assert report.micro_topic_f1 == 1
    assert report.schema_pass_rate == 1
    assert report.passes_initial_gate
    assert "Synthetic evaluation summary." not in repr(report)


def test_m4_holdout_rejects_training_or_missing_predictions_and_failing_quality() -> None:
    labels = _labels()
    split = stratified_golden_holdout_split(labels=labels, split_seed="m4-eval-v1")
    predictions = {
        example_id: _prediction(sentiment="negative") for example_id in split.holdout_ids
    }
    with_training = {**predictions, split.train_ids[0]: _prediction()}

    with pytest.raises(EnrichmentEvaluationError, match="AI_EVALUATION_HOLDOUT_INVALID"):
        evaluate_holdout_enrichment(labels=labels, split=split, predictions=with_training)
    with pytest.raises(EnrichmentEvaluationError, match="AI_EVALUATION_HOLDOUT_INVALID"):
        evaluate_holdout_enrichment(
            labels=labels,
            split=split,
            predictions={split.holdout_ids[0]: _prediction()},
        )

    report = evaluate_holdout_enrichment(labels=labels, split=split, predictions=predictions)
    assert not report.passes_initial_gate


def test_m4_holdout_requires_enough_private_labels() -> None:
    with pytest.raises(EnrichmentEvaluationError, match="AI_EVALUATION_DATASET_TOO_SMALL"):
        stratified_golden_holdout_split(labels=_labels()[:4], split_seed="m4-eval-v1")
