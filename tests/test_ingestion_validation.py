from __future__ import annotations

import csv
from pathlib import Path

import pytest

from reviewlens.ingestion.contracts import DatasetContract, load_olist_contract
from reviewlens.ingestion.csv_stream import ParsedCsvRecord, iter_csv_records
from reviewlens.ingestion.source import discover_source_snapshot
from reviewlens.ingestion.validation import (
    ValidationCode,
    validate_dataset_file,
    validate_parsed_record,
)
from reviewlens.synthetic.generator import generate_fixture


def _mutated_record(
    root: Path,
    *,
    dataset_name: str,
    column_name: str,
    value: str,
) -> tuple[DatasetContract, ParsedCsvRecord]:
    generate_fixture(root)
    contract = load_olist_contract()
    dataset = next(item for item in contract.datasets if item.dataset_name == dataset_name)
    original = next(
        iter_csv_records(root / dataset.file_name, expected_header=dataset.expected_header)
    )
    values = list(original.values)
    values[dataset.expected_header.index(column_name)] = value
    return dataset, ParsedCsvRecord(
        source_row_number=original.source_row_number,
        byte_start=original.byte_start,
        byte_end=original.byte_end,
        values=tuple(values),
    )


def test_all_nine_synthetic_files_pass_typed_and_file_validation(tmp_path: Path) -> None:
    generate_fixture(tmp_path)
    snapshot = discover_source_snapshot(tmp_path)
    contract = load_olist_contract()

    reports = [
        validate_dataset_file(
            item.path,
            dataset=contract.by_file_name[item.file_name],
            declared_rows=item.observed_rows,
        )
        for item in snapshot.files
    ]

    assert len(reports) == 9
    assert all(report.valid for report in reports)
    assert all(report.validation_profile_version == "olist-validation-v1" for report in reports)
    assert all(report.observed_rows == report.accepted_rows for report in reports)
    assert all(report.rejected_rows == 0 for report in reports)


@pytest.mark.parametrize(
    ("dataset_name", "column_name", "value", "expected_code"),
    [
        ("customers", "customer_id", "", ValidationCode.REQUIRED),
        ("order_items", "order_item_id", "1.5", ValidationCode.INTEGER_INVALID),
        ("order_items", "price", "NaN", ValidationCode.DECIMAL_INVALID),
        ("order_items", "shipping_limit_date", "2025/01/03", ValidationCode.TIMESTAMP_INVALID),
        ("order_reviews", "review_score", "6", ValidationCode.RANGE_INVALID),
        ("geolocation", "geolocation_lat", "-91", ValidationCode.RANGE_INVALID),
        ("orders", "order_status", "unknown", ValidationCode.VALUE_NOT_ALLOWED),
        ("order_payments", "payment_type", "crypto", ValidationCode.VALUE_NOT_ALLOWED),
        ("customers", "customer_zip_code_prefix", "123", ValidationCode.FORMAT_INVALID),
        ("customers", "customer_state", "sp", ValidationCode.FORMAT_INVALID),
    ],
)
def test_field_failures_use_stable_taxonomy_without_raw_value(
    tmp_path: Path,
    dataset_name: str,
    column_name: str,
    value: str,
    expected_code: ValidationCode,
) -> None:
    dataset, parsed = _mutated_record(
        tmp_path,
        dataset_name=dataset_name,
        column_name=column_name,
        value=value,
    )

    result = validate_parsed_record(parsed, dataset=dataset)

    assert not result.accepted
    assert result.record is None
    assert [(error.code, error.column_name) for error in result.errors] == [
        (expected_code, column_name)
    ]
    if value:
        assert value not in repr(result)


def test_nullable_empty_value_becomes_null(tmp_path: Path) -> None:
    dataset, parsed = _mutated_record(
        tmp_path,
        dataset_name="order_reviews",
        column_name="review_comment_message",
        value="",
    )

    result = validate_parsed_record(parsed, dataset=dataset)

    assert result.accepted
    assert result.record is not None
    assert result.record.as_mapping()["review_comment_message"] is None


def test_file_report_detects_declared_count_and_unique_identity_failures(tmp_path: Path) -> None:
    contract = load_olist_contract()
    dataset = contract.by_file_name["olist_customers_dataset.csv"]
    path = tmp_path / dataset.file_name
    rows = [
        ["same", "person-1", "01001", "sao paulo", "SP"],
        ["same", "person-2", "01001", "sao paulo", "SP"],
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(dataset.expected_header)
        writer.writerows(rows)

    report = validate_dataset_file(path, dataset=dataset, declared_rows=3)

    assert report.observed_rows == 2
    assert report.accepted_rows == 2
    assert report.duplicate_identity_rows == 1
    assert report.file_errors == (
        ValidationCode.ROW_COUNT_MISMATCH,
        ValidationCode.DUPLICATE_IDENTITY,
    )
    assert dict(report.error_counts) == {
        ValidationCode.DUPLICATE_IDENTITY.value: 1,
        ValidationCode.ROW_COUNT_MISMATCH.value: 1,
    }


def test_occurrence_identity_allows_repeated_geolocation_zip(tmp_path: Path) -> None:
    contract = load_olist_contract()
    dataset = contract.by_file_name["olist_geolocation_dataset.csv"]
    path = tmp_path / dataset.file_name
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(dataset.expected_header)
        writer.writerow(["01001", "-23.55", "-46.63", "sao paulo", "SP"])
        writer.writerow(["01001", "-23.56", "-46.64", "sao paulo", "SP"])

    report = validate_dataset_file(path, dataset=dataset, declared_rows=2)

    assert report.valid
    assert report.duplicate_identity_rows == 0
