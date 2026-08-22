"""Private-only Olist enrichment annotation-pack creation and validation.

The generated queue contains restricted review text and is intentionally written
only beneath an ignored ``private_evaluation/`` directory.  Committed code emits
only aggregate validation output; it never prints review text or natural IDs.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import TextIO

from reviewlens.ai.evaluation import (
    EnrichmentEvaluationError,
    EnrichmentEvaluationReport,
    GoldenDeliveryOutcome,
    GoldenEnrichmentLabel,
    GoldenLengthBucket,
    evaluate_holdout_enrichment,
    stratified_golden_holdout_split,
)
from reviewlens.ai.validation import AspectSentiment, ValidatedEnrichment

ANNOTATION_PACK_VERSION = "reviewlens-m4-enrichment-annotation-pack-v1"
MINIMUM_GOLDEN_LABELS = 200


class GoldenAnnotationPackError(ValueError):
    """Sanitized private annotation-pack failure without review content or IDs."""

    def __init__(self, code: str = "AI_EVALUATION_ANNOTATION_PACK_INVALID") -> None:
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class GoldenAnnotationCandidate:
    """One private annotation unit; natural IDs remain outside this object."""

    opaque_example_id: str
    source_record_hash: str
    review_score: int
    length_bucket: GoldenLengthBucket
    category_bucket: str
    delivery_outcome: GoldenDeliveryOutcome
    review_text: str = field(repr=False)

    def __post_init__(self) -> None:
        if (
            not _is_hash(self.opaque_example_id)
            or not _is_hash(self.source_record_hash)
            or self.review_score not in {1, 2, 3, 4, 5}
            or not self.category_bucket
            or len(self.category_bucket) > 128
            or not self.review_text.strip()
        ):
            raise GoldenAnnotationPackError()

    @property
    def sampling_stratum(self) -> tuple[int, str, str, str]:
        return (
            self.review_score,
            self.length_bucket.value,
            self.category_bucket,
            self.delivery_outcome.value,
        )


@dataclass(frozen=True, slots=True)
class GoldenAnnotationPackPaths:
    """Private output paths only; no content is represented or logged."""

    annotation_queue_path: Path
    labels_path: Path
    metadata_path: Path


def build_olist_annotation_candidates(
    *, archive_dir: Path
) -> tuple[GoldenAnnotationCandidate, ...]:
    """Join private Olist CSV metadata without retaining natural IDs in results."""

    products = _load_product_categories(archive_dir / "olist_products_dataset.csv")
    categories_by_order = _load_order_categories(
        archive_dir / "olist_order_items_dataset.csv", products
    )
    delivery_by_order = _load_delivery_outcomes(archive_dir / "olist_orders_dataset.csv")
    candidates: dict[str, GoldenAnnotationCandidate] = {}
    for row in _read_rows(
        archive_dir / "olist_order_reviews_dataset.csv",
        required=(
            "review_id",
            "order_id",
            "review_score",
            "review_comment_title",
            "review_comment_message",
        ),
    ):
        review_id = _required_value(row, "review_id")
        order_id = _required_value(row, "order_id")
        try:
            review_score = int(_required_value(row, "review_score"))
        except ValueError as error:
            raise GoldenAnnotationPackError("AI_EVALUATION_ANNOTATION_SOURCE_INVALID") from error
        title = row.get("review_comment_title", "")
        message = row.get("review_comment_message", "")
        review_text = "\n".join(value.strip() for value in (title, message) if value.strip())
        if not review_text:
            continue
        opaque_id = _digest(review_id, order_id)
        candidate = GoldenAnnotationCandidate(
            opaque_example_id=opaque_id,
            source_record_hash=_digest(review_id, order_id, str(review_score), title, message),
            review_score=review_score,
            length_bucket=_length_bucket(review_text),
            category_bucket=_category_bucket(categories_by_order.get(order_id, frozenset())),
            delivery_outcome=delivery_by_order.get(order_id, GoldenDeliveryOutcome.UNKNOWN),
            review_text=review_text,
        )
        previous = candidates.get(opaque_id)
        if previous is not None and previous != candidate:
            raise GoldenAnnotationPackError("AI_EVALUATION_ANNOTATION_SOURCE_CONFLICT")
        candidates[opaque_id] = candidate
    if len(candidates) < MINIMUM_GOLDEN_LABELS:
        raise GoldenAnnotationPackError("AI_EVALUATION_ANNOTATION_SOURCE_TOO_SMALL")
    return tuple(sorted(candidates.values(), key=lambda item: item.opaque_example_id))


def select_stratified_annotation_candidates(
    *,
    candidates: Sequence[GoldenAnnotationCandidate],
    count: int,
    seed: str,
) -> tuple[GoldenAnnotationCandidate, ...]:
    """Select a deterministic score/length/category/delivery-stratified sample.

    Aspect is intentionally absent here because it is a human label.  The later
    golden holdout splitter adds aspect stratification once annotation completes.
    """

    if count < 1 or not seed or len(seed) > 128:
        raise GoldenAnnotationPackError()
    unique = {candidate.opaque_example_id: candidate for candidate in candidates}
    if len(unique) != len(candidates) or count > len(unique):
        raise GoldenAnnotationPackError("AI_EVALUATION_ANNOTATION_SELECTION_INVALID")
    grouped: dict[tuple[int, str, str, str], list[GoldenAnnotationCandidate]] = defaultdict(list)
    for candidate in unique.values():
        grouped[candidate.sampling_stratum].append(candidate)
    ranked = {
        stratum: tuple(
            sorted(
                items,
                key=lambda item: _digest(seed, item.opaque_example_id),
            )
        )
        for stratum, items in grouped.items()
    }
    total = len(unique)
    allocations = {stratum: 0 for stratum in ranked}
    group_order = sorted(ranked, key=lambda stratum: _digest(seed, repr(stratum)))
    for stratum in group_order[:count]:
        allocations[stratum] = 1
    while sum(allocations.values()) < count:
        available = [
            stratum for stratum, items in ranked.items() if allocations[stratum] < len(items)
        ]
        if not available:
            raise GoldenAnnotationPackError("AI_EVALUATION_ANNOTATION_SELECTION_INVALID")
        stratum = max(
            available,
            key=lambda item: (
                (len(ranked[item]) * count / total) - allocations[item],
                _digest(seed, repr(item)),
            ),
        )
        allocations[stratum] += 1
    return tuple(
        sorted(
            (
                candidate
                for stratum, items in ranked.items()
                for candidate in items[: allocations[stratum]]
            ),
            key=lambda item: item.opaque_example_id,
        )
    )


def write_annotation_pack(
    *,
    candidates: Sequence[GoldenAnnotationCandidate],
    output_dir: Path,
    seed: str,
) -> GoldenAnnotationPackPaths:
    """Write a private queue plus blank structured labels without overwriting data."""

    if output_dir.exists() and any(output_dir.iterdir()):
        raise GoldenAnnotationPackError("AI_EVALUATION_ANNOTATION_OUTPUT_EXISTS")
    output_dir.mkdir(parents=True, exist_ok=True)
    selected = tuple(candidates)
    if len(selected) < MINIMUM_GOLDEN_LABELS:
        raise GoldenAnnotationPackError("AI_EVALUATION_ANNOTATION_SOURCE_TOO_SMALL")
    queue_path = output_dir / "annotation_queue.jsonl"
    labels_path = output_dir / "labels.jsonl"
    metadata_path = output_dir / "METADATA.json"
    _write_jsonl(queue_path, (_queue_record(candidate) for candidate in selected))
    _write_jsonl(labels_path, (_blank_label_record(candidate) for candidate in selected))
    metadata = {
        "annotation_pack_version": ANNOTATION_PACK_VERSION,
        "candidate_count": len(selected),
        "dataset_sha256": _candidate_dataset_sha256(selected),
        "sampling_dimensions": [
            "review_score",
            "length_bucket",
            "category_bucket",
            "delivery_outcome",
        ],
        "seed_sha256": _digest(seed),
        "status": "pending_human_review",
    }
    metadata_path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return GoldenAnnotationPackPaths(queue_path, labels_path, metadata_path)


def load_completed_golden_labels(*, labels_path: Path) -> tuple[GoldenEnrichmentLabel, ...]:
    """Load only fully human-reviewed private labels; never read queue text."""

    labels: list[GoldenEnrichmentLabel] = []
    for _line_number, line in enumerate(
        labels_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            raise GoldenAnnotationPackError("AI_EVALUATION_ANNOTATION_LABEL_INVALID") from error
        if not isinstance(record, dict) or record.get("annotation_status") != "approved":
            raise GoldenAnnotationPackError("AI_EVALUATION_ANNOTATION_LABELS_INCOMPLETE")
        try:
            aspects = tuple(
                AspectSentiment.model_validate(item) for item in record["aspect_sentiments"]
            )
            label = GoldenEnrichmentLabel(
                opaque_example_id=record["opaque_example_id"],
                review_score=record["review_score"],
                length_bucket=GoldenLengthBucket(record["length_bucket"]),
                category_bucket=record["category_bucket"],
                delivery_outcome=GoldenDeliveryOutcome(record["delivery_outcome"]),
                sentiment=record["sentiment"],
                aspect_sentiments=aspects,
                topics=tuple(record["topics"]),
            )
        except (EnrichmentEvaluationError, KeyError, TypeError, ValueError) as error:
            raise GoldenAnnotationPackError("AI_EVALUATION_ANNOTATION_LABEL_INVALID") from error
        labels.append(label)
    if len(labels) < MINIMUM_GOLDEN_LABELS:
        raise GoldenAnnotationPackError("AI_EVALUATION_ANNOTATION_LABELS_INCOMPLETE")
    return tuple(labels)


def write_machine_assisted_suggestions(
    *,
    annotation_queue_path: Path,
    labels_path: Path,
    output_path: Path,
) -> int:
    """Create private score/delivery suggestions without reading text semantics.

    The output status is deliberately ``machine_assisted``. It cannot be
    consumed by the human-golden loader and must be reviewed before approval.
    """

    if output_path.exists():
        raise GoldenAnnotationPackError("AI_EVALUATION_ANNOTATION_OUTPUT_EXISTS")
    queue = _load_queue_metadata(annotation_queue_path)
    templates = _load_label_templates(labels_path)
    if set(queue) != set(templates) or len(queue) < MINIMUM_GOLDEN_LABELS:
        raise GoldenAnnotationPackError("AI_EVALUATION_ANNOTATION_LABEL_INVALID")
    suggestions = (
        _machine_assisted_label_record(queue[example_id], templates[example_id])
        for example_id in sorted(queue)
    )
    _write_jsonl(output_path, suggestions)
    return len(queue)


def evaluate_private_holdout(
    *,
    labels_path: Path,
    split_seed: str,
    predictions_path: Path,
    enrichment_version: str,
) -> EnrichmentEvaluationReport:
    """Evaluate a private prediction JSONL file against exactly the blind holdout.

    Prediction records may contain restricted model output, so they are read only
    from a caller-provided private path.  Errors are stable codes and the returned
    report is aggregate-only.
    """

    try:
        labels = load_completed_golden_labels(labels_path=labels_path)
        split = stratified_golden_holdout_split(labels=labels, split_seed=split_seed)
        return evaluate_holdout_enrichment(
            labels=labels,
            split=split,
            enrichment_version=enrichment_version,
            predictions=_load_private_predictions(predictions_path),
        )
    except EnrichmentEvaluationError as error:
        raise GoldenAnnotationPackError(str(error)) from error


def write_aggregate_evaluation_report(
    *, report: EnrichmentEvaluationReport, output_path: Path
) -> None:
    """Persist an immutable aggregate-only report without prediction content."""

    if output_path.exists():
        raise GoldenAnnotationPackError("AI_EVALUATION_ANNOTATION_OUTPUT_EXISTS")
    payload = {
        "dataset_sha256": report.dataset_sha256,
        "enrichment_version": report.enrichment_version,
        "evaluated_count": report.evaluated_count,
        "macro_aspect_sentiment_f1": str(report.macro_aspect_sentiment_f1),
        "macro_sentiment_f1": str(report.macro_sentiment_f1),
        "micro_topic_f1": str(report.micro_topic_f1),
        "passes_initial_gate": report.passes_initial_gate,
        "schema_pass_rate": str(report.schema_pass_rate),
        "split_sha256": report.split_sha256,
    }
    try:
        with output_path.open("x", encoding="utf-8", newline="") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")
    except OSError as error:
        raise GoldenAnnotationPackError("AI_EVALUATION_ANNOTATION_OUTPUT_UNAVAILABLE") from error


def main(argv: Sequence[str] | None = None) -> int:
    """Create or validate private annotation material with aggregate-only output."""

    parser = argparse.ArgumentParser(description="ReviewLens private M4 golden-set tooling")
    commands = parser.add_subparsers(dest="command", required=True)
    generate = commands.add_parser("generate")
    generate.add_argument("--archive-dir", type=Path, default=Path("archive"))
    generate.add_argument("--output-dir", type=Path, required=True)
    generate.add_argument("--seed", required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("--labels-path", type=Path, required=True)
    validate.add_argument("--split-seed", required=True)
    suggest = commands.add_parser("suggest")
    suggest.add_argument("--annotation-queue-path", type=Path, required=True)
    suggest.add_argument("--labels-path", type=Path, required=True)
    suggest.add_argument("--output-path", type=Path, required=True)
    evaluate = commands.add_parser("evaluate")
    evaluate.add_argument("--labels-path", type=Path, required=True)
    evaluate.add_argument("--split-seed", required=True)
    evaluate.add_argument("--predictions-path", type=Path, required=True)
    evaluate.add_argument("--enrichment-version", required=True)
    evaluate.add_argument("--report-path", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "generate":
            candidates = build_olist_annotation_candidates(archive_dir=args.archive_dir)
            selected = select_stratified_annotation_candidates(
                candidates=candidates,
                count=MINIMUM_GOLDEN_LABELS,
                seed=args.seed,
            )
            paths = write_annotation_pack(
                candidates=selected, output_dir=args.output_dir, seed=args.seed
            )
            print(
                json.dumps(
                    {
                        "candidate_count": len(selected),
                        "metadata_path": str(paths.metadata_path),
                        "status": "pending_human_review",
                    },
                    sort_keys=True,
                )
            )
            return 0
        if args.command == "suggest":
            count = write_machine_assisted_suggestions(
                annotation_queue_path=args.annotation_queue_path,
                labels_path=args.labels_path,
                output_path=args.output_path,
            )
            print(
                json.dumps(
                    {
                        "candidate_count": count,
                        "status": "machine_assisted_review_required",
                    },
                    sort_keys=True,
                )
            )
            return 0
        if args.command == "evaluate":
            report = evaluate_private_holdout(
                labels_path=args.labels_path,
                split_seed=args.split_seed,
                predictions_path=args.predictions_path,
                enrichment_version=args.enrichment_version,
            )
            write_aggregate_evaluation_report(report=report, output_path=args.report_path)
            print(
                json.dumps(
                    {
                        "evaluated_count": report.evaluated_count,
                        "passes_initial_gate": report.passes_initial_gate,
                        "status": "private_evaluation_complete",
                    },
                    sort_keys=True,
                )
            )
            return 0
        labels = load_completed_golden_labels(labels_path=args.labels_path)
        split = stratified_golden_holdout_split(labels=labels, split_seed=args.split_seed)
        print(
            json.dumps(
                {
                    "dataset_sha256": split.dataset_sha256,
                    "holdout_count": len(split.holdout_ids),
                    "label_count": len(labels),
                    "split_seed_sha256": _digest(args.split_seed),
                    "status": "ready_for_private_predictions",
                },
                sort_keys=True,
            )
        )
        return 0
    except GoldenAnnotationPackError as error:
        parser.error(str(error))
    return 2


def _load_product_categories(path: Path) -> dict[str, str]:
    return {
        _required_value(row, "product_id"): row.get("product_category_name", "").strip()
        for row in _read_rows(path, required=("product_id", "product_category_name"))
    }


def _load_order_categories(path: Path, products: dict[str, str]) -> dict[str, frozenset[str]]:
    grouped: dict[str, set[str]] = defaultdict(set)
    for row in _read_rows(path, required=("order_id", "product_id")):
        category = products.get(_required_value(row, "product_id"), "")
        if category:
            grouped[_required_value(row, "order_id")].add(category)
    return {order_id: frozenset(categories) for order_id, categories in grouped.items()}


def _load_delivery_outcomes(path: Path) -> dict[str, GoldenDeliveryOutcome]:
    outcomes: dict[str, GoldenDeliveryOutcome] = {}
    for row in _read_rows(
        path,
        required=("order_id", "order_delivered_customer_date", "order_estimated_delivery_date"),
    ):
        delivered = _parse_date(row.get("order_delivered_customer_date", ""))
        estimated = _parse_date(row.get("order_estimated_delivery_date", ""))
        outcomes[_required_value(row, "order_id")] = (
            GoldenDeliveryOutcome.UNKNOWN
            if delivered is None or estimated is None
            else GoldenDeliveryOutcome.DELAYED
            if delivered > estimated
            else GoldenDeliveryOutcome.ON_TIME
        )
    return outcomes


def _read_rows(path: Path, *, required: tuple[str, ...]) -> Iterable[dict[str, str]]:
    try:
        handle: TextIO
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None or not set(required).issubset(reader.fieldnames):
                raise GoldenAnnotationPackError("AI_EVALUATION_ANNOTATION_SOURCE_INVALID")
            yield from reader
    except OSError as error:
        raise GoldenAnnotationPackError("AI_EVALUATION_ANNOTATION_SOURCE_UNAVAILABLE") from error


def _required_value(row: dict[str, str], field_name: str) -> str:
    value = row.get(field_name, "").strip()
    if not value:
        raise GoldenAnnotationPackError("AI_EVALUATION_ANNOTATION_SOURCE_INVALID")
    return value


def _parse_date(value: str) -> date | None:
    if not value.strip():
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError as error:
        raise GoldenAnnotationPackError("AI_EVALUATION_ANNOTATION_SOURCE_INVALID") from error


def _length_bucket(value: str) -> GoldenLengthBucket:
    if len(value) < 80:
        return GoldenLengthBucket.SHORT
    if len(value) < 240:
        return GoldenLengthBucket.MEDIUM
    return GoldenLengthBucket.LONG


def _category_bucket(categories: frozenset[str]) -> str:
    return "unknown" if not categories else f"category_{_digest(*sorted(categories))[:16]}"


def _queue_record(candidate: GoldenAnnotationCandidate) -> dict[str, object]:
    return {
        "category_bucket": candidate.category_bucket,
        "delivery_outcome": candidate.delivery_outcome.value,
        "length_bucket": candidate.length_bucket.value,
        "opaque_example_id": candidate.opaque_example_id,
        "review_score": candidate.review_score,
        "review_text": candidate.review_text,
        "source_record_hash": candidate.source_record_hash,
    }


def _blank_label_record(candidate: GoldenAnnotationCandidate) -> dict[str, object]:
    return {
        "annotation_status": "pending",
        "aspect_sentiments": None,
        "category_bucket": candidate.category_bucket,
        "delivery_outcome": candidate.delivery_outcome.value,
        "length_bucket": candidate.length_bucket.value,
        "opaque_example_id": candidate.opaque_example_id,
        "review_score": candidate.review_score,
        "sentiment": None,
        "topics": None,
    }


def _load_queue_metadata(path: Path) -> dict[str, dict[str, object]]:
    queue: dict[str, dict[str, object]] = {}
    for record in _read_jsonl(path):
        example_id = record.get("opaque_example_id")
        if (
            not isinstance(example_id, str)
            or not _is_hash(example_id)
            or not isinstance(record.get("review_score"), int)
            or not isinstance(record.get("delivery_outcome"), str)
        ):
            raise GoldenAnnotationPackError("AI_EVALUATION_ANNOTATION_LABEL_INVALID")
        if example_id in queue:
            raise GoldenAnnotationPackError("AI_EVALUATION_ANNOTATION_LABEL_INVALID")
        queue[example_id] = {
            "category_bucket": record.get("category_bucket"),
            "delivery_outcome": record["delivery_outcome"],
            "length_bucket": record.get("length_bucket"),
            "opaque_example_id": example_id,
            "review_score": record["review_score"],
        }
    return queue


def _load_label_templates(path: Path) -> dict[str, dict[str, object]]:
    templates: dict[str, dict[str, object]] = {}
    for record in _read_jsonl(path):
        example_id = record.get("opaque_example_id")
        if (
            not isinstance(example_id, str)
            or not _is_hash(example_id)
            or record.get("annotation_status") != "pending"
            or example_id in templates
        ):
            raise GoldenAnnotationPackError("AI_EVALUATION_ANNOTATION_LABEL_INVALID")
        templates[example_id] = record
    return templates


def _load_private_predictions(path: Path) -> Mapping[str, ValidatedEnrichment]:
    """Load exact-ID prediction records without exposing their bodies in errors."""

    predictions: dict[str, ValidatedEnrichment] = {}
    for record in _read_jsonl(path):
        example_id = record.get("opaque_example_id")
        if not isinstance(example_id, str) or not _is_hash(example_id) or example_id in predictions:
            raise GoldenAnnotationPackError("AI_EVALUATION_PREDICTION_INVALID")
        payload = {key: value for key, value in record.items() if key != "opaque_example_id"}
        try:
            predictions[example_id] = ValidatedEnrichment.model_validate(payload)
        except (TypeError, ValueError):
            raise GoldenAnnotationPackError("AI_EVALUATION_PREDICTION_INVALID") from None
    return predictions


def _machine_assisted_label_record(
    queue: dict[str, object], template: dict[str, object]
) -> dict[str, object]:
    """Return a low-confidence local suggestion from score/delivery metadata only."""

    score = queue["review_score"]
    delivery = queue["delivery_outcome"]
    if not isinstance(score, int) or not isinstance(delivery, str):
        raise GoldenAnnotationPackError("AI_EVALUATION_ANNOTATION_LABEL_INVALID")
    sentiment = "negative" if score <= 2 else "neutral" if score == 3 else "positive"
    aspect_sentiments: list[dict[str, object]] = []
    topics: list[str] = []
    if delivery == GoldenDeliveryOutcome.DELAYED.value:
        aspect_sentiments.append({"aspect": "delivery", "sentiment": "negative", "confidence": 0.5})
        topics.append("delivery_speed")
    elif delivery == GoldenDeliveryOutcome.ON_TIME.value and score >= 4:
        aspect_sentiments.append({"aspect": "delivery", "sentiment": "positive", "confidence": 0.5})
        topics.append("delivery_speed")
    return {
        "annotation_status": "machine_assisted",
        "aspect_sentiments": aspect_sentiments,
        "category_bucket": template["category_bucket"],
        "delivery_outcome": template["delivery_outcome"],
        "label_source": "offline_score_delivery_heuristic_v1",
        "length_bucket": template["length_bucket"],
        "opaque_example_id": template["opaque_example_id"],
        "review_score": template["review_score"],
        "sentiment": sentiment,
        "topics": topics,
    }


def _write_jsonl(path: Path, records: Iterable[dict[str, object]]) -> None:
    with path.open("x", encoding="utf-8", newline="") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def _read_jsonl(path: Path) -> Iterable[dict[str, object]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise GoldenAnnotationPackError("AI_EVALUATION_ANNOTATION_SOURCE_UNAVAILABLE") from error
    for line in lines:
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            raise GoldenAnnotationPackError("AI_EVALUATION_ANNOTATION_LABEL_INVALID") from error
        if not isinstance(record, dict):
            raise GoldenAnnotationPackError("AI_EVALUATION_ANNOTATION_LABEL_INVALID")
        yield record


def _candidate_dataset_sha256(candidates: Sequence[GoldenAnnotationCandidate]) -> str:
    payload = [
        {
            "category_bucket": item.category_bucket,
            "delivery_outcome": item.delivery_outcome.value,
            "length_bucket": item.length_bucket.value,
            "opaque_example_id": item.opaque_example_id,
            "review_score": item.review_score,
            "source_record_hash": item.source_record_hash,
        }
        for item in sorted(candidates, key=lambda item: item.opaque_example_id)
    ]
    return hashlib.sha256(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()


def _digest(*values: str) -> str:
    return hashlib.sha256("\x1f".join(values).encode()).hexdigest()


def _is_hash(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)
