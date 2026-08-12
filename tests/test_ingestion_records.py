from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from reviewlens.ingestion.contracts import DatasetContract, load_olist_contract
from reviewlens.ingestion.csv_stream import ParsedCsvRecord, iter_csv_records
from reviewlens.ingestion.records import (
    RecordDisposition,
    RecordHashError,
    RecordHashTracker,
    canonical_record_hash,
)
from reviewlens.ingestion.validation import ValidatedValue, validate_parsed_record
from reviewlens.synthetic.generator import generate_fixture


def _validated_order_item(root: Path) -> tuple[dict[str, ValidatedValue], DatasetContract]:
    generate_fixture(root)
    dataset = load_olist_contract().by_file_name["olist_order_items_dataset.csv"]
    parsed = next(
        iter_csv_records(root / dataset.file_name, expected_header=dataset.expected_header)
    )
    outcome = validate_parsed_record(parsed, dataset=dataset)
    assert outcome.record is not None
    return outcome.record.as_mapping(), dataset


def test_record_hash_is_mapping_order_and_runtime_position_independent(tmp_path: Path) -> None:
    values, dataset = _validated_order_item(tmp_path)
    reordered = dict(reversed(tuple(values.items())))

    first = canonical_record_hash(dataset=dataset, values=values)
    second = canonical_record_hash(dataset=dataset, values=reordered)

    assert first == second
    assert len(first) == 64


def test_equivalent_decimal_encodings_have_same_hash(tmp_path: Path) -> None:
    generate_fixture(tmp_path)
    dataset = load_olist_contract().by_file_name["olist_order_items_dataset.csv"]
    parsed = next(
        iter_csv_records(tmp_path / dataset.file_name, expected_header=dataset.expected_header)
    )
    price_index = dataset.expected_header.index("price")
    alternate_values = list(parsed.values)
    alternate_values[price_index] = f"{Decimal(parsed.values[price_index]):.4f}"
    alternate = ParsedCsvRecord(
        source_row_number=999,
        byte_start=9999,
        byte_end=10099,
        values=tuple(alternate_values),
    )
    first = validate_parsed_record(parsed, dataset=dataset)
    second = validate_parsed_record(alternate, dataset=dataset)
    assert first.record is not None and second.record is not None

    assert canonical_record_hash(
        dataset=dataset, values=first.record.as_mapping()
    ) == canonical_record_hash(dataset=dataset, values=second.record.as_mapping())


def test_business_value_change_changes_record_hash(tmp_path: Path) -> None:
    values, dataset = _validated_order_item(tmp_path)
    changed = dict(values)
    changed["price"] = Decimal("999.99")

    assert canonical_record_hash(dataset=dataset, values=values) != canonical_record_hash(
        dataset=dataset,
        values=changed,
    )


def test_tracker_distinguishes_new_replay_and_candidate_duplicate(tmp_path: Path) -> None:
    values, dataset = _validated_order_item(tmp_path)
    record_hash = canonical_record_hash(dataset=dataset, values=values)
    new_hash = "f" * 64 if record_hash != "f" * 64 else "e" * 64
    tracker = RecordHashTracker(existing_hashes=[record_hash])

    assert tracker.observe(record_hash) is RecordDisposition.REPLAY
    assert tracker.observe(record_hash) is RecordDisposition.DUPLICATE
    assert tracker.observe(new_hash) is RecordDisposition.NEW
    assert tracker.observe(new_hash) is RecordDisposition.DUPLICATE


def test_record_hash_failures_are_sanitized(tmp_path: Path) -> None:
    values, dataset = _validated_order_item(tmp_path)
    values["seeded-private-row-canary"] = "secret"

    with pytest.raises(RecordHashError) as bad_values:
        canonical_record_hash(dataset=dataset, values=values)
    with pytest.raises(RecordHashError) as bad_history:
        RecordHashTracker(existing_hashes=["seeded-private-row-canary"])

    assert str(bad_values.value) == "RECORD_HASH_INVALID"
    assert str(bad_history.value) == "RECORD_HASH_INVALID"
    assert "seeded-private-row-canary" not in str(bad_values.value)


def test_record_hash_rejects_untyped_value_even_with_exact_columns(tmp_path: Path) -> None:
    values, dataset = _validated_order_item(tmp_path)
    values["price"] = "39.90"

    with pytest.raises(RecordHashError, match="RECORD_HASH_INVALID"):
        canonical_record_hash(dataset=dataset, values=values)
