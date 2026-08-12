"""Bounded binary CSV streaming with deterministic logical-row byte offsets."""

from __future__ import annotations

import csv
import io
from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import BinaryIO

DEFAULT_CHUNK_BYTES = 65_536
DEFAULT_MAX_RECORD_BYTES = 8_388_608


class CsvStreamCode(StrEnum):
    FILE_INVALID = "CSV_FILE_INVALID"
    FILE_EMPTY = "CSV_FILE_EMPTY"
    HEADER_MISMATCH = "CSV_HEADER_MISMATCH"
    ENCODING_INVALID = "CSV_ENCODING_INVALID"
    MALFORMED = "CSV_MALFORMED"
    FIELD_COUNT_MISMATCH = "CSV_FIELD_COUNT_MISMATCH"
    RECORD_TOO_LARGE = "CSV_RECORD_TOO_LARGE"


class CsvStreamError(RuntimeError):
    """Stable parser failure containing position metadata but never row content/path."""

    def __init__(self, code: CsvStreamCode, *, source_row_number: int | None = None) -> None:
        self.code = code
        self.source_row_number = source_row_number
        context = f":{source_row_number}" if source_row_number is not None else ""
        super().__init__(f"{code.value}{context}")


@dataclass(frozen=True, slots=True)
class ParsedCsvRecord:
    """One data record; byte interval is half-open and excludes its line delimiter."""

    source_row_number: int
    byte_start: int
    byte_end: int
    values: tuple[str, ...] = field(repr=False)


def iter_csv_records(
    path: Path,
    *,
    expected_header: tuple[str, ...],
    chunk_bytes: int = DEFAULT_CHUNK_BYTES,
    max_record_bytes: int = DEFAULT_MAX_RECORD_BYTES,
) -> Iterator[ParsedCsvRecord]:
    """Yield logical data records without loading the complete CSV into memory.

    ``source_row_number`` is the one-based logical CSV record number including
    the header, so the first data record is 2 even when quoted fields span lines.
    Byte offsets address the original file bytes and exclude CRLF/LF delimiters.
    """

    if not expected_header or chunk_bytes < 1 or max_record_bytes < 1:
        raise CsvStreamError(CsvStreamCode.FILE_INVALID)
    if not path.is_file() or path.is_symlink():
        raise CsvStreamError(CsvStreamCode.FILE_INVALID)

    try:
        with path.open("rb") as handle:
            raw_records = _iter_raw_records(
                handle,
                chunk_bytes=chunk_bytes,
                max_record_bytes=max_record_bytes,
            )
            try:
                _, _, raw_header = next(raw_records)
            except StopIteration:
                raise CsvStreamError(CsvStreamCode.FILE_EMPTY) from None
            header = _parse_record(raw_header, source_row_number=1, header=True)
            if header != expected_header:
                raise CsvStreamError(CsvStreamCode.HEADER_MISMATCH, source_row_number=1)

            for source_row_number, (byte_start, byte_end, raw_record) in enumerate(
                raw_records,
                start=2,
            ):
                values = _parse_record(
                    raw_record,
                    source_row_number=source_row_number,
                    header=False,
                )
                if len(values) != len(expected_header):
                    raise CsvStreamError(
                        CsvStreamCode.FIELD_COUNT_MISMATCH,
                        source_row_number=source_row_number,
                    )
                yield ParsedCsvRecord(
                    source_row_number=source_row_number,
                    byte_start=byte_start,
                    byte_end=byte_end,
                    values=values,
                )
    except CsvStreamError:
        raise
    except OSError:
        raise CsvStreamError(CsvStreamCode.FILE_INVALID) from None


def _iter_raw_records(
    handle: BinaryIO,
    *,
    chunk_bytes: int,
    max_record_bytes: int,
) -> Iterator[tuple[int, int, bytes]]:
    buffer = bytearray()
    byte_cursor = 0
    record_start = 0
    logical_record_number = 1
    in_quotes = False
    quote_pending = False

    while chunk := handle.read(chunk_bytes):
        for value in chunk:
            buffer.append(value)
            byte_cursor += 1

            if value == 0x22:  # ASCII double quote
                if in_quotes:
                    # Toggle between an escaped pair and a possible closing quote.
                    quote_pending = not quote_pending
                else:
                    in_quotes = True
            else:
                if in_quotes and quote_pending:
                    in_quotes = False
                    quote_pending = False
                if value == 0x0A and not in_quotes:  # LF or CRLF record delimiter.
                    raw_record = bytes(buffer[:-1])
                    if raw_record.endswith(b"\r"):
                        raw_record = raw_record[:-1]
                    yield record_start, record_start + len(raw_record), raw_record
                    record_start = byte_cursor
                    logical_record_number += 1
                    buffer.clear()
                    continue

            # Permit exactly one outer CR beyond the cap only while waiting for LF.
            waiting_for_lf = len(buffer) == max_record_bytes + 1 and value == 0x0D and not in_quotes
            if len(buffer) > max_record_bytes and not waiting_for_lf:
                raise CsvStreamError(
                    CsvStreamCode.RECORD_TOO_LARGE,
                    source_row_number=logical_record_number,
                )

    if in_quotes and quote_pending:
        in_quotes = False
    if in_quotes:
        raise CsvStreamError(
            CsvStreamCode.MALFORMED,
            source_row_number=logical_record_number,
        )
    if len(buffer) > max_record_bytes:
        raise CsvStreamError(
            CsvStreamCode.RECORD_TOO_LARGE,
            source_row_number=logical_record_number,
        )
    if buffer:
        yield record_start, byte_cursor, bytes(buffer)


def _parse_record(
    raw_record: bytes,
    *,
    source_row_number: int,
    header: bool,
) -> tuple[str, ...]:
    try:
        encoding = "utf-8-sig" if header else "utf-8"
        decoded = raw_record.decode(encoding)
    except UnicodeDecodeError:
        raise CsvStreamError(
            CsvStreamCode.ENCODING_INVALID,
            source_row_number=source_row_number,
        ) from None

    try:
        parsed = list(csv.reader(io.StringIO(decoded, newline=""), strict=True))
    except csv.Error:
        raise CsvStreamError(
            CsvStreamCode.MALFORMED,
            source_row_number=source_row_number,
        ) from None
    if len(parsed) != 1:
        raise CsvStreamError(
            CsvStreamCode.MALFORMED,
            source_row_number=source_row_number,
        )
    return tuple(parsed[0])
