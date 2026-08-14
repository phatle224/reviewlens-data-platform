"""Deterministic unknown-member and late/correction policies for M3."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

UNKNOWN_MEMBER_POLICY_VERSION = "reviewlens-unknown-member-v1"
REVISION_POLICY_VERSION = "reviewlens-dimension-revision-v1"

_HASH = re.compile(r"^[0-9a-f]{64}$")


class WarehouseRevisionError(ValueError):
    """Sanitized revision-policy error."""

    code = "WAREHOUSE_REVISION_INVALID"

    def __init__(self) -> None:
        super().__init__(self.code)


class DimensionEntity(StrEnum):
    CUSTOMER = "CUSTOMER"
    PRODUCT = "PRODUCT"
    SELLER = "SELLER"
    GEOGRAPHY = "GEOGRAPHY"


class RevisionDisposition(StrEnum):
    CURRENT = "CURRENT"
    CORRECTION_SUPERSEDED = "CORRECTION_SUPERSEDED"
    LATE_SUPERSEDED = "LATE_SUPERSEDED"


@dataclass(frozen=True, slots=True)
class UnknownMember:
    entity_type: DimensionEntity
    member_key: str
    display_label: str = "UNKNOWN"
    policy_version: str = UNKNOWN_MEMBER_POLICY_VERSION

    def __post_init__(self) -> None:
        if (
            not isinstance(self.entity_type, DimensionEntity)
            or _HASH.fullmatch(self.member_key) is None
            or self.display_label != "UNKNOWN"
            or self.policy_version != UNKNOWN_MEMBER_POLICY_VERSION
        ):
            raise WarehouseRevisionError()


@dataclass(frozen=True, slots=True)
class DimensionRevision:
    entity_key_hash: str
    effective_at: datetime
    ingested_at: datetime
    source_row_number: int
    record_hash: str

    def __post_init__(self) -> None:
        if (
            _HASH.fullmatch(self.entity_key_hash) is None
            or _HASH.fullmatch(self.record_hash) is None
            or self.effective_at.tzinfo is not None
            or self.ingested_at.tzinfo is None
            or self.ingested_at.utcoffset() != UTC.utcoffset(self.ingested_at)
            or isinstance(self.source_row_number, bool)
            or self.source_row_number < 1
        ):
            raise WarehouseRevisionError()

    @property
    def canonical_key(self) -> tuple[datetime, datetime, int, str]:
        return (
            self.effective_at,
            self.ingested_at,
            self.source_row_number,
            self.record_hash,
        )


@dataclass(frozen=True, slots=True)
class RevisionDecision:
    revision: DimensionRevision
    disposition: RevisionDisposition


@dataclass(frozen=True, slots=True)
class RevisionResolution:
    entity_key_hash: str
    decisions: tuple[RevisionDecision, ...]
    replay_duplicate_count: int
    policy_version: str = REVISION_POLICY_VERSION

    def __post_init__(self) -> None:
        if (
            _HASH.fullmatch(self.entity_key_hash) is None
            or not self.decisions
            or self.decisions[0].disposition is not RevisionDisposition.CURRENT
            or sum(
                decision.disposition is RevisionDisposition.CURRENT for decision in self.decisions
            )
            != 1
            or isinstance(self.replay_duplicate_count, bool)
            or self.replay_duplicate_count < 0
            or self.policy_version != REVISION_POLICY_VERSION
        ):
            raise WarehouseRevisionError()

    @property
    def current(self) -> DimensionRevision:
        return self.decisions[0].revision


def unknown_member(entity_type: DimensionEntity) -> UnknownMember:
    if not isinstance(entity_type, DimensionEntity):
        raise WarehouseRevisionError()
    payload = f"{UNKNOWN_MEMBER_POLICY_VERSION}\x00{entity_type.value}".encode("ascii")
    return UnknownMember(entity_type=entity_type, member_key=hashlib.sha256(payload).hexdigest())


def resolve_dimension_revisions(revisions: Iterable[DimensionRevision]) -> RevisionResolution:
    """Resolve one entity independently of input order and record exact replay count."""

    supplied = tuple(revisions)
    if not supplied or len({item.entity_key_hash for item in supplied}) != 1:
        raise WarehouseRevisionError()
    unique = {item.canonical_key: item for item in supplied}
    ordered = tuple(sorted(unique.values(), key=lambda item: item.canonical_key, reverse=True))
    current = ordered[0]
    decisions = [RevisionDecision(current, RevisionDisposition.CURRENT)]
    for revision in ordered[1:]:
        disposition = (
            RevisionDisposition.LATE_SUPERSEDED
            if revision.effective_at < current.effective_at
            else RevisionDisposition.CORRECTION_SUPERSEDED
        )
        decisions.append(RevisionDecision(revision, disposition))
    return RevisionResolution(
        entity_key_hash=current.entity_key_hash,
        decisions=tuple(decisions),
        replay_duplicate_count=len(supplied) - len(unique),
    )
