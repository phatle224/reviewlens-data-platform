from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from reviewlens.clock import FrozenClock
from reviewlens.ingestion.contracts import load_olist_contract
from reviewlens.ingestion.csv_stream import iter_csv_records
from reviewlens.ingestion.parquet import ParquetArtifactError
from reviewlens.ingestion.processing import DatasetProcessingReport, process_dataset_file
from reviewlens.ingestion.records import canonical_record_hash
from reviewlens.ingestion.validation import validate_parsed_record
from reviewlens.synthetic.generator import generate_fixture

SOURCE_RELEASE_ID = "olist-test-release"
BATCH_ID = "batch-test"
DATASET_RUN_ID = f"dsrun_{'2' * 64}"
SOURCE_OBJECT_ID = f"srcobj_{'3' * 64}"
SOURCE_SHA256 = "4" * 64
INSTANT = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)


def _write_reviews(path: Path) -> None:
    dataset = load_olist_contract().by_file_name[path.name]
    rows = [
        [
            "review-1",
            "order-1",
            "5",
            "Excelente",
            "ótimo\nproduto",
            "2018-01-01 00:00:00",
            "2018-01-02 03:04:05",
        ],
        [
            "review-bad",
            "order-bad",
            "9",
            "Falhou",
            "seeded-private-row-canary",
            "2018-01-01 00:00:00",
            "2018-01-02 03:04:05",
        ],
        [
            "review-1",
            "order-1",
            "5",
            "Excelente",
            "ótimo\nproduto",
            "2018-01-01 00:00:00",
            "2018-01-02 03:04:05",
        ],
        [
            "review-replay",
            "order-replay",
            "4",
            "Bom",
            "entrega rápida",
            "2018-02-01 00:00:00",
            "2018-02-02 03:04:05",
        ],
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(dataset.expected_header)
        writer.writerows(rows)


def _last_record_hash(path: Path) -> str:
    dataset = load_olist_contract().by_file_name[path.name]
    parsed = tuple(iter_csv_records(path, expected_header=dataset.expected_header))[-1]
    outcome = validate_parsed_record(parsed, dataset=dataset)
    assert outcome.record is not None
    return canonical_record_hash(dataset=dataset, values=outcome.record.as_mapping())


def test_processing_writes_typed_raw_and_partitioned_quarantine(tmp_path: Path) -> None:
    dataset = load_olist_contract().by_file_name["olist_order_reviews_dataset.csv"]
    source = tmp_path / dataset.file_name
    _write_reviews(source)

    report = process_dataset_file(
        source,
        dataset=dataset,
        output_root=tmp_path / "private",
        source_release_id=SOURCE_RELEASE_ID,
        ingestion_batch_id=BATCH_ID,
        dataset_run_id=DATASET_RUN_ID,
        source_object_id=SOURCE_OBJECT_ID,
        source_object_sha256=SOURCE_SHA256,
        existing_record_hashes=[_last_record_hash(source)],
        clock=FrozenClock(INSTANT),
        row_group_size=1,
    )

    assert report.reconciled
    assert (
        report.observed_rows,
        report.new_rows,
        report.replay_rows,
        report.duplicate_rows,
        report.rejected_rows,
        report.parse_failed_rows,
    ) == (4, 1, 1, 1, 1, 0)
    assert report.raw_artifact is not None
    assert report.raw_artifact.object_key.startswith(
        f"raw/order_reviews/source_release_id={SOURCE_RELEASE_ID}/batch_id={BATCH_ID}/"
    )
    raw_path = tmp_path / "private" / report.raw_artifact.object_key
    raw_table = pq.ParquetFile(raw_path).read()  # type: ignore[no-untyped-call]
    assert raw_table.num_rows == 1
    assert raw_table.schema.field("review_score").type == pa.int64()
    assert raw_table.schema.field("review_creation_date").type == pa.timestamp("us")
    assert raw_table.schema.field("ingested_at").type == pa.timestamp("us", tz="UTC")
    raw_row = raw_table.to_pylist()[0]
    assert raw_row["review_comment_message"] == "ótimo\nproduto"
    assert json.loads(raw_row["raw_payload"])["review_comment_message"] == "ótimo\nproduto"

    assert {
        artifact.object_key.split("error_code=")[1].split("/")[0]
        for artifact in report.quarantine_artifacts
    } == {
        "DUPLICATE_RECORD",
        "RANGE_INVALID",
    }
    quarantine_rows = [
        row
        for artifact in report.quarantine_artifacts
        for row in pq.ParquetFile(  # type: ignore[no-untyped-call]
            tmp_path / "private" / artifact.object_key
        )
        .read()
        .to_pylist()
    ]
    assert len(quarantine_rows) == 2
    assert {row["source_row_number"] for row in quarantine_rows} == {3, 4}
    assert all(row["raw_reference"].startswith(SOURCE_OBJECT_ID) for row in quarantine_rows)
    assert "seeded-private-row-canary" not in repr(report)

    manifest_path = tmp_path / "private" / report.raw_artifact.manifest_key
    manifest_text = manifest_path.read_text(encoding="utf-8")
    assert "seeded-private-row-canary" not in manifest_text
    assert str(tmp_path) not in manifest_text
    assert json.loads(manifest_text)["row_count"] == 1


def test_processing_quarantines_file_parse_failure_and_reconciles(tmp_path: Path) -> None:
    dataset = load_olist_contract().by_file_name["olist_order_reviews_dataset.csv"]
    source = tmp_path / dataset.file_name
    header = ",".join(dataset.expected_header)
    source.write_text(
        header
        + "\nreview-1,order-1,5,title,message,2018-01-01 00:00:00,2018-01-02 00:00:00"
        + '\nreview-2,order-2,4,title,"unterminated\n',
        encoding="utf-8",
    )

    report = process_dataset_file(
        source,
        dataset=dataset,
        output_root=tmp_path / "private",
        source_release_id=SOURCE_RELEASE_ID,
        ingestion_batch_id=BATCH_ID,
        dataset_run_id=DATASET_RUN_ID,
        source_object_id=SOURCE_OBJECT_ID,
        source_object_sha256=SOURCE_SHA256,
        clock=FrozenClock(INSTANT),
    )

    assert report.reconciled
    assert (report.observed_rows, report.new_rows, report.parse_failed_rows) == (2, 1, 1)
    assert report.file_failures == 1
    assert len(report.quarantine_artifacts) == 1
    artifact = report.quarantine_artifacts[0]
    assert "error_code=CSV_MALFORMED" in artifact.object_key
    row = (
        pq.ParquetFile(  # type: ignore[no-untyped-call]
            tmp_path / "private" / artifact.object_key
        )
        .read()
        .to_pylist()[0]
    )
    assert row["source_row_number"] == 3
    assert row["raw_payload"] is None


def test_decimal_round_trip_uses_fixed_typed_schema(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    generate_fixture(source_root)
    dataset = load_olist_contract().by_file_name["olist_order_items_dataset.csv"]

    report = process_dataset_file(
        source_root / dataset.file_name,
        dataset=dataset,
        output_root=tmp_path / "p",
        source_release_id=SOURCE_RELEASE_ID,
        ingestion_batch_id=BATCH_ID,
        dataset_run_id=DATASET_RUN_ID,
        source_object_id=SOURCE_OBJECT_ID,
        source_object_sha256=SOURCE_SHA256,
        clock=FrozenClock(INSTANT),
    )

    assert report.raw_artifact is not None
    table = pq.ParquetFile(  # type: ignore[no-untyped-call]
        tmp_path / "p" / report.raw_artifact.object_key
    ).read()
    assert table.schema.field("price").type == pa.decimal128(38, 18)
    assert all(isinstance(value, Decimal) for value in table.column("price").to_pylist())


def test_parquet_create_only_replay_is_stable_and_conflict_is_denied(tmp_path: Path) -> None:
    dataset = load_olist_contract().by_file_name["olist_order_reviews_dataset.csv"]
    source = tmp_path / dataset.file_name
    _write_reviews(source)

    def process() -> DatasetProcessingReport:
        return process_dataset_file(
            source,
            dataset=dataset,
            output_root=tmp_path / "private",
            source_release_id=SOURCE_RELEASE_ID,
            ingestion_batch_id=BATCH_ID,
            dataset_run_id=DATASET_RUN_ID,
            source_object_id=SOURCE_OBJECT_ID,
            source_object_sha256=SOURCE_SHA256,
            existing_record_hashes=[_last_record_hash(source)],
            clock=FrozenClock(INSTANT),
        )

    first = process()
    second = process()

    assert first.raw_artifact is not None and second.raw_artifact is not None
    assert not first.raw_artifact.replayed
    assert second.raw_artifact.replayed
    assert first.raw_artifact.sha256 == second.raw_artifact.sha256

    raw_path = tmp_path / "private" / first.raw_artifact.object_key
    raw_path.write_bytes(b"conflicting-private-artifact")
    with pytest.raises(ParquetArtifactError, match="PARQUET_ARTIFACT_INVALID"):
        process()
