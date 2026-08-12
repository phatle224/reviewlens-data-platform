"""Typed Olist row validation and streaming file-level quality checks."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path

from reviewlens.ingestion.contracts import (
    DatasetContract,
    IdentitySemantics,
    LogicalType,
)
from reviewlens.ingestion.csv_stream import ParsedCsvRecord, iter_csv_records

ValidatedValue = str | int | Decimal | datetime | None
VALIDATION_PROFILE_VERSION = "olist-validation-v1"
_INTEGER_PATTERN = re.compile(r"^-?(?:0|[1-9][0-9]*)$")
_ZIP_PATTERN = re.compile(r"^[0-9]{5}$")
_STATE_PATTERN = re.compile(r"^[A-Z]{2}$")
_ORDER_STATUSES = frozenset(
    {
        "approved",
        "canceled",
        "created",
        "delivered",
        "invoiced",
        "processing",
        "shipped",
        "unavailable",
    }
)
_PAYMENT_TYPES = frozenset({"boleto", "credit_card", "debit_card", "not_defined", "voucher"})
_NON_NEGATIVE_COLUMNS = frozenset(
    {
        "freight_value",
        "payment_installments",
        "payment_value",
        "price",
        "product_description_lenght",
        "product_height_cm",
        "product_length_cm",
        "product_name_lenght",
        "product_photos_qty",
        "product_weight_g",
        "product_width_cm",
    }
)
_POSITIVE_COLUMNS = frozenset({"order_item_id", "payment_sequential"})


class ValidationCode(StrEnum):
    REQUIRED = "FIELD_REQUIRED"
    INTEGER_INVALID = "INTEGER_INVALID"
    DECIMAL_INVALID = "DECIMAL_INVALID"
    TIMESTAMP_INVALID = "TIMESTAMP_INVALID"
    RANGE_INVALID = "RANGE_INVALID"
    VALUE_NOT_ALLOWED = "VALUE_NOT_ALLOWED"
    FORMAT_INVALID = "FORMAT_INVALID"
    ROW_COUNT_MISMATCH = "FILE_ROW_COUNT_MISMATCH"
    DUPLICATE_IDENTITY = "FILE_DUPLICATE_IDENTITY"


@dataclass(frozen=True, slots=True)
class FieldValidationError:
    code: ValidationCode
    column_name: str


@dataclass(frozen=True, slots=True)
class ValidatedRecord:
    source_row_number: int
    byte_start: int
    byte_end: int
    columns: tuple[str, ...]
    values: tuple[ValidatedValue, ...] = field(repr=False)

    def as_mapping(self) -> dict[str, ValidatedValue]:
        return dict(zip(self.columns, self.values, strict=True))


@dataclass(frozen=True, slots=True)
class RowValidationResult:
    source_row_number: int
    record: ValidatedRecord | None = field(default=None, repr=False)
    errors: tuple[FieldValidationError, ...] = ()

    @property
    def accepted(self) -> bool:
        return self.record is not None and not self.errors


@dataclass(frozen=True, slots=True)
class DatasetValidationReport:
    validation_profile_version: str
    dataset_name: str
    observed_rows: int
    accepted_rows: int
    rejected_rows: int
    duplicate_identity_rows: int
    error_counts: tuple[tuple[str, int], ...]
    file_errors: tuple[ValidationCode, ...]

    @property
    def valid(self) -> bool:
        return self.rejected_rows == 0 and not self.file_errors


def iter_validated_records(
    path: Path, *, dataset: DatasetContract
) -> Iterator[RowValidationResult]:
    for parsed in iter_csv_records(path, expected_header=dataset.expected_header):
        yield validate_parsed_record(parsed, dataset=dataset)


def validate_parsed_record(
    parsed: ParsedCsvRecord,
    *,
    dataset: DatasetContract,
) -> RowValidationResult:
    typed: list[ValidatedValue] = []
    errors: list[FieldValidationError] = []
    for column, raw_value in zip(dataset.columns, parsed.values, strict=True):
        value, error = _parse_value(
            column_name=column.name,
            logical_type=column.logical_type,
            nullable=column.nullable,
            raw_value=raw_value,
        )
        typed.append(value)
        if error is not None:
            errors.append(error)
    if errors:
        return RowValidationResult(source_row_number=parsed.source_row_number, errors=tuple(errors))
    return RowValidationResult(
        source_row_number=parsed.source_row_number,
        record=ValidatedRecord(
            source_row_number=parsed.source_row_number,
            byte_start=parsed.byte_start,
            byte_end=parsed.byte_end,
            columns=dataset.expected_header,
            values=tuple(typed),
        ),
    )


def validate_dataset_file(
    path: Path,
    *,
    dataset: DatasetContract,
    declared_rows: int,
) -> DatasetValidationReport:
    if declared_rows < 0:
        raise ValueError("declared_rows must be non-negative")
    observed_rows = accepted_rows = rejected_rows = duplicate_rows = 0
    counts: Counter[str] = Counter()
    identities: set[str] = set()

    for outcome in iter_validated_records(path, dataset=dataset):
        observed_rows += 1
        if not outcome.accepted or outcome.record is None:
            rejected_rows += 1
            counts.update(error.code.value for error in outcome.errors)
            continue
        accepted_rows += 1
        if dataset.identity_semantics is IdentitySemantics.UNIQUE:
            identity = _identity_digest(dataset, outcome.record.as_mapping())
            if identity in identities:
                duplicate_rows += 1
                counts[ValidationCode.DUPLICATE_IDENTITY.value] += 1
            else:
                identities.add(identity)

    file_errors: list[ValidationCode] = []
    if observed_rows != declared_rows:
        file_errors.append(ValidationCode.ROW_COUNT_MISMATCH)
        counts[ValidationCode.ROW_COUNT_MISMATCH.value] += 1
    if duplicate_rows:
        file_errors.append(ValidationCode.DUPLICATE_IDENTITY)
    return DatasetValidationReport(
        validation_profile_version=VALIDATION_PROFILE_VERSION,
        dataset_name=dataset.dataset_name,
        observed_rows=observed_rows,
        accepted_rows=accepted_rows,
        rejected_rows=rejected_rows,
        duplicate_identity_rows=duplicate_rows,
        error_counts=tuple(sorted(counts.items())),
        file_errors=tuple(file_errors),
    )


def _parse_value(
    *,
    column_name: str,
    logical_type: LogicalType,
    nullable: bool,
    raw_value: str,
) -> tuple[ValidatedValue, FieldValidationError | None]:
    if raw_value == "":
        if nullable:
            return None, None
        return None, FieldValidationError(ValidationCode.REQUIRED, column_name)

    if logical_type is LogicalType.STRING:
        value: ValidatedValue = raw_value
    elif logical_type is LogicalType.INTEGER:
        if _INTEGER_PATTERN.fullmatch(raw_value) is None:
            return None, FieldValidationError(ValidationCode.INTEGER_INVALID, column_name)
        value = int(raw_value)
    elif logical_type is LogicalType.DECIMAL:
        try:
            parsed_decimal = Decimal(raw_value)
        except InvalidOperation:
            return None, FieldValidationError(ValidationCode.DECIMAL_INVALID, column_name)
        if not parsed_decimal.is_finite():
            return None, FieldValidationError(ValidationCode.DECIMAL_INVALID, column_name)
        value = parsed_decimal
    else:
        try:
            value = datetime.strptime(raw_value, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None, FieldValidationError(ValidationCode.TIMESTAMP_INVALID, column_name)

    constraint_error = _validate_constraint(column_name, value)
    if constraint_error is not None:
        return None, FieldValidationError(constraint_error, column_name)
    return value, None


def _validate_constraint(column_name: str, value: ValidatedValue) -> ValidationCode | None:
    if value is None:
        return None
    if column_name == "review_score" and (not isinstance(value, int) or not 1 <= value <= 5):
        return ValidationCode.RANGE_INVALID
    if column_name == "geolocation_lat" and (
        not isinstance(value, Decimal) or not -90 <= value <= 90
    ):
        return ValidationCode.RANGE_INVALID
    if column_name == "geolocation_lng" and (
        not isinstance(value, Decimal) or not -180 <= value <= 180
    ):
        return ValidationCode.RANGE_INVALID
    if column_name in _NON_NEGATIVE_COLUMNS and (
        not isinstance(value, (int, Decimal)) or value < 0
    ):
        return ValidationCode.RANGE_INVALID
    if column_name in _POSITIVE_COLUMNS and (not isinstance(value, int) or value < 1):
        return ValidationCode.RANGE_INVALID
    if column_name == "order_status" and value not in _ORDER_STATUSES:
        return ValidationCode.VALUE_NOT_ALLOWED
    if column_name == "payment_type" and value not in _PAYMENT_TYPES:
        return ValidationCode.VALUE_NOT_ALLOWED
    if column_name.endswith("zip_code_prefix") and (
        not isinstance(value, str) or _ZIP_PATTERN.fullmatch(value) is None
    ):
        return ValidationCode.FORMAT_INVALID
    if column_name.endswith("state") and (
        not isinstance(value, str) or _STATE_PATTERN.fullmatch(value) is None
    ):
        return ValidationCode.FORMAT_INVALID
    return None


def _identity_digest(
    dataset: DatasetContract,
    values: Mapping[str, ValidatedValue],
) -> str:
    payload = [values[name] for name in dataset.identity_fields]
    encoded = json.dumps(payload, default=str, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()
