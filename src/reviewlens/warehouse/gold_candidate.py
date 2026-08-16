"""Fail-closed planning and test evidence for isolated M3 Gold candidates."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime

from reviewlens.warehouse.candidates import (
    CandidateDefinition,
    CandidateLayer,
    CandidateLease,
    CandidateRecord,
    InMemoryCandidateRegistry,
    PhysicalRelationRef,
    ProcessingInput,
    ProcessingInputKind,
    ProcessingRunDefinition,
    WarehouseCandidateError,
    build_candidate_definition,
    build_processing_run,
)

GOLD_CANDIDATE_BUILD_VERSION = "reviewlens-gold-candidate-build-v1"
GOLD_CANDIDATE_SELECTOR = "m3_gold_candidate"

SILVER_GOLD_INPUT_LOGICAL_NAMES = (
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
)

GOLD_CANDIDATE_MODEL_NAMES = frozenset(
    {
        "bridge_review_item_attribution",
        "dim_customer",
        "dim_date",
        "dim_geography",
        "dim_product",
        "dim_seller",
        "fact_order",
        "fact_order_item",
        "fact_payment",
        "fact_review_base",
        "mart_customer_overview",
        "mart_order_delivery",
        "mart_product_review",
        "mart_seller_performance",
        "sem_customer_overview",
        "sem_order_delivery",
        "sem_product_review",
        "sem_seller_performance",
    }
)

GOLD_CANDIDATE_OUTPUT_LOGICAL_NAMES = (
    "BRIDGE_REVIEW_ITEM_ATTRIBUTION",
    "DIM_CUSTOMER",
    "DIM_DATE",
    "DIM_GEOGRAPHY",
    "DIM_PRODUCT",
    "DIM_SELLER",
    "FACT_ORDER",
    "FACT_ORDER_ITEM",
    "FACT_PAYMENT",
    "FACT_REVIEW_BASE",
    "MART_CUSTOMER_OVERVIEW",
    "MART_ORDER_DELIVERY",
    "MART_PRODUCT_REVIEW",
    "MART_SELLER_PERFORMANCE",
    "SEM_CUSTOMER_OVERVIEW",
    "SEM_ORDER_DELIVERY",
    "SEM_PRODUCT_REVIEW",
    "SEM_SELLER_PERFORMANCE",
)

_HASH = re.compile(r"^[0-9a-f]{64}$")


class GoldCandidateTargetError(ValueError):
    """Sanitized target error that never includes a relation or runtime value."""

    code = "WAREHOUSE_GOLD_CANDIDATE_INVALID"

    def __init__(self) -> None:
        super().__init__(self.code)


@dataclass(frozen=True, slots=True)
class GoldCandidateBuildTarget:
    """One isolated Gold build destination and its immutable Silver input."""

    silver_run: ProcessingRunDefinition
    silver_candidate: CandidateDefinition
    gold_run: ProcessingRunDefinition
    gold_candidate: CandidateDefinition

    def __post_init__(self) -> None:
        if (
            self.silver_run.phase is not CandidateLayer.SILVER
            or self.silver_candidate.layer is not CandidateLayer.SILVER
            or self.silver_candidate.processing_run_id != self.silver_run.processing_run_id
            or self.gold_run.phase is not CandidateLayer.GOLD
            or self.gold_candidate.layer is not CandidateLayer.GOLD
            or self.gold_candidate.processing_run_id != self.gold_run.processing_run_id
            or self.gold_candidate.strategy_version != GOLD_CANDIDATE_BUILD_VERSION
            or self.silver_candidate.physical_namespace == self.gold_candidate.physical_namespace
            or self.gold_run.source_release_id != self.silver_run.source_release_id
            or self.gold_run.ingestion_batch_id != self.silver_run.ingestion_batch_id
            or self.gold_run.contract_version != GOLD_CANDIDATE_BUILD_VERSION
        ):
            raise GoldCandidateTargetError()

        inputs = {item.input.logical_name: item.input for item in self.gold_run.inputs}
        if set(inputs) != set(SILVER_GOLD_INPUT_LOGICAL_NAMES):
            raise GoldCandidateTargetError()
        for logical_name in SILVER_GOLD_INPUT_LOGICAL_NAMES:
            input_relation = inputs[logical_name]
            if (
                input_relation.kind is not ProcessingInputKind.CANDIDATE_RELATION
                or input_relation.physical_ref != self.silver_candidate.relation(logical_name)
                or input_relation.version_id != f"candidate-{self.silver_candidate.candidate_id}"
                or input_relation.content_sha256 != self.silver_candidate.candidate_id
            ):
                raise GoldCandidateTargetError()

    @property
    def dbt_vars(self) -> dict[str, str]:
        """Return the only variables an isolated Gold dbt run may receive."""

        return {
            "candidate_namespace": self.gold_candidate.physical_namespace,
            "ingestion_batch_id": self.gold_run.ingestion_batch_id,
            "silver_candidate_namespace": self.silver_candidate.physical_namespace,
            "source_release_id": self.gold_run.source_release_id,
        }

    @property
    def dbt_vars_json(self) -> str:
        """Return deterministic JSON accepted by dbt's ``--vars`` option."""

        return json.dumps(self.dbt_vars, separators=(",", ":"), sort_keys=True)

    @property
    def output_relations(self) -> tuple[PhysicalRelationRef, ...]:
        """Return the exact non-serving physical outputs expected from the target."""

        return tuple(
            self.gold_candidate.relation(logical_name)
            for logical_name in GOLD_CANDIDATE_OUTPUT_LOGICAL_NAMES
        )


