"""Deterministic M3 processing lineage and isolated candidate state machine."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from threading import Lock

PROCESSING_ID_VERSION = "reviewlens-processing-id-v1"
CANDIDATE_STRATEGY_VERSION = "reviewlens-silver-candidate-v1"

_HASH = re.compile(r"^[0-9a-f]{64}$")
_VERSION = re.compile(r"^[a-z][a-z0-9_.-]{1,127}$")
_IDENTIFIER = re.compile(r"^[A-Z][A-Z0-9_]{0,254}$")
_SOURCE_RELEASE = re.compile(r"^olist_[0-9a-f]{64}$")
_INGESTION_BATCH = re.compile(r"^batch_[0-9a-f]{64}$")
_OWNER = re.compile(r"^[a-z][a-z0-9_.-]{1,63}$")
_SENSITIVE = re.compile(r"(?:SECRET|TOKEN|PASSWORD|PRIVATE_KEY|API_KEY)", re.IGNORECASE)


class WarehouseCandidateError(ValueError):
    """Sanitized candidate error that never echoes identifiers or inputs."""

    code = "WAREHOUSE_CANDIDATE_INVALID"

    def __init__(self) -> None:
        super().__init__(self.code)


class ProcessingInputKind(StrEnum):
    BRONZE_RELATION = "BRONZE_RELATION"
    CANDIDATE_RELATION = "CANDIDATE_RELATION"


class CandidateLayer(StrEnum):
    SILVER = "SILVER"
    GOLD = "GOLD"


class CandidateState(StrEnum):
    PLANNED = "PLANNED"
    BUILDING = "BUILDING"
    TEST_PASSED = "TEST_PASSED"
    FAILED = "FAILED"
    CLEANED = "CLEANED"


@dataclass(frozen=True, slots=True, order=True)
class PhysicalRelationRef:
    database: str
    schema: str
    object_name: str

    def __post_init__(self) -> None:
        if any(
            _IDENTIFIER.fullmatch(value) is None or _SENSITIVE.search(value) is not None
            for value in (self.database, self.schema, self.object_name)
        ):
            raise WarehouseCandidateError()

    @property
    def qualified_name(self) -> str:
        return f"{self.database}.{self.schema}.{self.object_name}"


@dataclass(frozen=True, slots=True)
class ProcessingInput:
    kind: ProcessingInputKind
    logical_name: str
    physical_ref: PhysicalRelationRef
    version_id: str
    content_sha256: str | None = None

    def __post_init__(self) -> None:
        if (
            _IDENTIFIER.fullmatch(self.logical_name) is None
            or _SENSITIVE.search(self.logical_name) is not None
            or _VERSION.fullmatch(self.version_id) is None
            or _SENSITIVE.search(self.version_id) is not None
            or (self.content_sha256 is not None and _HASH.fullmatch(self.content_sha256) is None)
        ):
            raise WarehouseCandidateError()

    @property
    def canonical_key(self) -> tuple[str, str, str, str, str]:
        return (
            self.kind.value,
            self.logical_name,
            self.physical_ref.qualified_name,
            self.version_id,
            self.content_sha256 or "",
        )


@dataclass(frozen=True, slots=True)
class ProcessingInputRef:
    input_ref_id: str
    input_ordinal: int
    input: ProcessingInput

    def __post_init__(self) -> None:
        if _HASH.fullmatch(self.input_ref_id) is None or self.input_ordinal < 1:
            raise WarehouseCandidateError()


@dataclass(frozen=True, slots=True)
class ProcessingRunDefinition:
    processing_run_id: str
    contract_version: str
    phase: CandidateLayer
    source_release_id: str
    ingestion_batch_id: str
    inputs: tuple[ProcessingInputRef, ...]

    def __post_init__(self) -> None:
        if (
            _HASH.fullmatch(self.processing_run_id) is None
            or _VERSION.fullmatch(self.contract_version) is None
            or not isinstance(self.phase, CandidateLayer)
            or _SOURCE_RELEASE.fullmatch(self.source_release_id) is None
            or _INGESTION_BATCH.fullmatch(self.ingestion_batch_id) is None
            or not self.inputs
            or tuple(item.input_ordinal for item in self.inputs)
            != tuple(range(1, len(self.inputs) + 1))
            or len({item.input_ref_id for item in self.inputs}) != len(self.inputs)
        ):
            raise WarehouseCandidateError()


@dataclass(frozen=True, slots=True)
class CandidateDefinition:
    candidate_id: str
    processing_run_id: str
    layer: CandidateLayer
    strategy_version: str
    physical_namespace: str

    def __post_init__(self) -> None:
        if (
            _HASH.fullmatch(self.candidate_id) is None
            or _HASH.fullmatch(self.processing_run_id) is None
            or not isinstance(self.layer, CandidateLayer)
            or _VERSION.fullmatch(self.strategy_version) is None
            or self.physical_namespace != f"C_{self.candidate_id.upper()}"
        ):
            raise WarehouseCandidateError()

    def relation(self, logical_name: str) -> PhysicalRelationRef:
        if _IDENTIFIER.fullmatch(logical_name) is None:
            raise WarehouseCandidateError()
        return PhysicalRelationRef(
            database="REVIEWLENS",
            schema=self.layer.value,
            object_name=f"{self.physical_namespace}__{logical_name}",
        )


@dataclass(frozen=True, slots=True)
class CandidateLease:
    candidate_id: str
    owner_id: str
    expires_at: datetime

    def __post_init__(self) -> None:
        _require_candidate_id(self.candidate_id)
        _require_owner(self.owner_id)
        _require_utc(self.expires_at)


@dataclass(frozen=True, slots=True)
class CandidateRecord:
    definition: CandidateDefinition
    state: CandidateState
    lease: CandidateLease | None = None


def build_processing_run(
    *,
    contract_version: str,
    phase: CandidateLayer,
    source_release_id: str,
    ingestion_batch_id: str,
    inputs: Iterable[ProcessingInput],
) -> ProcessingRunDefinition:
    if (
        not isinstance(phase, CandidateLayer)
        or _VERSION.fullmatch(contract_version) is None
        or _SOURCE_RELEASE.fullmatch(source_release_id) is None
        or _INGESTION_BATCH.fullmatch(ingestion_batch_id) is None
    ):
        raise WarehouseCandidateError()
    ordered = tuple(sorted(inputs, key=lambda item: item.canonical_key))
    if not ordered or len({item.canonical_key for item in ordered}) != len(ordered):
        raise WarehouseCandidateError()
    processing_run_id = _digest(
        "processing_run",
        {
            "contract_version": contract_version,
            "ingestion_batch_id": ingestion_batch_id,
            "inputs": [item.canonical_key for item in ordered],
            "phase": phase.value,
            "source_release_id": source_release_id,
        },
    )
    refs = tuple(
        ProcessingInputRef(
            input_ref_id=_digest(
                "processing_input",
                {
                    "input": item.canonical_key,
                    "input_ordinal": ordinal,
                    "processing_run_id": processing_run_id,
                },
            ),
            input_ordinal=ordinal,
            input=item,
        )
        for ordinal, item in enumerate(ordered, start=1)
    )
    return ProcessingRunDefinition(
        processing_run_id=processing_run_id,
        contract_version=contract_version,
        phase=phase,
        source_release_id=source_release_id,
        ingestion_batch_id=ingestion_batch_id,
        inputs=refs,
    )


def build_candidate_definition(
    processing_run: ProcessingRunDefinition,
    *,
    strategy_version: str = CANDIDATE_STRATEGY_VERSION,
) -> CandidateDefinition:
    if _VERSION.fullmatch(strategy_version) is None:
        raise WarehouseCandidateError()
    candidate_id = _digest(
        "candidate",
        {
            "layer": processing_run.phase.value,
            "processing_run_id": processing_run.processing_run_id,
            "strategy_version": strategy_version,
        },
    )
    return CandidateDefinition(
        candidate_id=candidate_id,
        processing_run_id=processing_run.processing_run_id,
        layer=processing_run.phase,
        strategy_version=strategy_version,
        physical_namespace=f"C_{candidate_id.upper()}",
    )


class InMemoryCandidateRegistry:
    """Thread-safe append/replay fake for lineage and candidate lifecycle tests."""

    def __init__(self) -> None:
        self._runs: dict[str, ProcessingRunDefinition] = {}
        self._candidates: dict[str, CandidateRecord] = {}
        self._lock = Lock()

    def append_run(self, run: ProcessingRunDefinition) -> None:
        with self._lock:
            existing = self._runs.get(run.processing_run_id)
            if existing is not None and existing != run:
                raise WarehouseCandidateError()
            self._runs[run.processing_run_id] = run

    def runs_for_input(self, version_id: str) -> tuple[ProcessingRunDefinition, ...]:
        if _VERSION.fullmatch(version_id) is None:
            raise WarehouseCandidateError()
        with self._lock:
            return tuple(
                sorted(
                    (
                        run
                        for run in self._runs.values()
                        if any(ref.input.version_id == version_id for ref in run.inputs)
                    ),
                    key=lambda run: run.processing_run_id,
                )
            )

    def register_candidate(self, definition: CandidateDefinition) -> CandidateRecord:
        with self._lock:
            existing = self._candidates.get(definition.candidate_id)
            if existing is not None:
                if existing.definition != definition:
                    raise WarehouseCandidateError()
                return existing
            if definition.processing_run_id not in self._runs:
                raise WarehouseCandidateError()
            record = CandidateRecord(definition=definition, state=CandidateState.PLANNED)
            self._candidates[definition.candidate_id] = record
            return record

    def claim(
        self,
        candidate_id: str,
        *,
        owner_id: str,
        now: datetime,
        expires_at: datetime,
    ) -> CandidateLease:
        _require_candidate_id(candidate_id)
        _require_owner(owner_id)
        _require_utc(now)
        _require_utc(expires_at)
        if expires_at <= now:
            raise WarehouseCandidateError()
        with self._lock:
            record = self._candidate(candidate_id)
            lease = record.lease
            if record.state not in {CandidateState.PLANNED, CandidateState.BUILDING}:
                raise WarehouseCandidateError()
            if lease is not None and lease.expires_at > now and lease.owner_id != owner_id:
                raise WarehouseCandidateError()
            next_lease = CandidateLease(candidate_id, owner_id, expires_at)
            self._candidates[candidate_id] = replace(
                record,
                state=CandidateState.BUILDING,
                lease=next_lease,
            )
            return next_lease

    def finish(self, lease: CandidateLease, *, success: bool, now: datetime) -> CandidateRecord:
        _require_utc(now)
        with self._lock:
            record = self._candidate(lease.candidate_id)
            if record.state is not CandidateState.BUILDING or record.lease != lease:
                raise WarehouseCandidateError()
            if lease.expires_at <= now:
                raise WarehouseCandidateError()
            completed = replace(
                record,
                state=CandidateState.TEST_PASSED if success else CandidateState.FAILED,
                lease=None,
            )
            self._candidates[lease.candidate_id] = completed
            return completed

    def cleanup(
        self,
        candidate_id: str,
        *,
        active_candidate_ids: Iterable[str] = (),
    ) -> CandidateRecord:
        _require_candidate_id(candidate_id)
        active = set(active_candidate_ids)
        if any(_HASH.fullmatch(value) is None for value in active):
            raise WarehouseCandidateError()
        with self._lock:
            record = self._candidate(candidate_id)
            if record.state is not CandidateState.FAILED or candidate_id in active:
                raise WarehouseCandidateError()
            cleaned = replace(record, state=CandidateState.CLEANED)
            self._candidates[candidate_id] = cleaned
            return cleaned

    def get(self, candidate_id: str) -> CandidateRecord:
        _require_candidate_id(candidate_id)
        with self._lock:
            return self._candidate(candidate_id)

    def _candidate(self, candidate_id: str) -> CandidateRecord:
        try:
            return self._candidates[candidate_id]
        except KeyError:
            raise WarehouseCandidateError() from None


def _digest(kind: str, fields: object) -> str:
    payload = json.dumps(
        {"fields": fields, "kind": kind, "version": PROCESSING_ID_VERSION},
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def _require_candidate_id(value: str) -> None:
    if _HASH.fullmatch(value) is None:
        raise WarehouseCandidateError()


def _require_owner(value: str) -> None:
    if _OWNER.fullmatch(value) is None:
        raise WarehouseCandidateError()


def _require_utc(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise WarehouseCandidateError()
