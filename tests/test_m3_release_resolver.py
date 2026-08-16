from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier
from typing import cast

import pytest

from reviewlens.warehouse.candidates import (
    CandidateLayer,
    CandidateState,
    InMemoryCandidateRegistry,
    PhysicalRelationRef,
    ProcessingInput,
    ProcessingInputKind,
    ProcessingRunDefinition,
    build_candidate_definition,
    build_processing_run,
)
from reviewlens.warehouse.gold_candidate import (
    GOLD_CANDIDATE_MODEL_NAMES,
    GoldCandidateBuildEvidence,
    GoldCandidateBuildTarget,
    finish_gold_candidate_target,
    plan_gold_candidate_target,
)
from reviewlens.warehouse.release_resolver import (
    ActiveReleaseResolver,
    ReleaseRequestPin,
    ReleaseResolutionError,
    ServingAudience,
)
from reviewlens.warehouse.releases import (
    InMemoryReleaseRegistry,
    ReleaseContractError,
    ReleaseDefinition,
    ReleaseTransition,
    build_release_definition,
)
from reviewlens.warehouse.semantic import load_semantic_catalog

SOURCE_RELEASE_ID = f"olist_{'a' * 64}"
BATCH_ID = f"batch_{'b' * 64}"
NOW = datetime(2026, 8, 16, 5, 0, tzinfo=UTC)
CATALOG_PATH = Path("config/semantic_catalog.v1.json")
SEMANTIC_LOGICAL_NAMES = (
    "ORDER_DELIVERY",
    "PRODUCT_REVIEW",
    "SELLER_PERFORMANCE",
    "CUSTOMER_OVERVIEW",
)


def _silver_run(contract_version: str) -> ProcessingRunDefinition:
    return build_processing_run(
        contract_version=contract_version,
        phase=CandidateLayer.SILVER,
        source_release_id=SOURCE_RELEASE_ID,
        ingestion_batch_id=BATCH_ID,
        inputs=(
            ProcessingInput(
                kind=ProcessingInputKind.BRONZE_RELATION,
                logical_name="CUSTOMERS",
                physical_ref=PhysicalRelationRef("REVIEWLENS", "BRONZE", "BRZ_OLIST_CUSTOMERS_RAW"),
                version_id=f"dsrun_{'c' * 64}",
                content_sha256="d" * 64,
            ),
            ProcessingInput(
                kind=ProcessingInputKind.BRONZE_RELATION,
                logical_name="ORDERS",
                physical_ref=PhysicalRelationRef("REVIEWLENS", "BRONZE", "BRZ_OLIST_ORDERS_RAW"),
                version_id=f"dsrun_{'e' * 64}",
                content_sha256="f" * 64,
            ),
        ),
    )


def _tested_target(
    candidates: InMemoryCandidateRegistry, contract_version: str
) -> GoldCandidateBuildTarget:
    silver_run = _silver_run(contract_version)
    silver_candidate = build_candidate_definition(silver_run)
    candidates.append_run(silver_run)
    candidates.register_candidate(silver_candidate)
    silver_lease = candidates.claim(
        silver_candidate.candidate_id,
        owner_id="silver-builder",
        now=NOW,
        expires_at=NOW + timedelta(minutes=10),
    )
    assert (
        candidates.finish_test_gate(silver_lease, passed=True, now=NOW + timedelta(minutes=1)).state
        is CandidateState.TEST_PASSED
    )
    target = plan_gold_candidate_target(silver_run=silver_run, silver_candidate=silver_candidate)
    candidates.append_run(target.gold_run)
    candidates.register_candidate(target.gold_candidate)
    gold_lease = candidates.claim(
        target.gold_candidate.candidate_id,
        owner_id="gold-builder",
        now=NOW,
        expires_at=NOW + timedelta(minutes=10),
    )
    finish_gold_candidate_target(
        candidates,
        target=target,
        lease=gold_lease,
        evidence=GoldCandidateBuildEvidence(
            candidate_id=target.gold_candidate.candidate_id,
            selected_model_names=GOLD_CANDIDATE_MODEL_NAMES,
            dbt_build_succeeded=True,
            dbt_test_succeeded=True,
            runtime_contract_succeeded=True,
        ),
        now=NOW + timedelta(minutes=1),
    )
    return target


def _definition(candidates: InMemoryCandidateRegistry, contract_version: str) -> ReleaseDefinition:
    return build_release_definition(candidates, target=_tested_target(candidates, contract_version))


def _resolver_with_active_release() -> tuple[
    ActiveReleaseResolver, ReleaseDefinition, InMemoryReleaseRegistry
]:
    candidates = InMemoryCandidateRegistry()
    definition = _definition(candidates, "silver-contract-v1")
    registry = InMemoryReleaseRegistry()
    registry.register_definition(definition, actor_service="release-owner", now=NOW)
    registry.activate(
        definition.release_id,
        expected_pointer_version=0,
        actor_service="release-owner",
        now=NOW,
    )
    return (
        ActiveReleaseResolver(registry=registry, catalog=load_semantic_catalog(CATALOG_PATH)),
        definition,
        registry,
    )


