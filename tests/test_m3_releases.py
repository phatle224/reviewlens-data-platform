from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

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
from reviewlens.warehouse.releases import (
    RELEASE_DEFINITION_VERSION,
    RELEASE_POINTER_NAME,
    InMemoryReleaseRegistry,
    ReleaseContractError,
    ReleaseDefinition,
    ReleaseEventType,
    build_release_definition,
)

SOURCE_RELEASE_ID = f"olist_{'a' * 64}"
BATCH_ID = f"batch_{'b' * 64}"
NOW = datetime(2026, 8, 16, 4, 0, tzinfo=UTC)
MIGRATION = Path("infra/snowflake/007_atomic_release.sql")


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


def test_release_definition_is_deterministic_immutable_and_has_exact_candidate_refs() -> None:
    candidates = InMemoryCandidateRegistry()
    target = _tested_target(candidates, "silver-contract-v1")

    first = build_release_definition(candidates, target=target)
    second = build_release_definition(candidates, target=target)
    releases = InMemoryReleaseRegistry()

    assert first == second
    assert first.release_id == first.definition_sha256
    assert first.definition_version == RELEASE_DEFINITION_VERSION
    assert len(first.object_refs) == 28
    assert {item.layer.value for item in first.object_refs} == {"SILVER", "GOLD"}
    assert {item.physical_ref.schema for item in first.object_refs} == {"SILVER", "GOLD"}
    assert releases.register_definition(first, actor_service="release-owner", now=NOW) == first
    assert releases.register_definition(first, actor_service="release-owner", now=NOW) == first
    assert [event.event_type for event in releases.events] == [ReleaseEventType.CREATED]


def test_failed_candidate_cannot_create_definition_or_change_an_active_pointer() -> None:
    candidates = InMemoryCandidateRegistry()
    baseline = _definition(candidates, "silver-contract-v1")
    releases = InMemoryReleaseRegistry()
    releases.register_definition(baseline, actor_service="release-owner", now=NOW)
    active = releases.activate(
        baseline.release_id,
        expected_pointer_version=0,
        actor_service="release-owner",
        now=NOW,
    )

    silver_run = _silver_run("silver-contract-v2")
    silver_candidate = build_candidate_definition(silver_run)
    candidates.append_run(silver_run)
    candidates.register_candidate(silver_candidate)
    failed_target = plan_gold_candidate_target(
        silver_run=silver_run,
        silver_candidate=silver_candidate,
    )
    candidates.append_run(failed_target.gold_run)
    candidates.register_candidate(failed_target.gold_candidate)

    with pytest.raises(ReleaseContractError) as error:
        build_release_definition(candidates, target=failed_target)

    assert str(error.value) == ReleaseContractError.code
    assert releases.active_pointer == active.pointer
    assert len(releases.events) == 2


def test_activation_replay_rollback_and_stale_compare_and_set_are_deterministic() -> None:
    candidates = InMemoryCandidateRegistry()
    first = _definition(candidates, "silver-contract-v1")
    second = _definition(candidates, "silver-contract-v2")
    releases = InMemoryReleaseRegistry()
    for definition in (first, second):
        releases.register_definition(definition, actor_service="release-owner", now=NOW)

    activated = releases.activate(
        first.release_id,
        expected_pointer_version=0,
        actor_service="release-owner",
        now=NOW,
    )
    replay = releases.activate(
        first.release_id,
        expected_pointer_version=0,
        actor_service="release-owner",
        now=NOW + timedelta(seconds=1),
    )
    switched = releases.activate(
        second.release_id,
        expected_pointer_version=1,
        actor_service="release-owner",
        now=NOW + timedelta(seconds=2),
    )
    with pytest.raises(ReleaseContractError):
        releases.activate(
            first.release_id,
            expected_pointer_version=1,
            actor_service="release-owner",
            now=NOW + timedelta(seconds=3),
        )
    rolled_back = releases.rollback(
        first.release_id,
        expected_pointer_version=2,
        actor_service="release-owner",
        now=NOW + timedelta(seconds=4),
    )
    rollback_replay = releases.rollback(
        first.release_id,
        expected_pointer_version=2,
        actor_service="release-owner",
        now=NOW + timedelta(seconds=5),
    )

    assert activated.pointer.pointer_version == 1
    assert replay.replayed is True
    assert replay.event == activated.event
    assert switched.pointer.pointer_version == 2
    assert rolled_back.pointer.pointer_version == 3
    assert rolled_back.event.event_type is ReleaseEventType.ROLLED_BACK
    assert rolled_back.event.previous_release_id == second.release_id
    assert rollback_replay.replayed is True
    assert releases.active_pointer == rolled_back.pointer


