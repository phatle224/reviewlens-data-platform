"""Deterministic private enrichment golden-set splitting and evaluation."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal
from enum import StrEnum

from reviewlens.ai.enrichment import ASPECTS, SENTIMENTS, TOPICS
from reviewlens.ai.validation import AspectSentiment, ValidatedEnrichment

_SHA256 = frozenset("0123456789abcdef")
_ONE = Decimal("1")
_ZERO = Decimal("0")


class GoldenLengthBucket(StrEnum):
    SHORT = "short"
    MEDIUM = "medium"
    LONG = "long"


class GoldenDeliveryOutcome(StrEnum):
    ON_TIME = "on_time"
    DELAYED = "delayed"
    UNKNOWN = "unknown"


class EnrichmentEvaluationError(ValueError):
    """Sanitized evaluation error that intentionally excludes private labels."""


@dataclass(frozen=True, slots=True)
class GoldenEnrichmentLabel:
    """Private structured label with an opaque example reference and no review text."""

    opaque_example_id: str
    review_score: int
    length_bucket: GoldenLengthBucket
    category_bucket: str
    delivery_outcome: GoldenDeliveryOutcome
    sentiment: str
    aspect_sentiments: tuple[AspectSentiment, ...]
    topics: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_hash(self.opaque_example_id)
        if self.review_score not in {1, 2, 3, 4, 5}:
            raise EnrichmentEvaluationError("AI_EVALUATION_LABEL_INVALID")
        if not self.category_bucket or len(self.category_bucket) > 128:
            raise EnrichmentEvaluationError("AI_EVALUATION_LABEL_INVALID")
        if self.sentiment not in SENTIMENTS:
            raise EnrichmentEvaluationError("AI_EVALUATION_LABEL_INVALID")
        if any(
            item.aspect not in ASPECTS or item.sentiment not in SENTIMENTS
            for item in self.aspect_sentiments
        ):
            raise EnrichmentEvaluationError("AI_EVALUATION_LABEL_INVALID")
        if len({item.aspect for item in self.aspect_sentiments}) != len(self.aspect_sentiments):
            raise EnrichmentEvaluationError("AI_EVALUATION_LABEL_INVALID")
        if any(topic not in TOPICS for topic in self.topics) or len(set(self.topics)) != len(
            self.topics
        ):
            raise EnrichmentEvaluationError("AI_EVALUATION_LABEL_INVALID")

    @property
    def stratum(self) -> tuple[int, str, str, str]:
        """The required score/aspect/length/category/delivery stratification key."""

        aspects = ",".join(sorted(item.aspect for item in self.aspect_sentiments)) or "none"
        return (
            self.review_score,
            aspects,
            self.length_bucket.value,
            f"{self.category_bucket}:{self.delivery_outcome.value}",
        )


@dataclass(frozen=True, slots=True)
class GoldenHoldoutSplit:
    dataset_sha256: str
    split_seed: str
    train_ids: tuple[str, ...]
    holdout_ids: tuple[str, ...]

    @property
    def holdout_fraction(self) -> Decimal:
        total = len(self.train_ids) + len(self.holdout_ids)
        return Decimal(len(self.holdout_ids)) / Decimal(total)


@dataclass(frozen=True, slots=True)
class EnrichmentEvaluationReport:
    dataset_sha256: str
    split_sha256: str
    enrichment_version: str
    evaluated_count: int
    macro_sentiment_f1: Decimal
    macro_aspect_sentiment_f1: Decimal
    micro_topic_f1: Decimal
    schema_pass_rate: Decimal

    def __post_init__(self) -> None:
        _require_hash(self.dataset_sha256)
        _require_hash(self.split_sha256)
        _require_hash(self.enrichment_version)
        if self.evaluated_count < 1 or any(
            not value.is_finite() or value < _ZERO or value > _ONE
            for value in (
                self.macro_sentiment_f1,
                self.macro_aspect_sentiment_f1,
                self.micro_topic_f1,
                self.schema_pass_rate,
            )
        ):
            raise EnrichmentEvaluationError("AI_EVALUATION_REPORT_INVALID")

    @property
    def passes_initial_gate(self) -> bool:
        return (
            self.macro_sentiment_f1 >= Decimal("0.85")
            and self.macro_aspect_sentiment_f1 >= Decimal("0.75")
            and self.micro_topic_f1 >= Decimal("0.75")
            and self.schema_pass_rate == _ONE
        )


def stratified_golden_holdout_split(
    *,
    labels: tuple[GoldenEnrichmentLabel, ...],
    split_seed: str,
    holdout_fraction: Decimal = Decimal("0.20"),
) -> GoldenHoldoutSplit:
    """Produce a deterministic blind holdout with at least the requested fraction.

    The split is stratified across score, labelled aspects, review-length bucket,
    opaque category bucket and delivery outcome.  IDs, not labels or text, are
    returned to the caller so downstream evaluation can remain aggregate-only.
    """

    if not split_seed or len(split_seed) > 128 or not (_ZERO < holdout_fraction < _ONE):
        raise EnrichmentEvaluationError("AI_EVALUATION_SPLIT_INVALID")
    by_id = _unique_labels(labels)
    total = len(by_id)
    requested = int((Decimal(total) * holdout_fraction).to_integral_value(rounding=ROUND_CEILING))
    if total < 5 or requested < 1:
        raise EnrichmentEvaluationError("AI_EVALUATION_DATASET_TOO_SMALL")

    grouped: dict[tuple[int, str, str, str], list[GoldenEnrichmentLabel]] = {}
    for label in by_id.values():
        grouped.setdefault(label.stratum, []).append(label)
    ranked_groups = sorted(
        (
            (
                stratum,
                _ranked_ids(group_labels, split_seed),
                Decimal(len(group_labels)) * holdout_fraction,
            )
            for stratum, group_labels in grouped.items()
        ),
        key=lambda item: item[0],
    )

    selected: set[str] = set()
    remainders: list[tuple[Decimal, str, tuple[str, ...]]] = []
    for stratum, ranked_ids, expected in ranked_groups:
        base_count = int(expected)
        selected.update(ranked_ids[:base_count])
        remainders.append(
            (expected - Decimal(base_count), _stable_rank(stratum, split_seed), ranked_ids)
        )
    remaining = requested - len(selected)
    for _, _, ranked_ids in sorted(remainders, key=lambda item: (-item[0], item[1])):
        if remaining == 0:
            break
        candidate = next(
            (example_id for example_id in ranked_ids if example_id not in selected), None
        )
        if candidate is not None:
            selected.add(candidate)
            remaining -= 1
    if remaining != 0:
        raise EnrichmentEvaluationError("AI_EVALUATION_SPLIT_INVALID")

    holdout_ids = tuple(sorted(selected))
    train_ids = tuple(sorted(set(by_id) - selected))
    return GoldenHoldoutSplit(
        dataset_sha256=_dataset_sha256(tuple(by_id.values())),
        split_seed=split_seed,
        train_ids=train_ids,
        holdout_ids=holdout_ids,
    )


def evaluate_holdout_enrichment(
    *,
    labels: tuple[GoldenEnrichmentLabel, ...],
    split: GoldenHoldoutSplit,
    enrichment_version: str,
    predictions: Mapping[str, ValidatedEnrichment],
) -> EnrichmentEvaluationReport:
    """Evaluate only the declared blind holdout and return aggregate metrics."""

    _require_hash(enrichment_version)
    by_id = _unique_labels(labels)
    dataset_sha256 = _dataset_sha256(tuple(by_id.values()))
    if dataset_sha256 != split.dataset_sha256 or not split.holdout_ids:
        raise EnrichmentEvaluationError("AI_EVALUATION_SPLIT_INVALID")
    holdout_ids = frozenset(split.holdout_ids)
    if set(predictions) != holdout_ids or not holdout_ids.isdisjoint(split.train_ids):
        raise EnrichmentEvaluationError("AI_EVALUATION_HOLDOUT_INVALID")
    if any(not isinstance(prediction, ValidatedEnrichment) for prediction in predictions.values()):
        raise EnrichmentEvaluationError("AI_EVALUATION_PREDICTION_INVALID")

    holdout = tuple(by_id[example_id] for example_id in sorted(holdout_ids))
    sentiment_pairs = tuple(
        (label.sentiment, predictions[label.opaque_example_id].sentiment) for label in holdout
    )
    aspect_pairs = tuple(
        (
            frozenset(f"{item.aspect}:{item.sentiment}" for item in label.aspect_sentiments),
            frozenset(
                f"{item.aspect}:{item.sentiment}"
                for item in predictions[label.opaque_example_id].aspect_sentiments
            ),
        )
        for label in holdout
    )
    topic_pairs = tuple(
        (frozenset(label.topics), frozenset(predictions[label.opaque_example_id].topics))
        for label in holdout
    )
    return EnrichmentEvaluationReport(
        dataset_sha256=dataset_sha256,
        split_sha256=_split_sha256(split),
        enrichment_version=enrichment_version,
        evaluated_count=len(holdout),
        macro_sentiment_f1=_macro_single_label_f1(sentiment_pairs),
        macro_aspect_sentiment_f1=_macro_set_label_f1(aspect_pairs),
        micro_topic_f1=_micro_set_label_f1(topic_pairs),
        schema_pass_rate=_ONE,
    )


def _unique_labels(labels: tuple[GoldenEnrichmentLabel, ...]) -> dict[str, GoldenEnrichmentLabel]:
    by_id: dict[str, GoldenEnrichmentLabel] = {}
    for label in labels:
        existing = by_id.get(label.opaque_example_id)
        if existing is not None and existing != label:
            raise EnrichmentEvaluationError("AI_EVALUATION_LABEL_CONFLICT")
        by_id[label.opaque_example_id] = label
    if not by_id:
        raise EnrichmentEvaluationError("AI_EVALUATION_DATASET_TOO_SMALL")
    return by_id


def _ranked_ids(labels: list[GoldenEnrichmentLabel], split_seed: str) -> tuple[str, ...]:
    return tuple(
        sorted(
            (label.opaque_example_id for label in labels),
            key=lambda item: _stable_rank(item, split_seed),
        )
    )


def _stable_rank(value: object, split_seed: str) -> str:
    return hashlib.sha256(f"{split_seed}\x1f{value}".encode()).hexdigest()


def _dataset_sha256(labels: tuple[GoldenEnrichmentLabel, ...]) -> str:
    canonical = [
        {
            "id": label.opaque_example_id,
            "score": label.review_score,
            "length": label.length_bucket.value,
            "category": label.category_bucket,
            "delivery": label.delivery_outcome.value,
            "sentiment": label.sentiment,
            "aspects": [(item.aspect, item.sentiment) for item in label.aspect_sentiments],
            "topics": list(label.topics),
        }
        for label in sorted(labels, key=lambda item: item.opaque_example_id)
    ]
    return hashlib.sha256(
        json.dumps(canonical, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()


def _split_sha256(split: GoldenHoldoutSplit) -> str:
    canonical = json.dumps(
        {
            "dataset": split.dataset_sha256,
            "seed": split.split_seed,
            "train": split.train_ids,
            "holdout": split.holdout_ids,
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def _macro_single_label_f1(pairs: tuple[tuple[str, str], ...]) -> Decimal:
    classes = sorted({value for pair in pairs for value in pair})
    return sum((_single_class_f1(pairs, label) for label in classes), _ZERO) / Decimal(len(classes))


def _single_class_f1(pairs: tuple[tuple[str, str], ...], label: str) -> Decimal:
    true_positive = sum(actual == label and predicted == label for actual, predicted in pairs)
    false_positive = sum(actual != label and predicted == label for actual, predicted in pairs)
    false_negative = sum(actual == label and predicted != label for actual, predicted in pairs)
    return _f1(true_positive, false_positive, false_negative)


def _macro_set_label_f1(pairs: tuple[tuple[frozenset[str], frozenset[str]], ...]) -> Decimal:
    labels = sorted(
        {label for actual, predicted in pairs for values in (actual, predicted) for label in values}
    )
    if not labels:
        return _ONE
    scores = []
    for label in labels:
        true_positive = sum(label in actual and label in predicted for actual, predicted in pairs)
        false_positive = sum(
            label not in actual and label in predicted for actual, predicted in pairs
        )
        false_negative = sum(
            label in actual and label not in predicted for actual, predicted in pairs
        )
        scores.append(_f1(true_positive, false_positive, false_negative))
    return sum(scores, _ZERO) / Decimal(len(scores))


def _micro_set_label_f1(pairs: tuple[tuple[frozenset[str], frozenset[str]], ...]) -> Decimal:
    true_positive = sum(len(actual & predicted) for actual, predicted in pairs)
    false_positive = sum(len(predicted - actual) for actual, predicted in pairs)
    false_negative = sum(len(actual - predicted) for actual, predicted in pairs)
    return _f1(true_positive, false_positive, false_negative)


def _f1(true_positive: int, false_positive: int, false_negative: int) -> Decimal:
    denominator = (2 * true_positive) + false_positive + false_negative
    return Decimal(2 * true_positive) / Decimal(denominator) if denominator else _ONE


def _require_hash(value: str) -> None:
    if len(value) != 64 or any(character not in _SHA256 for character in value):
        raise EnrichmentEvaluationError("AI_EVALUATION_LABEL_INVALID")
