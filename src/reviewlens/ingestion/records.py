"""Canonical record hashes and explicit duplicate/replay classification."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Iterable, Mapping
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from reviewlens.ingestion.contracts import DatasetContract, LogicalType
from reviewlens.ingestion.validation import ValidatedValue

RECORD_HASH_VERSION = "olist-record-hash-v1"
_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class RecordHashError(ValueError):
    code = "RECORD_HASH_INVALID"

    def __init__(self) -> None:
        super().__init__(self.code)


class RecordDisposition(StrEnum):
    NEW = "NEW"
    REPLAY = "REPLAY"
    DUPLICATE = "DUPLICATE"


def canonical_record_hash(
    *,
    dataset: DatasetContract,
    values: Mapping[str, ValidatedValue],
) -> str:
    """Hash typed business values in contract order, excluding all lineage metadata."""

    if set(values) != set(dataset.expected_header):
        raise RecordHashError()
    canonical_values: list[list[str | int | None]] = []
    for column in dataset.columns:
        value = values[column.name]
        if not _value_matches_contract(
            value,
            logical_type=column.logical_type,
            nullable=column.nullable,
        ):
            raise RecordHashError()
        canonical_values.append([column.name, _canonical_value(value)])
    payload = json.dumps(
        {
            "contract": RECORD_HASH_VERSION,
            "dataset_name": dataset.dataset_name,
            "values": canonical_values,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class RecordHashTracker:
    """Classify hashes against committed history and duplicates in the candidate."""

    def __init__(self, existing_hashes: Iterable[str] = ()) -> None:
        existing = set(existing_hashes)
        if any(_HASH_PATTERN.fullmatch(value) is None for value in existing):
            raise RecordHashError()
        self._existing = existing
        self._candidate_seen: set[str] = set()

    def observe(self, record_hash: str) -> RecordDisposition:
        if _HASH_PATTERN.fullmatch(record_hash) is None:
            raise RecordHashError()
        if record_hash in self._candidate_seen:
            return RecordDisposition.DUPLICATE
        self._candidate_seen.add(record_hash)
        if record_hash in self._existing:
            return RecordDisposition.REPLAY
        return RecordDisposition.NEW


def _canonical_value(value: ValidatedValue) -> str | int | None:
    if value is None:
        return value
    if isinstance(value, bool):
        raise RecordHashError()
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise RecordHashError()
        normalized = format(value, "f")
        if "." in normalized:
            normalized = normalized.rstrip("0").rstrip(".")
        return "0" if normalized in {"-0", ""} else normalized
    raise RecordHashError()


def _value_matches_contract(
    value: ValidatedValue,
    *,
    logical_type: LogicalType,
    nullable: bool,
) -> bool:
    if value is None:
        return nullable
    if logical_type is LogicalType.STRING:
        return isinstance(value, str)
    if logical_type is LogicalType.INTEGER:
        return isinstance(value, int) and not isinstance(value, bool)
    if logical_type is LogicalType.DECIMAL:
        return isinstance(value, Decimal) and value.is_finite()
    return isinstance(value, datetime)
