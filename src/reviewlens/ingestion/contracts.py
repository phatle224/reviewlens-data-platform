"""Typed, versioned contract for the nine-file Olist source snapshot."""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from importlib.resources import files
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

EXPECTED_OLIST_FILES = frozenset(
    {
        "olist_customers_dataset.csv",
        "olist_geolocation_dataset.csv",
        "olist_order_items_dataset.csv",
        "olist_order_payments_dataset.csv",
        "olist_order_reviews_dataset.csv",
        "olist_orders_dataset.csv",
        "olist_products_dataset.csv",
        "olist_sellers_dataset.csv",
        "product_category_name_translation.csv",
    }
)
EXPECTED_OLIST_DATASETS = frozenset(
    {
        "customers",
        "geolocation",
        "order_items",
        "order_payments",
        "order_reviews",
        "orders",
        "products",
        "sellers",
        "category_translation",
    }
)


class SourceContractError(ValueError):
    """Sanitized contract failure that never echoes source content."""

    code = "SOURCE_CONTRACT_INVALID"

    def __init__(self) -> None:
        super().__init__(self.code)


class LogicalType(StrEnum):
    STRING = "string"
    INTEGER = "integer"
    DECIMAL = "decimal"
    TIMESTAMP = "timestamp"


class DataClass(StrEnum):
    INTERNAL = "internal"
    PSEUDONYMOUS = "pseudonymous"
    QUASI_IDENTIFIER = "quasi_identifier"
    RESTRICTED = "restricted"
    PUBLIC_METADATA = "public_metadata"


class IdentitySemantics(StrEnum):
    UNIQUE = "unique"
    OCCURRENCE = "occurrence"


class ColumnContract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    logical_type: LogicalType
    nullable: bool


class DatasetContract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    dataset_name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    file_name: str = Field(pattern=r"^[a-z0-9_]+\.csv$")
    required: bool
    data_class: DataClass
    identity_fields: tuple[str, ...] = Field(min_length=1)
    identity_semantics: IdentitySemantics
    columns: tuple[ColumnContract, ...] = Field(min_length=1)

    @property
    def expected_header(self) -> tuple[str, ...]:
        return tuple(column.name for column in self.columns)

    @model_validator(mode="after")
    def validate_columns_and_identity(self) -> DatasetContract:
        column_names = self.expected_header
        if len(column_names) != len(set(column_names)):
            raise ValueError("dataset column names must be unique")
        if len(self.identity_fields) != len(set(self.identity_fields)):
            raise ValueError("identity fields must be unique")
        if not set(self.identity_fields).issubset(column_names):
            raise ValueError("identity fields must reference declared columns")
        return self


class SourceContract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    contract_version: str = Field(pattern=r"^olist-source-v[1-9][0-9]*$")
    manifest_version: str = Field(pattern=r"^olist-manifest-v[1-9][0-9]*$")
    source_name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    source_contract: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    license_id: str
    datasets: tuple[DatasetContract, ...] = Field(min_length=1)

    @property
    def required_file_names(self) -> tuple[str, ...]:
        return tuple(sorted(dataset.file_name for dataset in self.datasets if dataset.required))

    @property
    def by_file_name(self) -> dict[str, DatasetContract]:
        return {dataset.file_name: dataset for dataset in self.datasets}

    @model_validator(mode="after")
    def validate_olist_baseline(self) -> SourceContract:
        file_names = [dataset.file_name for dataset in self.datasets]
        dataset_names = [dataset.dataset_name for dataset in self.datasets]
        if len(file_names) != len(set(file_names)):
            raise ValueError("source filenames must be unique")
        if len(dataset_names) != len(set(dataset_names)):
            raise ValueError("logical dataset names must be unique")
        if set(file_names) != EXPECTED_OLIST_FILES:
            raise ValueError("Olist contract must contain exactly nine expected files")
        if set(dataset_names) != EXPECTED_OLIST_DATASETS:
            raise ValueError("Olist contract must contain exactly nine expected datasets")
        if not all(dataset.required for dataset in self.datasets):
            raise ValueError("all nine Olist datasets must be required")
        if self.source_name != "olist":
            raise ValueError("source name must be olist")
        if self.source_contract != "olist-brazilian-ecommerce":
            raise ValueError("unexpected Olist source contract")
        if self.license_id != "CC-BY-NC-SA-4.0":
            raise ValueError("Olist license contract cannot be weakened")
        return self


def parse_source_contract(payload: str | bytes | dict[str, Any]) -> SourceContract:
    """Parse an untrusted contract without leaking its contents on failure."""

    try:
        if isinstance(payload, dict):
            return SourceContract.model_validate(payload)
        return SourceContract.model_validate_json(payload)
    except (ValidationError, ValueError, TypeError):
        raise SourceContractError() from None


@lru_cache(maxsize=1)
def load_olist_contract() -> SourceContract:
    resource = files("reviewlens.ingestion").joinpath("olist_source_contract.json")
    return parse_source_contract(resource.read_bytes())