@dataclass(frozen=True, slots=True)
class GoldCandidateBuildEvidence:
    """Sanitized dbt build/test outcome that may advance only this candidate."""

    candidate_id: str
    selected_model_names: frozenset[str]
    dbt_build_succeeded: bool
    dbt_test_succeeded: bool
    runtime_contract_succeeded: bool

    def __post_init__(self) -> None:
        if (
            _HASH.fullmatch(self.candidate_id) is None
            or not self.selected_model_names
            or not all(isinstance(name, str) for name in self.selected_model_names)
            or any("\n" in name or "\r" in name for name in self.selected_model_names)
            or any(type(value) is not bool for value in self._outcomes)
        ):
            raise GoldCandidateTargetError()

    @property
    def _outcomes(self) -> tuple[bool, bool, bool]:
        return (
            self.dbt_build_succeeded,
            self.dbt_test_succeeded,
            self.runtime_contract_succeeded,
        )

    @property
    def can_advance(self) -> bool:
        """Only a complete, successful selector result can reach TEST_PASSED."""

        return self.selected_model_names == GOLD_CANDIDATE_MODEL_NAMES and all(self._outcomes)


def plan_gold_candidate_target(
    *,
    silver_run: ProcessingRunDefinition,
    silver_candidate: CandidateDefinition,
) -> GoldCandidateBuildTarget:
    """Plan a deterministic Gold candidate without connecting to Snowflake."""

    if (
        not isinstance(silver_run, ProcessingRunDefinition)
        or not isinstance(silver_candidate, CandidateDefinition)
        or silver_run.phase is not CandidateLayer.SILVER
        or silver_candidate.layer is not CandidateLayer.SILVER
        or silver_candidate.processing_run_id != silver_run.processing_run_id
    ):
        raise GoldCandidateTargetError()

    inputs = tuple(
        ProcessingInput(
            kind=ProcessingInputKind.CANDIDATE_RELATION,
            logical_name=logical_name,
            physical_ref=silver_candidate.relation(logical_name),
            version_id=f"candidate-{silver_candidate.candidate_id}",
            content_sha256=silver_candidate.candidate_id,
        )
        for logical_name in SILVER_GOLD_INPUT_LOGICAL_NAMES
    )
    try:
        gold_run = build_processing_run(
            contract_version=GOLD_CANDIDATE_BUILD_VERSION,
            phase=CandidateLayer.GOLD,
            source_release_id=silver_run.source_release_id,
            ingestion_batch_id=silver_run.ingestion_batch_id,
            inputs=inputs,
        )
        gold_candidate = build_candidate_definition(
            gold_run,
            strategy_version=GOLD_CANDIDATE_BUILD_VERSION,
        )
    except WarehouseCandidateError as error:
        raise GoldCandidateTargetError() from error
    return GoldCandidateBuildTarget(
        silver_run=silver_run,
        silver_candidate=silver_candidate,
        gold_run=gold_run,
        gold_candidate=gold_candidate,
    )


def finish_gold_candidate_target(
    registry: InMemoryCandidateRegistry,
    *,
    target: GoldCandidateBuildTarget,
    lease: CandidateLease,
    evidence: GoldCandidateBuildEvidence,
    now: datetime,
) -> CandidateRecord:
    """Record pass/fail evidence; a failed or incomplete target cannot pass tests."""

    if (
        not isinstance(registry, InMemoryCandidateRegistry)
        or lease.candidate_id != target.gold_candidate.candidate_id
        or evidence.candidate_id != target.gold_candidate.candidate_id
    ):
        raise GoldCandidateTargetError()
    try:
        return registry.finish_test_gate(lease, passed=evidence.can_advance, now=now)
    except WarehouseCandidateError as error:
        raise GoldCandidateTargetError() from error
