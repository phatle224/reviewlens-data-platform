"""Deterministic Gold dimension and fact-partition contracts for M3."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from itertools import pairwise

from reviewlens.warehouse.revisions import DimensionEntity, unknown_member

GOLD_KEY_VERSION = "reviewlens-gold-key-v1"
GOLD_HISTORY_VERSION = "reviewlens-gold-history-v1"
GOLD_FACT_RECONCILIATION_VERSION = "reviewlens-gold-fact-reconciliation-v1"

_HASH = re.compile(r"^[0-9a-f]{64}$")


class GoldContractError(ValueError):
    """Sanitized Gold contract error that never echoes business values."""

    code = "WAREHOUSE_GOLD_INVALID"

    def __init__(self) -> None:
        super().__init__(self.code)


@dataclass(frozen=True, slots=True)
class DimensionHistoryRow:
    natural_key_hash: str
    member_key: str
    effective_from: datetime
    effective_to: datetime | None
    is_current: bool

    def __post_init__(self) -> None:
        if (
            _HASH.fullmatch(self.natural_key_hash) is None
            or _HASH.fullmatch(self.member_key) is None
            or self.effective_from.tzinfo is not None
            or (self.effective_to is not None and self.effective_to.tzinfo is not None)
            or (self.effective_to is not None and self.effective_to <= self.effective_from)
            or self.is_current != (self.effective_to is None)
        ):
            raise GoldContractError()


@dataclass(frozen=True, slots=True)
class FactPartitionResult:
    source_count: int
    fact_count: int
    excluded_count: int
    contract_version: str = GOLD_FACT_RECONCILIATION_VERSION

    def __post_init__(self) -> None:
        if (
            min(self.source_count, self.fact_count, self.excluded_count) < 0
            or self.source_count != self.fact_count + self.excluded_count
            or self.contract_version != GOLD_FACT_RECONCILIATION_VERSION
        ):
            raise GoldContractError()


def gold_dimension_key(
    entity_type: DimensionEntity,
    natural_key: str | None,
    *,
    version_hash: str | None = None,
) -> str:
    """Return the versioned member key or the entity-specific unknown key."""

    if not isinstance(entity_type, DimensionEntity):
        raise GoldContractError()
    if natural_key is None or not natural_key.strip():
        return unknown_member(entity_type).member_key
    if version_hash is not None and _HASH.fullmatch(version_hash) is None:
        raise GoldContractError()
    normalized = natural_key.strip()
    fields: tuple[str, ...] = (GOLD_KEY_VERSION, entity_type.value, normalized)
    if version_hash is not None:
        fields += (version_hash,)
    payload = "\x00".join(fields).encode()
    return hashlib.sha256(payload).hexdigest()


def resolve_dimension_as_of(
    *,
    entity_type: DimensionEntity,
    natural_key_hash: str,
    event_at: datetime,
    history: Iterable[DimensionHistoryRow],
) -> str:
    """Resolve one non-overlapping SCD history at a half-open as-of boundary."""

    if (
        not isinstance(entity_type, DimensionEntity)
        or _HASH.fullmatch(natural_key_hash) is None
        or event_at.tzinfo is not None
    ):
        raise GoldContractError()
    rows = tuple(sorted(history, key=lambda item: (item.effective_from, item.member_key)))
    if any(item.natural_key_hash != natural_key_hash for item in rows):
        raise GoldContractError()
    for left, right in pairwise(rows):
        if left.effective_to is None or left.effective_to > right.effective_from:
            raise GoldContractError()
    matches = tuple(
        item
        for item in rows
        if item.effective_from <= event_at
        and (item.effective_to is None or event_at < item.effective_to)
    )
    if len(matches) > 1:
        raise GoldContractError()
    return matches[0].member_key if matches else unknown_member(entity_type).member_key


def reconcile_fact_partition(
    *,
    source_grain_hashes: Iterable[str],
    fact_grain_hashes: Iterable[str],
    excluded_grain_hashes: Iterable[str],
) -> FactPartitionResult:
    """Require fact and explained exclusions to partition every unique source grain."""

    source = tuple(source_grain_hashes)
    facts = tuple(fact_grain_hashes)
    excluded = tuple(excluded_grain_hashes)
    if (
        any(_HASH.fullmatch(value) is None for value in (*source, *facts, *excluded))
        or len(set(source)) != len(source)
        or len(set(facts)) != len(facts)
        or len(set(excluded)) != len(excluded)
        or set(facts) & set(excluded)
        or set(source) != set(facts) | set(excluded)
    ):
        raise GoldContractError()
    return FactPartitionResult(len(source), len(facts), len(excluded))
