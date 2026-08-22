"""Offline contracts for the bounded private M4 blind-holdout pilot."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from reviewlens.ai.enrichment import EnrichmentVersionInput
from reviewlens.ai.evaluation import GoldenDeliveryOutcome, GoldenLengthBucket
from reviewlens.ai.golden_pack import (
    MINIMUM_GOLDEN_LABELS,
    GoldenAnnotationCandidate,
    load_completed_golden_labels,
    write_annotation_pack,
)
from reviewlens.ai.holdout_pilot import (
    HoldoutPilotError,
    preflight_private_holdout,
)


def _candidate(index: int) -> GoldenAnnotationCandidate:
    return GoldenAnnotationCandidate(
        opaque_example_id=f"{index:064x}",
        source_record_hash=f"{index + 1000:064x}",
        review_score=(index % 5) + 1,
        length_bucket=tuple(GoldenLengthBucket)[index % 3],
        category_bucket=f"category_{index % 4}",
        delivery_outcome=tuple(GoldenDeliveryOutcome)[index % 3],
        review_text=f"Synthetic private review {index}",
    )


def _approved_pack(tmp_path: Path) -> tuple[Path, Path]:
    paths = write_annotation_pack(
        candidates=tuple(_candidate(index) for index in range(MINIMUM_GOLDEN_LABELS)),
        output_dir=tmp_path / "private",
        seed="m4-v1",
    )
    records = [
        json.loads(line) for line in paths.labels_path.read_text(encoding="utf-8").splitlines()
    ]
    for record in records:
        record.update(
            {
                "annotation_status": "approved",
                "aspect_sentiments": [],
                "sentiment": "neutral",
                "topics": [],
            }
        )
    paths.labels_path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )
    return paths.labels_path, paths.annotation_queue_path


def _version() -> EnrichmentVersionInput:
    return EnrichmentVersionInput(
        model_slug="google/gemini-2.5-flash-lite",
        provider_policy_version="openrouter-data-collection-deny-v1",
        prompt_version="pt-br-enrichment-untrusted-evidence-v1",
    )


def test_m4_holdout_pilot_preflight_approves_exact_blind_holdout(tmp_path: Path) -> None:
    labels_path, queue_path = _approved_pack(tmp_path)

    preflight, items = preflight_private_holdout(
        labels_path=labels_path,
        annotation_queue_path=queue_path,
        split_seed="m4-eval-v1",
        version_input=_version(),
    )

    assert preflight.holdout_count == 40
    assert preflight.approved_count == 40
    assert len(items) == 40
    assert all(item.projection.decision.value == "approved" for item in items)
    assert "Synthetic private review" not in repr(items[0])


def test_m4_holdout_pilot_preflight_blocks_every_provider_call_when_dlp_fails(
    tmp_path: Path,
) -> None:
    labels_path, queue_path = _approved_pack(tmp_path)
    labels = load_completed_golden_labels(labels_path=labels_path)
    from reviewlens.ai.evaluation import stratified_golden_holdout_split

    split = stratified_golden_holdout_split(labels=labels, split_seed="m4-eval-v1")
    records = [json.loads(line) for line in queue_path.read_text(encoding="utf-8").splitlines()]
    for record in records:
        if record["opaque_example_id"] == split.holdout_ids[0]:
            record["review_text"] = "password should never cross the AI boundary"
    queue_path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )

    with pytest.raises(HoldoutPilotError, match="AI_ENRICHMENT_PILOT_DLP_INCOMPLETE"):
        preflight_private_holdout(
            labels_path=labels_path,
            annotation_queue_path=queue_path,
            split_seed="m4-eval-v1",
            version_input=_version(),
        )