def test_concurrent_compare_and_set_allows_one_winner_only() -> None:
    candidates = InMemoryCandidateRegistry()
    baseline = _definition(candidates, "silver-contract-v1")
    left = _definition(candidates, "silver-contract-v2")
    right = _definition(candidates, "silver-contract-v3")
    releases = InMemoryReleaseRegistry()
    for definition in (baseline, left, right):
        releases.register_definition(definition, actor_service="release-owner", now=NOW)
    releases.activate(
        baseline.release_id,
        expected_pointer_version=0,
        actor_service="release-owner",
        now=NOW,
    )

    def activate(release_id: str) -> str:
        try:
            return releases.activate(
                release_id,
                expected_pointer_version=1,
                actor_service="release-owner",
                now=NOW + timedelta(seconds=1),
            ).pointer.release_id
        except ReleaseContractError:
            return "DENIED"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = tuple(pool.map(activate, (left.release_id, right.release_id)))

    assert outcomes.count("DENIED") == 1
    assert releases.active_pointer is not None
    assert releases.active_pointer.pointer_version == 2
    assert releases.active_pointer.release_id in {left.release_id, right.release_id}


def test_terminal_release_cannot_activate_and_active_release_cannot_be_terminal() -> None:
    candidates = InMemoryCandidateRegistry()
    first = _definition(candidates, "silver-contract-v1")
    second = _definition(candidates, "silver-contract-v2")
    releases = InMemoryReleaseRegistry()
    for definition in (first, second):
        releases.register_definition(definition, actor_service="release-owner", now=NOW)
    releases.activate(
        first.release_id, expected_pointer_version=0, actor_service="release-owner", now=NOW
    )
    releases.activate(
        second.release_id,
        expected_pointer_version=1,
        actor_service="release-owner",
        now=NOW + timedelta(seconds=1),
    )

    invalidated = releases.invalidate(
        first.release_id,
        actor_service="release-owner",
        now=NOW + timedelta(seconds=2),
    )
    with pytest.raises(ReleaseContractError):
        releases.activate(
            first.release_id,
            expected_pointer_version=2,
            actor_service="release-owner",
            now=NOW + timedelta(seconds=3),
        )
    with pytest.raises(ReleaseContractError):
        releases.revoke(
            second.release_id,
            actor_service="release-owner",
            now=NOW + timedelta(seconds=3),
        )

    assert invalidated.event_type is ReleaseEventType.INVALIDATED
    assert releases.active_pointer is not None
    assert releases.active_pointer.release_id == second.release_id
    assert releases.active_pointer.pointer_name == RELEASE_POINTER_NAME


def test_release_errors_are_sanitized_and_do_not_echo_actor_input() -> None:
    releases = InMemoryReleaseRegistry()
    seeded = "SEEDED_SECRET_VALUE"

    with pytest.raises(ReleaseContractError) as error:
        releases.activate(
            "a" * 64,
            expected_pointer_version=0,
            actor_service=seeded,
            now=NOW,
        )

    assert str(error.value) == ReleaseContractError.code
    assert seeded not in str(error.value)


def test_atomic_release_migration_is_append_only_and_keeps_pointer_mutation_in_procedures() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    upper = source.upper()

    assert "CREATE TABLE IF NOT EXISTS REVIEWLENS.AUDIT.RELEASE_DEFINITION" in upper
    assert "CREATE TABLE IF NOT EXISTS REVIEWLENS.AUDIT.RELEASE_OBJECT_REF" in upper
    assert "MERGE INTO REVIEWLENS.AUDIT.ACTIVE_RELEASE_POINTER" in upper
    assert "CREATE PROCEDURE IF NOT EXISTS REVIEWLENS.AUDIT.ACTIVATE_RELEASE_V1" in upper
    assert "CREATE PROCEDURE IF NOT EXISTS REVIEWLENS.AUDIT.ROLLBACK_RELEASE_V1" in upper
    assert upper.count("BEGIN TRANSACTION") == 2
    assert upper.count("SQLROWCOUNT") == 2
    assert "EXPECTED_POINTER_VERSION" in upper
    assert "RESULT_POINTER_VERSION" in upper
    assert "GRANT EXECUTE ON PROCEDURE" in upper
    assert "GRANT UPDATE ON TABLE REVIEWLENS.AUDIT.ACTIVE_RELEASE_POINTER" not in upper
    for forbidden in ("RAW_PAYLOAD", "REVIEW_TEXT", "API_KEY", "PRIVATE_KEY", "PASSWORD"):
        assert forbidden not in upper
