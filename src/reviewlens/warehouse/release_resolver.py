"""Server-side, request-scoped resolution of one immutable M3 data release."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from reviewlens.warehouse.candidates import CandidateLayer, PhysicalRelationRef
from reviewlens.warehouse.releases import (
    RELEASE_POINTER_NAME,
    ActiveReleasePointer,
    InMemoryReleaseRegistry,
    ReleaseContractError,
    ReleaseDefinition,
)
from reviewlens.warehouse.semantic import (
    SEMANTIC_CATALOG_VERSION,
    SemanticCatalog,
    SemanticCatalogError,
    SemanticViewContract,
    resolve_semantic_view,
)

_HASH = re.compile(r"^[0-9a-f]{64}$")


class ReleaseResolutionError(ValueError):
    """Sanitized request-resolution failure with no user identifier echo."""

    code = "WAREHOUSE_RELEASE_RESOLUTION_INVALID"

    def __init__(self) -> None:
        super().__init__(self.code)


class ServingAudience(StrEnum):
    """Only application-owned consumers may resolve a semantic relation."""

    DASHBOARD = "DASHBOARD"
    TEXT_TO_SQL = "TEXT_TO_SQL"


@dataclass(frozen=True, slots=True)
class PinnedSemanticRelation:
    """One allowlisted semantic contract and its private Gold physical ref."""

    logical_name: str
    contract: SemanticViewContract
    physical_ref: PhysicalRelationRef

    def __post_init__(self) -> None:
        if (
            self.logical_name != self.contract.logical_name
            or self.physical_ref.database != "REVIEWLENS"
            or self.physical_ref.schema != CandidateLayer.GOLD.value
            or not self.physical_ref.object_name.endswith(f"__{self.contract.dbt_model.upper()}")
        ):
            raise ReleaseResolutionError()


@dataclass(frozen=True, slots=True)
class ReleaseRequestPin:
    """Immutable snapshot used for every physical read in one serving request."""

    release_id: str
    definition_sha256: str
    source_release_id: str
    pointer_version: int
    activation_event_id: str
    semantic_contract_version: str
    audience: ServingAudience
    definition: ReleaseDefinition
    relations: tuple[PinnedSemanticRelation, ...]

    def __post_init__(self) -> None:
        logical_names = tuple(item.logical_name for item in self.relations)
        if (
            _HASH.fullmatch(self.release_id) is None
            or self.definition_sha256 != self.release_id
            or not self.source_release_id.startswith("olist_")
            or _HASH.fullmatch(self.source_release_id.removeprefix("olist_")) is None
            or self.pointer_version < 1
            or _HASH.fullmatch(self.activation_event_id) is None
            or self.semantic_contract_version != SEMANTIC_CATALOG_VERSION
            or not isinstance(self.audience, ServingAudience)
            or not isinstance(self.definition, ReleaseDefinition)
            or self.definition.release_id != self.release_id
            or self.definition.definition_sha256 != self.definition_sha256
            or self.definition.source_release_id != self.source_release_id
            or self.definition.semantic_contract_version != self.semantic_contract_version
            or not self.relations
            or len(set(logical_names)) != len(logical_names)
            or any(self.audience.value not in item.contract.audiences for item in self.relations)
        ):
            raise ReleaseResolutionError()


class ActiveReleaseResolver:
    """Resolve logical semantic names from exactly one active-pointer snapshot.

    The resolver intentionally accepts no schema, candidate namespace, physical
    relation or release identifier from callers. It reads the pointer once, then
    resolves every requested semantic relation from that immutable definition.
    An activation racing after the read may affect a later request, never this
    request's pinned relation set.
    """

    def __init__(self, *, registry: InMemoryReleaseRegistry, catalog: SemanticCatalog) -> None:
        if not isinstance(registry, InMemoryReleaseRegistry) or not isinstance(
            catalog, SemanticCatalog
        ):
            raise ReleaseResolutionError()
        self._registry = registry
        self._catalog = catalog

    def resolve(
        self,
        *,
        audience: ServingAudience,
        logical_names: tuple[str, ...],
    ) -> ReleaseRequestPin:
        """Pin allowlisted semantic relations to one immutable active release."""

        if (
            not isinstance(audience, ServingAudience)
            or type(logical_names) is not tuple
            or not logical_names
            or not all(isinstance(name, str) for name in logical_names)
            or len(set(logical_names)) != len(logical_names)
        ):
            raise ReleaseResolutionError()

        pointer = self._registry.active_pointer
        if pointer is None:
            raise ReleaseResolutionError()
        definition = self._definition_for_pointer(pointer)
        refs = {
            (item.layer, item.logical_name): item.physical_ref for item in definition.object_refs
        }
        relations = tuple(
            self._resolve_relation(
                definition=definition,
                refs=refs,
                audience=audience,
                logical_name=logical_name,
            )
            for logical_name in logical_names
        )
        return ReleaseRequestPin(
            release_id=definition.release_id,
            definition_sha256=definition.definition_sha256,
            source_release_id=definition.source_release_id,
            pointer_version=pointer.pointer_version,
            activation_event_id=pointer.activation_event_id,
            semantic_contract_version=definition.semantic_contract_version,
            audience=audience,
            definition=definition,
            relations=relations,
        )

    def _definition_for_pointer(self, pointer: ActiveReleasePointer) -> ReleaseDefinition:
        if pointer.pointer_name != RELEASE_POINTER_NAME:
            raise ReleaseResolutionError()
        try:
            definition = self._registry.get_definition(pointer.release_id)
        except ReleaseContractError as error:
            raise ReleaseResolutionError() from error
        if (
            definition.release_id != pointer.release_id
            or definition.definition_sha256 != pointer.release_id
            or definition.semantic_contract_version != self._catalog.contract_version
        ):
            raise ReleaseResolutionError()
        return definition

    def _resolve_relation(
        self,
        *,
        definition: ReleaseDefinition,
        refs: dict[tuple[CandidateLayer, str], PhysicalRelationRef],
        audience: ServingAudience,
        logical_name: str,
    ) -> PinnedSemanticRelation:
        try:
            contract = resolve_semantic_view(self._catalog, logical_name)
        except SemanticCatalogError as error:
            raise ReleaseResolutionError() from error
        if audience.value not in contract.audiences:
            raise ReleaseResolutionError()

        release_logical_name = contract.dbt_model.upper()
        physical_ref = refs.get((CandidateLayer.GOLD, release_logical_name))
        expected_object_name = f"C_{definition.gold_candidate_id.upper()}__{release_logical_name}"
        if physical_ref is None or physical_ref.object_name != expected_object_name:
            raise ReleaseResolutionError()
        return PinnedSemanticRelation(
            logical_name=logical_name,
            contract=contract,
            physical_ref=physical_ref,
        )
