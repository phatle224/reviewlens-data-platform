"""Immutable M3 release definitions, append-only events and CAS activation."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from threading import Lock

from reviewlens.warehouse.candidates import (
    CandidateLayer,
    CandidateState,
    InMemoryCandidateRegistry,
    PhysicalRelationRef,
    WarehouseCandidateError,
)
from reviewlens.warehouse.gold_candidate import (
    GOLD_CANDIDATE_OUTPUT_LOGICAL_NAMES,
    GoldCandidateBuildTarget,
)
from reviewlens.warehouse.semantic import SEMANTIC_CATALOG_VERSION

RELEASE_DEFINITION_VERSION = "reviewlens-release-definition-v1"
RELEASE_POINTER_NAME = "ACTIVE_DATA_RELEASE"

_HASH = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Z][A-Z0-9_]{0,254}$")
_OWNER = re.compile(r"^[a-z][a-z0-9_.-]{1,63}$")
_REASON = re.compile(r"^[A-Z][A-Z0-9_]{2,127}$")
_VERSION = re.compile(r"^[a-z][a-z0-9_.-]{1,127}$")


class ReleaseContractError(ValueError):
    """Sanitized error for malformed, unsafe or stale release actions."""

    code = "WAREHOUSE_RELEASE_INVALID"

    def __init__(self) -> None:
        super().__init__(self.code)


class ReleaseEventType(StrEnum):
    CREATED = "CREATED"
    ACTIVATED = "ACTIVATED"
    ROLLED_BACK = "ROLLED_BACK"
    INVALIDATED = "INVALIDATED"
    REVOKED = "REVOKED"


@dataclass(frozen=True, slots=True, order=True)
class ReleaseObjectRef:
    """One immutable candidate physical relation owned by a release definition."""

    layer: CandidateLayer
    logical_name: str
    physical_ref: PhysicalRelationRef

    def __post_init__(self) -> None:
        if (
            not isinstance(self.layer, CandidateLayer)
            or _IDENTIFIER.fullmatch(self.logical_name) is None
            or self.physical_ref.schema != self.layer.value
            or not self.physical_ref.object_name.endswith(f"__{self.logical_name}")
        ):
            raise ReleaseContractError()

    @property
    def canonical_key(self) -> tuple[str, str, str, str, str]:
        return (
            self.layer.value,
            self.logical_name,
            self.physical_ref.database,
            self.physical_ref.schema,
            self.physical_ref.object_name,
        )


@dataclass(frozen=True, slots=True)
class ReleaseDefinition:
    """Frozen serving candidate identity; it contains no mutable pointer state."""

    release_id: str
    definition_sha256: str
    source_release_id: str
    ingestion_batch_id: str
    silver_processing_run_id: str
    gold_processing_run_id: str
    silver_candidate_id: str
    gold_candidate_id: str
    semantic_contract_version: str
    object_refs: tuple[ReleaseObjectRef, ...]
    definition_version: str = RELEASE_DEFINITION_VERSION

    def __post_init__(self) -> None:
        expected_silver = {
            item.logical_name for item in self.object_refs if item.layer is CandidateLayer.SILVER
        }
        expected_gold = {
            item.logical_name for item in self.object_refs if item.layer is CandidateLayer.GOLD
        }
        if (
            any(
                _HASH.fullmatch(value) is None
                for value in (
                    self.release_id,
                    self.definition_sha256,
                    self.silver_processing_run_id,
                    self.gold_processing_run_id,
                    self.silver_candidate_id,
                    self.gold_candidate_id,
                )
            )
            or self.release_id != self.definition_sha256
            or not self.source_release_id.startswith("olist_")
            or _HASH.fullmatch(self.source_release_id.removeprefix("olist_")) is None
            or not self.ingestion_batch_id.startswith("batch_")
            or _HASH.fullmatch(self.ingestion_batch_id.removeprefix("batch_")) is None
            or self.silver_candidate_id == self.gold_candidate_id
            or self.semantic_contract_version != SEMANTIC_CATALOG_VERSION
            or self.definition_version != RELEASE_DEFINITION_VERSION
            or not self.object_refs
            or len(self.object_refs)
            != len(_SILVER_RELEASE_LOGICAL_NAMES) + len(GOLD_CANDIDATE_OUTPUT_LOGICAL_NAMES)
            or tuple(sorted(self.object_refs)) != self.object_refs
            or len({item.canonical_key for item in self.object_refs}) != len(self.object_refs)
            or len({(item.layer, item.logical_name) for item in self.object_refs})
            != len(self.object_refs)
            or any(
                not _is_candidate_owned_object_ref(
                    item,
                    silver_candidate_id=self.silver_candidate_id,
                    gold_candidate_id=self.gold_candidate_id,
                )
                for item in self.object_refs
            )
            or expected_silver != _SILVER_RELEASE_LOGICAL_NAMES
            or expected_gold != set(GOLD_CANDIDATE_OUTPUT_LOGICAL_NAMES)
        ):
            raise ReleaseContractError()


@dataclass(frozen=True, slots=True)
class ReleaseEvent:
    """One append-only transition. Event IDs exclude runtime timestamps for replay."""

    event_id: str
    event_type: ReleaseEventType
    release_id: str
    previous_release_id: str | None
    expected_pointer_version: int
    result_pointer_version: int
    actor_service: str
    reason_code: str
    event_at: datetime

    def __post_init__(self) -> None:
        if (
            _HASH.fullmatch(self.event_id) is None
            or not isinstance(self.event_type, ReleaseEventType)
            or _HASH.fullmatch(self.release_id) is None
            or (
                self.previous_release_id is not None
                and _HASH.fullmatch(self.previous_release_id) is None
            )
            or self.expected_pointer_version < 0
            or self.result_pointer_version < 0
            or (
                self.event_type is ReleaseEventType.CREATED
                and (self.expected_pointer_version != 0 or self.result_pointer_version != 0)
            )
            or (
                self.event_type in {ReleaseEventType.ACTIVATED, ReleaseEventType.ROLLED_BACK}
                and self.result_pointer_version != self.expected_pointer_version + 1
            )
            or (
                self.event_type in {ReleaseEventType.INVALIDATED, ReleaseEventType.REVOKED}
                and self.result_pointer_version != self.expected_pointer_version
            )
            or _OWNER.fullmatch(self.actor_service) is None
            or _REASON.fullmatch(self.reason_code) is None
            or self.event_at.tzinfo is None
            or self.event_at.utcoffset() != UTC.utcoffset(self.event_at)
        ):
            raise ReleaseContractError()


@dataclass(frozen=True, slots=True)
class ActiveReleasePointer:
    """The only mutable release record, changed by versioned compare-and-set."""

    release_id: str
    activation_event_id: str
    pointer_version: int
    activated_at: datetime
    pointer_name: str = RELEASE_POINTER_NAME

    def __post_init__(self) -> None:
        if (
            self.pointer_name != RELEASE_POINTER_NAME
            or _HASH.fullmatch(self.release_id) is None
            or _HASH.fullmatch(self.activation_event_id) is None
            or self.pointer_version < 1
            or self.activated_at.tzinfo is None
            or self.activated_at.utcoffset() != UTC.utcoffset(self.activated_at)
        ):
            raise ReleaseContractError()


@dataclass(frozen=True, slots=True)
class ReleaseTransition:
    """Outcome of an activation/rollback CAS request."""

    event: ReleaseEvent
    pointer: ActiveReleasePointer
    replayed: bool


_SILVER_RELEASE_LOGICAL_NAMES = {
    "SIL_CATEGORY_TRANSLATION",
    "SIL_CUSTOMER",
    "SIL_GEOLOCATION_ZIP",
    "SIL_ORDER",
    "SIL_ORDER_ITEM",
    "SIL_ORDER_PAYMENT",
    "SIL_ORDER_REVIEW",
    "SIL_PRODUCT",
    "SIL_SELLER",
    "SIL_UNKNOWN_MEMBER_REGISTRY",
}


def _is_candidate_owned_object_ref(
    item: ReleaseObjectRef,
    *,
    silver_candidate_id: str,
    gold_candidate_id: str,
) -> bool:
    candidate_id = silver_candidate_id if item.layer is CandidateLayer.SILVER else gold_candidate_id
    return (
        item.physical_ref.database == "REVIEWLENS"
        and item.physical_ref.object_name == f"C_{candidate_id.upper()}__{item.logical_name}"
    )


def build_release_definition(
    candidates: InMemoryCandidateRegistry,
    *,
    target: GoldCandidateBuildTarget,
) -> ReleaseDefinition:
    """Freeze only a pair of tested Silver/Gold candidates into one release."""

    if not isinstance(candidates, InMemoryCandidateRegistry) or not isinstance(
        target, GoldCandidateBuildTarget
    ):
        raise ReleaseContractError()
    try:
        silver_record = candidates.get(target.silver_candidate.candidate_id)
        gold_record = candidates.get(target.gold_candidate.candidate_id)
    except WarehouseCandidateError as error:
        raise ReleaseContractError() from error
    if (
        silver_record.state is not CandidateState.TEST_PASSED
        or gold_record.state is not CandidateState.TEST_PASSED
    ):
        raise ReleaseContractError()

    silver_refs = tuple(
        ReleaseObjectRef(
            layer=CandidateLayer.SILVER,
            logical_name=item.input.logical_name,
            physical_ref=item.input.physical_ref,
        )
        for item in target.gold_run.inputs
    )
    gold_refs = tuple(
        ReleaseObjectRef(
            layer=CandidateLayer.GOLD,
            logical_name=logical_name,
            physical_ref=target.gold_candidate.relation(logical_name),
        )
        for logical_name in GOLD_CANDIDATE_OUTPUT_LOGICAL_NAMES
    )
    object_refs = tuple(sorted((*silver_refs, *gold_refs)))
    identity = {
        "definition_version": RELEASE_DEFINITION_VERSION,
        "gold_candidate_id": target.gold_candidate.candidate_id,
        "gold_processing_run_id": target.gold_run.processing_run_id,
        "ingestion_batch_id": target.gold_run.ingestion_batch_id,
        "object_refs": [item.canonical_key for item in object_refs],
        "semantic_contract_version": SEMANTIC_CATALOG_VERSION,
        "silver_candidate_id": target.silver_candidate.candidate_id,
        "silver_processing_run_id": target.silver_run.processing_run_id,
        "source_release_id": target.gold_run.source_release_id,
    }
    release_id = _digest("release_definition", identity)
    return ReleaseDefinition(
        release_id=release_id,
        definition_sha256=release_id,
        source_release_id=target.gold_run.source_release_id,
        ingestion_batch_id=target.gold_run.ingestion_batch_id,
        silver_processing_run_id=target.silver_run.processing_run_id,
        gold_processing_run_id=target.gold_run.processing_run_id,
        silver_candidate_id=target.silver_candidate.candidate_id,
        gold_candidate_id=target.gold_candidate.candidate_id,
        semantic_contract_version=SEMANTIC_CATALOG_VERSION,
        object_refs=object_refs,
    )


class InMemoryReleaseRegistry:
    """Thread-safe fake of immutable definitions, events and a CAS pointer."""

    def __init__(self) -> None:
        self._definitions: dict[str, ReleaseDefinition] = {}
        self._events: list[ReleaseEvent] = []
        self._pointer: ActiveReleasePointer | None = None
        self._terminal: dict[str, ReleaseEventType] = {}
        self._lock = Lock()

    @property
    def active_pointer(self) -> ActiveReleasePointer | None:
        with self._lock:
            return self._pointer

    @property
    def events(self) -> tuple[ReleaseEvent, ...]:
        with self._lock:
            return tuple(self._events)

    def register_definition(
        self,
        definition: ReleaseDefinition,
        *,
        actor_service: str,
        now: datetime,
    ) -> ReleaseDefinition:
        _require_actor(actor_service)
        _require_utc(now)
        if not isinstance(definition, ReleaseDefinition):
            raise ReleaseContractError()
        with self._lock:
            existing = self._definitions.get(definition.release_id)
            if existing is not None:
                if existing != definition:
                    raise ReleaseContractError()
                return existing
            self._definitions[definition.release_id] = definition
            self._events.append(
                _event(
                    event_type=ReleaseEventType.CREATED,
                    release_id=definition.release_id,
                    previous_release_id=None,
                    expected_pointer_version=0,
                    result_pointer_version=0,
                    actor_service=actor_service,
                    reason_code="CANDIDATE_TEST_PASSED",
                    event_at=now,
                )
            )
            return definition

    def activate(
        self,
        release_id: str,
        *,
        expected_pointer_version: int,
        actor_service: str,
        now: datetime,
    ) -> ReleaseTransition:
        return self._move_pointer(
            event_type=ReleaseEventType.ACTIVATED,
            release_id=release_id,
            expected_pointer_version=expected_pointer_version,
            actor_service=actor_service,
            reason_code="ACTIVATION_REQUESTED",
            now=now,
        )

    def rollback(
        self,
        release_id: str,
        *,
        expected_pointer_version: int,
        actor_service: str,
        now: datetime,
    ) -> ReleaseTransition:
        return self._move_pointer(
            event_type=ReleaseEventType.ROLLED_BACK,
            release_id=release_id,
            expected_pointer_version=expected_pointer_version,
            actor_service=actor_service,
            reason_code="ROLLBACK_REQUESTED",
            now=now,
        )

    def invalidate(
        self,
        release_id: str,
        *,
        actor_service: str,
        now: datetime,
        reason_code: str = "VALIDATION_FAILED",
    ) -> ReleaseEvent:
        return self._mark_terminal(
            ReleaseEventType.INVALIDATED,
            release_id,
            actor_service=actor_service,
            now=now,
            reason_code=reason_code,
        )

    def revoke(
        self,
        release_id: str,
        *,
        actor_service: str,
        now: datetime,
        reason_code: str = "RELEASE_REVOKED",
    ) -> ReleaseEvent:
        return self._mark_terminal(
            ReleaseEventType.REVOKED,
            release_id,
            actor_service=actor_service,
            now=now,
            reason_code=reason_code,
        )

    def get_definition(self, release_id: str) -> ReleaseDefinition:
        _require_release_id(release_id)
        with self._lock:
            try:
                return self._definitions[release_id]
            except KeyError:
                raise ReleaseContractError() from None

    def _move_pointer(
        self,
        *,
        event_type: ReleaseEventType,
        release_id: str,
        expected_pointer_version: int,
        actor_service: str,
        reason_code: str,
        now: datetime,
    ) -> ReleaseTransition:
        _require_release_id(release_id)
        _require_pointer_version(expected_pointer_version)
        _require_actor(actor_service)
        _require_reason(reason_code)
        _require_utc(now)
        with self._lock:
            self._require_eligible(release_id)
            current = self._pointer
            current_version = 0 if current is None else current.pointer_version
            if (
                current is not None
                and current.release_id == release_id
                and current.pointer_version == expected_pointer_version + 1
            ):
                replay = self._find_transition(event_type, release_id, current.pointer_version)
                if replay is not None:
                    return ReleaseTransition(event=replay, pointer=current, replayed=True)
            if current_version != expected_pointer_version:
                raise ReleaseContractError()
            if event_type is ReleaseEventType.ROLLED_BACK and (
                current is None
                or current.release_id == release_id
                or not self._was_active(release_id)
            ):
                raise ReleaseContractError()
            previous_release_id = None if current is None else current.release_id
            event = _event(
                event_type=event_type,
                release_id=release_id,
                previous_release_id=previous_release_id,
                expected_pointer_version=expected_pointer_version,
                result_pointer_version=expected_pointer_version + 1,
                actor_service=actor_service,
                reason_code=reason_code,
                event_at=now,
            )
            pointer = ActiveReleasePointer(
                release_id=release_id,
                activation_event_id=event.event_id,
                pointer_version=event.result_pointer_version,
                activated_at=now,
            )
            self._events.append(event)
            self._pointer = pointer
            return ReleaseTransition(event=event, pointer=pointer, replayed=False)

    def _mark_terminal(
        self,
        event_type: ReleaseEventType,
        release_id: str,
        *,
        actor_service: str,
        now: datetime,
        reason_code: str,
    ) -> ReleaseEvent:
        _require_release_id(release_id)
        _require_actor(actor_service)
        _require_utc(now)
        _require_reason(reason_code)
        with self._lock:
            if release_id not in self._definitions or (
                self._pointer is not None and self._pointer.release_id == release_id
            ):
                raise ReleaseContractError()
            prior = self._terminal.get(release_id)
            if prior is not None:
                if prior is event_type:
                    return next(
                        event
                        for event in reversed(self._events)
                        if event.event_type is event_type and event.release_id == release_id
                    )
                raise ReleaseContractError()
            current = self._pointer
            pointer_version = 0 if current is None else current.pointer_version
            event = _event(
                event_type=event_type,
                release_id=release_id,
                previous_release_id=None if current is None else current.release_id,
                expected_pointer_version=pointer_version,
                result_pointer_version=pointer_version,
                actor_service=actor_service,
                reason_code=reason_code,
                event_at=now,
            )
            self._events.append(event)
            self._terminal[release_id] = event_type
            return event

    def _require_eligible(self, release_id: str) -> None:
        if release_id not in self._definitions or release_id in self._terminal:
            raise ReleaseContractError()

    def _was_active(self, release_id: str) -> bool:
        return any(
            event.release_id == release_id
            and event.event_type in {ReleaseEventType.ACTIVATED, ReleaseEventType.ROLLED_BACK}
            for event in self._events
        )

    def _find_transition(
        self,
        event_type: ReleaseEventType,
        release_id: str,
        result_pointer_version: int,
    ) -> ReleaseEvent | None:
        for event in reversed(self._events):
            if (
                event.event_type is event_type
                and event.release_id == release_id
                and event.result_pointer_version == result_pointer_version
            ):
                return event
        return None


def _event(
    *,
    event_type: ReleaseEventType,
    release_id: str,
    previous_release_id: str | None,
    expected_pointer_version: int,
    result_pointer_version: int,
    actor_service: str,
    reason_code: str,
    event_at: datetime,
) -> ReleaseEvent:
    event_id = _digest(
        "release_event",
        {
            "actor_service": actor_service,
            "event_type": event_type.value,
            "expected_pointer_version": expected_pointer_version,
            "previous_release_id": previous_release_id,
            "reason_code": reason_code,
            "release_id": release_id,
            "result_pointer_version": result_pointer_version,
        },
    )
    return ReleaseEvent(
        event_id=event_id,
        event_type=event_type,
        release_id=release_id,
        previous_release_id=previous_release_id,
        expected_pointer_version=expected_pointer_version,
        result_pointer_version=result_pointer_version,
        actor_service=actor_service,
        reason_code=reason_code,
        event_at=event_at,
    )


def _digest(kind: str, fields: object) -> str:
    payload = json.dumps(
        {"fields": fields, "kind": kind, "version": RELEASE_DEFINITION_VERSION},
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def _require_release_id(value: str) -> None:
    if _HASH.fullmatch(value) is None:
        raise ReleaseContractError()


def _require_pointer_version(value: int) -> None:
    if type(value) is not int or value < 0:
        raise ReleaseContractError()


def _require_actor(value: str) -> None:
    if _OWNER.fullmatch(value) is None:
        raise ReleaseContractError()


def _require_reason(value: str) -> None:
    if _REASON.fullmatch(value) is None:
        raise ReleaseContractError()


def _require_utc(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ReleaseContractError()
