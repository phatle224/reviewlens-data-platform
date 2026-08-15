"""Fail-closed semantic catalog used by dashboards and guarded SQL."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SEMANTIC_CATALOG_VERSION = "reviewlens-semantic-catalog-v1"
SEMANTIC_PHYSICAL_NAME_POLICY = "resolve_active_release_server_side"

_LOGICAL_NAME = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")
_MODEL_NAME = re.compile(r"^sem_[a-z][a-z0-9_]{2,63}$")
_COLUMN_NAME = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
_ALLOWED_AUDIENCES = frozenset({"DASHBOARD", "TEXT_TO_SQL"})
_ALLOWED_GRANT_ROLES = frozenset({"ANALYST_ROLE", "TEXT_TO_SQL_ROLE"})
_REQUIRED_CONTEXT = frozenset(
    {"data_release_id", "metric_policy_version", "semantic_contract_version"}
)
_FORBIDDEN_COLUMNS = frozenset(
    {
        "customer_id",
        "order_id",
        "review_id",
        "seller_id",
        "source_record_hash",
        "review_comment_title",
        "review_comment_message",
        "raw_payload",
    }
)


class SemanticCatalogError(ValueError):
    """Sanitized catalog failure that never echoes an unsafe identifier."""

    code = "WAREHOUSE_SEMANTIC_CATALOG_INVALID"

    def __init__(self) -> None:
        super().__init__(self.code)


@dataclass(frozen=True, slots=True)
class SemanticViewContract:
    logical_name: str
    dbt_model: str
    audiences: frozenset[str]
    grant_roles: frozenset[str]
    grain: tuple[str, ...]
    dimensions: frozenset[str]
    measures: frozenset[str]
    non_additive_measures: frozenset[str]
    approved_columns: tuple[str, ...]

    def __post_init__(self) -> None:
        approved = frozenset(self.approved_columns)
        if (
            _LOGICAL_NAME.fullmatch(self.logical_name) is None
            or _MODEL_NAME.fullmatch(self.dbt_model) is None
            or not self.audiences
            or not self.audiences <= _ALLOWED_AUDIENCES
            or self.grant_roles != _ALLOWED_GRANT_ROLES
            or not self.grain
            or len(approved) != len(self.approved_columns)
            or any(_COLUMN_NAME.fullmatch(name) is None for name in approved)
            or approved & _FORBIDDEN_COLUMNS
            or not approved >= _REQUIRED_CONTEXT
            or not frozenset(self.grain) <= self.dimensions
            or not self.dimensions <= approved
            or not self.measures <= approved
            or not self.non_additive_measures <= self.measures
            or self.dimensions & self.measures
        ):
            raise SemanticCatalogError()


@dataclass(frozen=True, slots=True)
class SemanticCatalog:
    schema_version: int
    contract_version: str
    physical_name_policy: str
    views: tuple[SemanticViewContract, ...]

    def __post_init__(self) -> None:
        logical_names = tuple(view.logical_name for view in self.views)
        model_names = tuple(view.dbt_model for view in self.views)
        if (
            self.schema_version != 1
            or self.contract_version != SEMANTIC_CATALOG_VERSION
            or self.physical_name_policy != SEMANTIC_PHYSICAL_NAME_POLICY
            or not self.views
            or len(set(logical_names)) != len(logical_names)
            or len(set(model_names)) != len(model_names)
        ):
            raise SemanticCatalogError()


def _string_set(value: object) -> frozenset[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise SemanticCatalogError()
    return frozenset(value)


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise SemanticCatalogError()
    return tuple(value)


def parse_semantic_catalog(payload: Mapping[str, Any]) -> SemanticCatalog:
    """Parse one strict v1 catalog mapping."""

    if set(payload) != {
        "schema_version",
        "contract_version",
        "physical_name_policy",
        "views",
    } or not isinstance(payload["views"], list):
        raise SemanticCatalogError()
    views: list[SemanticViewContract] = []
    expected_view_fields = {
        "logical_name",
        "dbt_model",
        "audiences",
        "grant_roles",
        "grain",
        "dimensions",
        "measures",
        "non_additive_measures",
        "approved_columns",
    }
    for raw_view in payload["views"]:
        if not isinstance(raw_view, dict) or set(raw_view) != expected_view_fields:
            raise SemanticCatalogError()
        logical_name = raw_view["logical_name"]
        dbt_model = raw_view["dbt_model"]
        if not isinstance(logical_name, str) or not isinstance(dbt_model, str):
            raise SemanticCatalogError()
        views.append(
            SemanticViewContract(
                logical_name=logical_name,
                dbt_model=dbt_model,
                audiences=_string_set(raw_view["audiences"]),
                grant_roles=_string_set(raw_view["grant_roles"]),
                grain=_string_tuple(raw_view["grain"]),
                dimensions=_string_set(raw_view["dimensions"]),
                measures=_string_set(raw_view["measures"]),
                non_additive_measures=_string_set(raw_view["non_additive_measures"]),
                approved_columns=_string_tuple(raw_view["approved_columns"]),
            )
        )
    schema_version = payload["schema_version"]
    contract_version = payload["contract_version"]
    physical_name_policy = payload["physical_name_policy"]
    if (
        isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or not isinstance(contract_version, str)
        or not isinstance(physical_name_policy, str)
    ):
        raise SemanticCatalogError()
    return SemanticCatalog(
        schema_version=schema_version,
        contract_version=contract_version,
        physical_name_policy=physical_name_policy,
        views=tuple(views),
    )


def load_semantic_catalog(path: Path) -> SemanticCatalog:
    """Load a committed catalog without accepting scalar or array roots."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SemanticCatalogError() from error
    if not isinstance(payload, dict):
        raise SemanticCatalogError()
    return parse_semantic_catalog(payload)


def resolve_semantic_view(catalog: SemanticCatalog, logical_name: str) -> SemanticViewContract:
    """Resolve an allowlisted logical name, never a physical/candidate identifier."""

    if _LOGICAL_NAME.fullmatch(logical_name) is None:
        raise SemanticCatalogError()
    matches = tuple(view for view in catalog.views if view.logical_name == logical_name)
    if len(matches) != 1:
        raise SemanticCatalogError()
    return matches[0]
