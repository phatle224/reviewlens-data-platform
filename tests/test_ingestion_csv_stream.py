from __future__ import annotations

import tracemalloc
from pathlib import Path

import pytest

from reviewlens.ingestion.csv_stream import (
    CsvStreamCode,
    CsvStreamError,
    iter_csv_records,
)


def test_stream_parser_preserves_multiline_values_and_exact_byte_offsets(tmp_path: Path) -> None:
    path = tmp_path / "multiline.csv"
    body = b'\xef\xbb\xbfkey,text\r\n1,"hello\nworld"\r\n2,plain'
    path.write_bytes(body)

    records = list(
        iter_csv_records(
            path,
            expected_header=("key", "text"),
            chunk_bytes=3,
        )
    )

    assert [record.source_row_number for record in records] == [2, 3]
    assert [record.values for record in records] == [("1", "hello\nworld"), ("2", "plain")]
    expected_raw = [b'1,"hello\nworld"', b"2,plain"]
    for record, raw in zip(records, expected_raw, strict=True):
        assert body[record.byte_start : record.byte_end] == raw
    assert "hello" not in repr(records[0])


def test_stream_parser_handles_escaped_quotes_and_trailing_lf(tmp_path: Path) -> None:
    path = tmp_path / "quotes.csv"
    path.write_bytes(b'key,text\n1,"a ""quoted"" value"\n')

    records = list(iter_csv_records(path, expected_header=("key", "text"), chunk_bytes=1))

    assert len(records) == 1
    assert records[0].values == ("1", 'a "quoted" value')
    assert records[0].source_row_number == 2


@pytest.mark.parametrize(
    ("body", "expected_code", "expected_row"),
    [
        (b"key,text\n1,\xff\n", CsvStreamCode.ENCODING_INVALID, 2),
        (b'key,text\n1,"unterminated\n', CsvStreamCode.MALFORMED, 2),
        (b"key,text\n1,ok,extra\n", CsvStreamCode.FIELD_COUNT_MISMATCH, 2),
        (b"wrong,text\n1,ok\n", CsvStreamCode.HEADER_MISMATCH, 1),
        (b"", CsvStreamCode.FILE_EMPTY, None),
    ],
)
def test_stream_parser_failures_are_stable_and_row_safe(
    tmp_path: Path,
    body: bytes,
    expected_code: CsvStreamCode,
    expected_row: int | None,
) -> None:
    path = tmp_path / "seeded-private-row-canary.csv"
    path.write_bytes(body)

    with pytest.raises(CsvStreamError) as captured:
        list(iter_csv_records(path, expected_header=("key", "text"), chunk_bytes=2))

    assert captured.value.code is expected_code
    assert captured.value.source_row_number == expected_row
    assert "seeded-private-row-canary" not in str(captured.value)
    assert str(tmp_path) not in str(captured.value)


def test_stream_parser_rejects_oversized_logical_record(tmp_path: Path) -> None:
    path = tmp_path / "large-record.csv"
    path.write_bytes(b"key,text\r\n1," + b"x" * 30 + b"\r\n")

    boundary = list(
        iter_csv_records(
            path,
            expected_header=("key", "text"),
            chunk_bytes=4,
            max_record_bytes=32,
        )
    )
    assert len(boundary) == 1

    path.write_bytes(b"key,text\n1," + b"x" * 31 + b"\n")

    with pytest.raises(CsvStreamError) as captured:
        list(
            iter_csv_records(
                path,
                expected_header=("key", "text"),
                chunk_bytes=4,
                max_record_bytes=32,
            )
        )

    assert captured.value.code is CsvStreamCode.RECORD_TOO_LARGE
    assert captured.value.source_row_number == 2


def test_large_stream_stays_inside_bounded_memory_envelope(tmp_path: Path) -> None:
    path = tmp_path / "large-geolocation-like.csv"
    expected_rows = 100_000
    with path.open("wb") as handle:
        handle.write(b"zip,lat,lng\n")
        for row_number in range(expected_rows):
            handle.write(f"{row_number % 99999:05d},-23.5505,-46.6333\n".encode("ascii"))

    tracemalloc.start()
    try:
        observed_rows = sum(
            1
            for _ in iter_csv_records(
                path,
                expected_header=("zip", "lat", "lng"),
                chunk_bytes=16_384,
                max_record_bytes=1_024,
            )
        )
        _, peak_bytes = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert observed_rows == expected_rows
    assert peak_bytes < 2_000_000


def test_parser_rejects_missing_file_and_unsafe_options(tmp_path: Path) -> None:
    missing = tmp_path / "missing.csv"

    with pytest.raises(CsvStreamError) as missing_error:
        list(iter_csv_records(missing, expected_header=("key",)))
    with pytest.raises(CsvStreamError) as option_error:
        list(iter_csv_records(missing, expected_header=(), chunk_bytes=0))

    assert missing_error.value.code is CsvStreamCode.FILE_INVALID
    assert option_error.value.code is CsvStreamCode.FILE_INVALID
