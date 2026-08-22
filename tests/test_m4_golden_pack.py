"""Synthetic contracts for private M4 golden annotation-pack tooling."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from reviewlens.ai.golden_pack import (
    MINIMUM_GOLDEN_LABELS,
    GoldenAnnotationCandidate,
    GoldenAnnotationPackError,
    build_olist_annotation_candidates,
    load_completed_golden_labels,
    select_stratified_annotation_candidates,
    write_annotation_pack,
    write_machine_assisted_suggestions,
)

RUNBOOK = Path("docs/runbooks/M4_GOLDEN_SET_ANNOTATION.md")


def _candidate(index: int) -> GoldenAnnotationCandidate:
    from reviewlens.ai.evaluation import GoldenDeliveryOutcome, GoldenLengthBucket

    return GoldenAnnotationCandidate(
        opaque_example_id=f"{index:064x}",
        source_record_hash=f"{index + 1000:064x}",
        review_score=(index % 5) + 1,
        length_bucket=tuple(GoldenLengthBucket)[index % 3],
        category_bucket=f"category_{index % 4}",
        delivery_outcome=tuple(GoldenDeliveryOutcome)[index % 3],
        review_text=f"Synthetic private review {index}",
    )


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_m4_annotation_selection_is_deterministic_and_stratified_without_text_in_identity() -> None:
    candidates = tuple(_candidate(index) for index in range(MINIMUM_GOLDEN_LABELS + 20))

    first = select_stratified_annotation_candidates(candidates=candidates, count=200, seed="m4-v1")
    replay = select_stratified_annotation_candidates(
        candidates=tuple(reversed(candidates)), count=200, seed="m4-v1"
    )

    assert first == replay
    assert len(first) == 200
    assert len({candidate.opaque_example_id for candidate in first}) == 200
    assert {candidate.review_score for candidate in first} == {1, 2, 3, 4, 5}
    assert "Synthetic private review" not in repr(first[0])


def test_m4_annotation_pack_keeps_text_only_in_private_queue_and_requires_human_review(
    tmp_path: Path,
) -> None:
    selected = tuple(_candidate(index) for index in range(MINIMUM_GOLDEN_LABELS))
    paths = write_annotation_pack(
        candidates=selected, output_dir=tmp_path / "private", seed="m4-v1"
    )

    queue = paths.annotation_queue_path.read_text(encoding="utf-8")
    labels = paths.labels_path.read_text(encoding="utf-8")
    metadata = json.loads(paths.metadata_path.read_text(encoding="utf-8"))

    assert "Synthetic private review 0" in queue
    assert "Synthetic private review" not in labels
    assert metadata["candidate_count"] == 200
    assert metadata["status"] == "pending_human_review"
    with pytest.raises(
        GoldenAnnotationPackError, match="AI_EVALUATION_ANNOTATION_LABELS_INCOMPLETE"
    ):
        load_completed_golden_labels(labels_path=paths.labels_path)
    with pytest.raises(GoldenAnnotationPackError, match="AI_EVALUATION_ANNOTATION_OUTPUT_EXISTS"):
        write_annotation_pack(candidates=selected, output_dir=tmp_path / "private", seed="m4-v1")


def test_m4_annotation_builder_joins_private_metadata_without_exposing_natural_ids(
    tmp_path: Path,
) -> None:
    reviews: list[dict[str, str]] = []
    for index in range(MINIMUM_GOLDEN_LABELS):
        reviews.append(
            {
                "review_id": f"review-{index}",
                "order_id": f"order-{index}",
                "review_score": str((index % 5) + 1),
                "review_comment_title": "Synthetic title",
                "review_comment_message": f"Synthetic message {index}",
            }
        )
    _write_csv(
        tmp_path / "olist_products_dataset.csv",
        [{"product_id": "product-1", "product_category_name": "synthetic-category"}],
    )
    _write_csv(
        tmp_path / "olist_order_items_dataset.csv",
        [{"order_id": f"order-{index}", "product_id": "product-1"} for index in range(200)],
    )
    _write_csv(
        tmp_path / "olist_orders_dataset.csv",
        [
            {
                "order_id": f"order-{index}",
                "order_delivered_customer_date": "2018-01-02 00:00:00",
                "order_estimated_delivery_date": "2018-01-03 00:00:00",
            }
            for index in range(200)
        ],
    )
    _write_csv(tmp_path / "olist_order_reviews_dataset.csv", reviews)

    candidates = build_olist_annotation_candidates(archive_dir=tmp_path)

    assert len(candidates) == 200
    assert all(candidate.category_bucket.startswith("category_") for candidate in candidates)
    assert all("order-" not in repr(candidate) for candidate in candidates)


def test_m4_machine_assisted_suggestions_are_private_and_cannot_be_human_golden(
    tmp_path: Path,
) -> None:
    selected = tuple(_candidate(index) for index in range(MINIMUM_GOLDEN_LABELS))
    paths = write_annotation_pack(
        candidates=selected, output_dir=tmp_path / "private", seed="m4-v1"
    )
    suggestion_path = tmp_path / "private" / "labels.machine_assisted.jsonl"

    count = write_machine_assisted_suggestions(
        annotation_queue_path=paths.annotation_queue_path,
        labels_path=paths.labels_path,
        output_path=suggestion_path,
    )
    suggestion = suggestion_path.read_text(encoding="utf-8")

    assert count == 200
    assert "machine_assisted" in suggestion
    assert "offline_score_delivery_heuristic_v1" in suggestion
    assert "Synthetic private review" not in suggestion
    with pytest.raises(
        GoldenAnnotationPackError, match="AI_EVALUATION_ANNOTATION_LABELS_INCOMPLETE"
    ):
        load_completed_golden_labels(labels_path=suggestion_path)


def test_m4_annotation_runbook_keeps_the_pack_private_and_requires_human_review() -> None:
    source = RUNBOOK.read_text(encoding="utf-8")

    for required in (
        "private_evaluation/",
        "annotation_queue.jsonl",
        "labels.jsonl",
        "pending",
        "approved",
        "reviewlens-golden-pack generate",
        "reviewlens-golden-pack validate",
        "blind holdout",
        "200+ rows",
    ):
        assert required in source
    assert "không upload lên" in source.lower()
    assert (RUNBOOK.parent / "M4_AI_ENRICHMENT_OPERATIONS.md").exists()