def test_request_resolver_pins_allowlisted_semantic_refs_to_one_active_release() -> None:
    resolver, definition, _ = _resolver_with_active_release()

    pin = resolver.resolve(
        audience=ServingAudience.DASHBOARD,
        logical_names=("ORDER_DELIVERY", "PRODUCT_REVIEW"),
    )

    expected_refs = {
        item.logical_name: item.physical_ref
        for item in definition.object_refs
        if item.layer is CandidateLayer.GOLD
    }
    assert pin.release_id == definition.release_id
    assert pin.definition_sha256 == definition.definition_sha256
    assert pin.source_release_id == definition.source_release_id
    assert pin.pointer_version == 1
    assert pin.audience is ServingAudience.DASHBOARD
    assert pin.definition == definition
    assert {item.layer for item in pin.definition.object_refs} == {
        CandidateLayer.SILVER,
        CandidateLayer.GOLD,
    }
    assert tuple(item.logical_name for item in pin.relations) == (
        "ORDER_DELIVERY",
        "PRODUCT_REVIEW",
    )
    assert [item.physical_ref for item in pin.relations] == [
        expected_refs["SEM_ORDER_DELIVERY"],
        expected_refs["SEM_PRODUCT_REVIEW"],
    ]
    assert all(
        item.physical_ref.object_name.startswith(f"C_{definition.gold_candidate_id.upper()}__")
        for item in pin.relations
    )


@pytest.mark.parametrize(
    "logical_names",
    [
        (),
        ("order_delivery",),
        ("SEM_ORDER_DELIVERY",),
        ("REVIEWLENS.GOLD.SEM_ORDER_DELIVERY",),
        ("BRZ_OLIST_ORDERS_RAW",),
        ("ORDER_DELIVERY", "ORDER_DELIVERY"),
    ],
)
def test_request_resolver_rejects_unsafe_or_ambiguous_inputs(
    logical_names: tuple[str, ...],
) -> None:
    resolver, _, _ = _resolver_with_active_release()

    with pytest.raises(ReleaseResolutionError) as error:
        resolver.resolve(audience=ServingAudience.DASHBOARD, logical_names=logical_names)

    assert str(error.value) == ReleaseResolutionError.code
    assert all(value not in str(error.value) for value in logical_names)


def test_request_resolver_requires_an_active_pointer_and_owned_argument_types() -> None:
    resolver = ActiveReleaseResolver(
        registry=InMemoryReleaseRegistry(),
        catalog=load_semantic_catalog(CATALOG_PATH),
    )

    with pytest.raises(ReleaseResolutionError) as error:
        resolver.resolve(audience=ServingAudience.DASHBOARD, logical_names=("ORDER_DELIVERY",))
    assert str(error.value) == ReleaseResolutionError.code

    active_resolver, _, _ = _resolver_with_active_release()
    with pytest.raises(ReleaseResolutionError):
        active_resolver.resolve(
            audience=cast(ServingAudience, "DASHBOARD"),
            logical_names=cast(tuple[str, ...], "ORDER_DELIVERY"),
        )


def test_request_resolver_never_mixes_refs_when_activation_races() -> None:
    candidates = InMemoryCandidateRegistry()
    first = _definition(candidates, "silver-contract-v1")
    second = _definition(candidates, "silver-contract-v2")
    registry = InMemoryReleaseRegistry()
    for definition in (first, second):
        registry.register_definition(definition, actor_service="release-owner", now=NOW)
    registry.activate(
        first.release_id,
        expected_pointer_version=0,
        actor_service="release-owner",
        now=NOW,
    )
    resolver = ActiveReleaseResolver(registry=registry, catalog=load_semantic_catalog(CATALOG_PATH))
    barrier = Barrier(17)

    def resolve() -> ReleaseRequestPin:
        barrier.wait()
        return resolver.resolve(
            audience=ServingAudience.TEXT_TO_SQL,
            logical_names=SEMANTIC_LOGICAL_NAMES,
        )

    def activate() -> ReleaseTransition:
        barrier.wait()
        return registry.activate(
            second.release_id,
            expected_pointer_version=1,
            actor_service="release-owner",
            now=NOW + timedelta(seconds=1),
        )

    with ThreadPoolExecutor(max_workers=17) as pool:
        resolve_futures = [pool.submit(resolve) for _ in range(16)]
        activation = pool.submit(activate).result()
        pins = tuple(future.result() for future in resolve_futures)

    definitions = {first.release_id: first, second.release_id: second}
    assert activation.pointer.pointer_version == 2
    assert len(pins) == 16
    for pin in pins:
        definition = definitions[pin.release_id]
        assert pin.pointer_version in {1, 2}
        assert len(pin.relations) == len(SEMANTIC_LOGICAL_NAMES)
        assert {
            relation.physical_ref.object_name.split("__", maxsplit=1)[0]
            for relation in pin.relations
        } == {f"C_{definition.gold_candidate_id.upper()}"}


def test_release_definition_rejects_refs_from_another_candidate_namespace() -> None:
    candidates = InMemoryCandidateRegistry()
    definition = _definition(candidates, "silver-contract-v1")
    original = definition.object_refs[-1]
    foreign = replace(
        original,
        physical_ref=PhysicalRelationRef(
            "REVIEWLENS",
            original.layer.value,
            f"C_{'F' * 64}__{original.logical_name}",
        ),
    )

    with pytest.raises(ReleaseContractError) as error:
        replace(definition, object_refs=(*definition.object_refs[:-1], foreign))

    assert str(error.value) == ReleaseContractError.code
    with pytest.raises(ReleaseContractError):
        replace(
            definition,
            object_refs=tuple(sorted((*definition.object_refs, definition.object_refs[0]))),
        )
