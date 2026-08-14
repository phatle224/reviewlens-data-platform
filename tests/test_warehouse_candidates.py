from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest

from reviewlens.warehouse.candidates import (
    CandidateLayer,
    CandidateState,
    InMemoryCandidateRegistry,
    PhysicalRelationRef,
    ProcessingInput,
    ProcessingInputKind,
    ProcessingRunDefinition,
    WarehouseCandidateError,
    build_candidate_definition,
    build_processing_run,
)
from reviewlens.warehouse.quality import evaluate_quality_gate

SOURCE_RELEASE_ID = f"olist_{'a' * 64}"
BATCH_ID = f"batch_{'b' * 64}"
NOW = datetime(2026, 8, 14, 2, 0, tzinfo=UTC)


def _inputs() -> tuple[ProcessingInput, ...]:
    return (
        ProcessingInput(
            kind=ProcessingInputKind.BRONZE_RELATION,
            logical_name="CUSTOMERS",
            physical_ref=PhysicalRelationRef(
                "REVIEWLENS",
                "BRONZE",
                "BRZ_OLIST_CUSTOMERS_RAW",
            ),
            version_id=f"dsrun_{'c' * 64}",
            content_sha256="d" * 64,
        ),
        ProcessingInput(
            kind=ProcessingInputKind.BRONZE_RELATION,
            logical_name="ORDERS",
            physical_ref=PhysicalRelationRef(
                "REVIEWLENS",
                "BRONZE",
                "BRZ_OLIST_ORDERS_RAW",
            ),
            version_id=f"dsrun_{'e' * 64}",
            content_sha256="f" * 64,
        ),
    )


def _run(contract_version: str = "silver-contract-v1") -> ProcessingRunDefinition:
    return build_processing_run(
        contract_version=contract_version,
        phase=CandidateLayer.SILVER,
        source_release_id=SOURCE_RELEASE_ID,
        ingestion_batch_id=BATCH_ID,
        inputs=_inputs(),
    )


def test_processing_run_is_order_independent_and_has_ordered_one_to_many_refs() -> None:
    first = _run()
    second = build_processing_run(
        contract_version="silver-contract-v1",
        phase=CandidateLayer.SILVER,
        source_release_id=SOURCE_RELEASE_ID,
        ingestion_batch_id=BATCH_ID,
        inputs=reversed(_inputs()),
    )

    assert first == second
    assert len(first.processing_run_id) == 64
    assert [item.input_ordinal for item in first.inputs] == [1, 2]
    assert len({item.input_ref_id for item in first.inputs}) == 2
    assert [item.input.logical_name for item in first.inputs] == ["CUSTOMERS", "ORDERS"]


def test_same_bronze_inputs_can_lineage_to_multiple_contract_reprocess_runs() -> None:
    registry = InMemoryCandidateRegistry()
    first = _run("silver-contract-v1")
    second = _run("silver-contract-v2")

    registry.append_run(first)
    registry.append_run(first)
    registry.append_run(second)

    linked = registry.runs_for_input(first.inputs[0].input.version_id)
    assert {item.processing_run_id for item in linked} == {
        first.processing_run_id,
        second.processing_run_id,
    }


def test_invalid_or_duplicate_lineage_fails_closed_without_echoing_input() -> None:
    seeded = "SEEDED_SECRET_VALUE"
    with pytest.raises(WarehouseCandidateError) as invalid_ref:
        PhysicalRelationRef("REVIEWLENS", "BRONZE", seeded)
    with pytest.raises(WarehouseCandidateError) as duplicate:
        build_processing_run(
            contract_version="silver-contract-v1",
            phase=CandidateLayer.SILVER,
            source_release_id=SOURCE_RELEASE_ID,
            ingestion_batch_id=BATCH_ID,
            inputs=(_inputs()[0], _inputs()[0]),
        )

    assert str(invalid_ref.value) == WarehouseCandidateError.code
    assert str(duplicate.value) == WarehouseCandidateError.code
    assert seeded not in str(invalid_ref.value)


def test_candidate_namespaces_isolate_concurrent_processing_runs() -> None:
    first = build_candidate_definition(_run("silver-contract-v1"))
    second = build_candidate_definition(_run("silver-contract-v2"))

    assert first.candidate_id != second.candidate_id
    assert first.physical_namespace != second.physical_namespace
    first_relation = first.relation("SIL_CUSTOMER")
    second_relation = second.relation("SIL_CUSTOMER")
    assert first_relation.schema == second_relation.schema == "SILVER"
    assert first_relation.object_name != second_relation.object_name
    assert first.candidate_id.upper() in first_relation.object_name


def test_exactly_one_owner_claims_candidate_concurrently() -> None:
    run = _run()
    definition = build_candidate_definition(run)
    registry = InMemoryCandidateRegistry()
    registry.append_run(run)
    registry.register_candidate(definition)

    def claim(owner: str) -> str:
        try:
            return registry.claim(
                definition.candidate_id,
                owner_id=owner,
                now=NOW,
                expires_at=NOW + timedelta(minutes=10),
            ).owner_id
        except WarehouseCandidateError:
            return "DENIED"

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = tuple(pool.map(claim, (f"worker-{item}" for item in range(8))))

    assert outcomes.count("DENIED") == 7
    assert registry.get(definition.candidate_id).state is CandidateState.BUILDING


def test_cleanup_only_accepts_failed_unreferenced_candidate() -> None:
    run = _run()
    definition = build_candidate_definition(run)
    registry = InMemoryCandidateRegistry()
    registry.append_run(run)
    registry.register_candidate(definition)
    lease = registry.claim(
        definition.candidate_id,
        owner_id="worker-1",
        now=NOW,
        expires_at=NOW + timedelta(minutes=10),
    )

    with pytest.raises(WarehouseCandidateError):
        registry.cleanup(definition.candidate_id)
    failed = registry.fail(lease, now=NOW + timedelta(minutes=1))
    assert failed.state is CandidateState.FAILED
    with pytest.raises(WarehouseCandidateError):
        registry.cleanup(
            definition.candidate_id,
            active_candidate_ids=(definition.candidate_id,),
        )

    assert registry.cleanup(definition.candidate_id).state is CandidateState.CLEANED


def test_tested_candidate_cannot_be_cleaned_or_reclaimed() -> None:
    run = _run()
    definition = build_candidate_definition(run)
    registry = InMemoryCandidateRegistry()
    registry.append_run(run)
    registry.register_candidate(definition)
    lease = registry.claim(
        definition.candidate_id,
        owner_id="worker-1",
        now=NOW,
        expires_at=NOW + timedelta(minutes=10),
    )
    passed = registry.finish_quality_gate(
        lease,
        result=evaluate_quality_gate(()),
        now=NOW + timedelta(minutes=1),
    )

    assert passed.state is CandidateState.TEST_PASSED
    with pytest.raises(WarehouseCandidateError):
        registry.cleanup(definition.candidate_id)
    with pytest.raises(WarehouseCandidateError):
        registry.claim(
            definition.candidate_id,
            owner_id="worker-2",
            now=NOW + timedelta(minutes=2),
            expires_at=NOW + timedelta(minutes=12),
        )
