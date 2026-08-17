"""Safe planning and aggregate evidence codecs for the private M3 replay drill."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from reviewlens.ingestion.bronze import BRONZE_TABLE_BY_DATASET
from reviewlens.ingestion.contracts import load_olist_contract
from reviewlens.ingestion.identity import dataset_run_id, ingestion_batch_id, source_object_id
from reviewlens.ingestion.preflight import (
    approved_source_release_id,
    load_approved_olist_snapshot,
)
from reviewlens.warehouse.candidates import (
    CANDIDATE_STRATEGY_VERSION,
    CandidateDefinition,
    CandidateLayer,
    PhysicalRelationRef,
    ProcessingInput,
    ProcessingInputKind,
    ProcessingRunDefinition,
    WarehouseCandidateError,
    build_candidate_definition,
    build_processing_run,
)
from reviewlens.warehouse.equivalence import (
    CandidateBuildMode,
    CandidateEquivalenceSnapshot,
    CandidatePair,
    RelationFingerprint,
    WarehouseEquivalenceError,
)
from reviewlens.warehouse.gold_candidate import (
    GOLD_CANDIDATE_OUTPUT_LOGICAL_NAMES,
    GOLD_CANDIDATE_SELECTOR,
    GoldCandidateBuildTarget,
    plan_gold_candidate_target,
)
from reviewlens.warehouse.releases import SILVER_RELEASE_LOGICAL_NAMES
from reviewlens.warehouse.semantic import SEMANTIC_CATALOG_VERSION

M3_REPLAY_DRILL_VERSION = "reviewlens-m3-replay-drill-v1"
M3_SILVER_CANDIDATE_SELECTOR = "m3_silver_candidate"
M3_FINGERPRINT_METHOD = "snowflake-hash-agg-sha2-v1"

_EXPECTED_FINGERPRINT_KEYS = frozenset(
    {(CandidateLayer.SILVER.value, logical_name) for logical_name in SILVER_RELEASE_LOGICAL_NAMES}
    | {
        (CandidateLayer.GOLD.value, logical_name)
        for logical_name in GOLD_CANDIDATE_OUTPUT_LOGICAL_NAMES
    }
)


class M3ReplayDrillError(ValueError):
    """Sanitized drill-plan or aggregate-evidence validation error."""

    code = "M3_REPLAY_DRILL_INVALID"

    def __init__(self) -> None:
        super().__init__(self.code)


@dataclass(frozen=True, slots=True)
class DbtBuildPlan:
    """One non-secret dbt build command prepared without executing it."""

    selector: str
    variables: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        if (
            self.selector not in {M3_SILVER_CANDIDATE_SELECTOR, GOLD_CANDIDATE_SELECTOR}
            or not self.variables
            or tuple(sorted(self.variables)) != self.variables
            or len({key for key, _ in self.variables}) != len(self.variables)
            or any(not key.isidentifier() or not value for key, value in self.variables)
        ):
            raise M3ReplayDrillError()

    @property
    def vars_json(self) -> str:
        return json.dumps(
            dict(self.variables), ensure_ascii=True, separators=(",", ":"), sort_keys=True
        )

    def argv(self, *, executable: str = "dbt") -> tuple[str, ...]:
        if executable != "dbt":
            raise M3ReplayDrillError()
        return (
            executable,
            "build",
            "--project-dir",
            "dbt",
            "--profiles-dir",
            "dbt",
            "--selector",
            self.selector,
            "--vars",
            self.vars_json,
        )


@dataclass(frozen=True, slots=True)
class M3ReplayDrillPlan:
    """Immutable Silver/Gold candidate pair and commands for one static-snapshot drill."""

    source_release_id: str
    ingestion_batch_id: str
    silver_run: ProcessingRunDefinition
    silver_candidate: CandidateDefinition
    gold_target: GoldCandidateBuildTarget
    contract_version: str = M3_REPLAY_DRILL_VERSION

    def __post_init__(self) -> None:
        if (
            self.contract_version != M3_REPLAY_DRILL_VERSION
            or self.silver_run.phase is not CandidateLayer.SILVER
            or self.silver_candidate.layer is not CandidateLayer.SILVER
            or self.silver_candidate.processing_run_id != self.silver_run.processing_run_id
            or self.silver_run.source_release_id != self.source_release_id
            or self.silver_run.ingestion_batch_id != self.ingestion_batch_id
            or self.gold_target.silver_run != self.silver_run
            or self.gold_target.silver_candidate != self.silver_candidate
            or self.gold_target.gold_run.source_release_id != self.source_release_id
            or self.gold_target.gold_run.ingestion_batch_id != self.ingestion_batch_id
            or len(self.silver_run.inputs) != len(BRONZE_TABLE_BY_DATASET)
            or {item.input.logical_name for item in self.silver_run.inputs}
            != {dataset_name.upper() for dataset_name in BRONZE_TABLE_BY_DATASET}
        ):
            raise M3ReplayDrillError()

    @property
    def candidate_pair(self) -> CandidatePair:
        return CandidatePair(
            silver_candidate_id=self.silver_candidate.candidate_id,
            gold_candidate_id=self.gold_target.gold_candidate.candidate_id,
        )

    @property
    def silver_build(self) -> DbtBuildPlan:
        return DbtBuildPlan(
            selector=M3_SILVER_CANDIDATE_SELECTOR,
            variables=tuple(
                sorted(
                    {
                        "candidate_namespace": self.silver_candidate.physical_namespace,
                        "ingestion_batch_id": self.ingestion_batch_id,
                        "source_release_id": self.source_release_id,
                    }.items()
                )
            ),
        )

    @property
    def gold_build(self) -> DbtBuildPlan:
        return DbtBuildPlan(
            selector=GOLD_CANDIDATE_SELECTOR,
            variables=tuple(sorted(self.gold_target.dbt_vars.items())),
        )

    @property
    def gold_read_grants(self) -> tuple[str, ...]:
        """Return the ten exact Silver-object grants needed by the Gold builder."""

        return tuple(
            "GRANT SELECT ON TABLE "
            f"{self.silver_candidate.relation(logical_name).qualified_name} "
            "TO ROLE GOLD_BUILDER_ROLE"
            for logical_name in sorted(SILVER_RELEASE_LOGICAL_NAMES)
        )

    @property
    def fingerprint_sql(self) -> str:
        """Render one 28-relation aggregate-only query; never print this in public evidence."""

        relations = [
            *(
                (CandidateLayer.SILVER, logical_name, self.silver_candidate.relation(logical_name))
                for logical_name in sorted(SILVER_RELEASE_LOGICAL_NAMES)
            ),
            *(
                (
                    CandidateLayer.GOLD,
                    logical_name,
                    self.gold_target.gold_candidate.relation(logical_name),
                )
                for logical_name in self.gold_target_output_names
            ),
        ]
        return (
            "\nUNION ALL\n".join(
                _fingerprint_select(
                    layer=layer, logical_name=logical_name, physical_ref=physical_ref
                )
                for layer, logical_name, physical_ref in relations
            )
            + "\nORDER BY LAYER, LOGICAL_NAME"
        )

    @property
    def gold_target_output_names(self) -> tuple[str, ...]:
        return tuple(
            relation.object_name.rsplit("__", maxsplit=1)[1]
            for relation in self.gold_target.output_relations
        )

    @property
    def safe_summary(self) -> dict[str, Any]:
        """Return only identifiers/counts safe for a local operator console."""

        return {
            "contract_version": self.contract_version,
            "fingerprint_method": M3_FINGERPRINT_METHOD,
            "fingerprint_relation_count": len(SILVER_RELEASE_LOGICAL_NAMES)
            + len(self.gold_target_output_names),
            "gold_candidate_id": self.candidate_pair.gold_candidate_id,
            "gold_read_grant_count": len(self.gold_read_grants),
            "gold_selector": self.gold_build.selector,
            "ingestion_batch_id": self.ingestion_batch_id,
            "silver_candidate_id": self.candidate_pair.silver_candidate_id,
            "silver_selector": self.silver_build.selector,
            "source_release_id": self.source_release_id,
        }


def build_approved_m3_replay_drill_plan() -> M3ReplayDrillPlan:
    """Plan a replay drill only for the committed approved nine-file Olist snapshot."""

    approved_snapshot = load_approved_olist_snapshot()
    source_release_id = approved_source_release_id(approved_snapshot)
    batch_id = ingestion_batch_id(source_release_id=source_release_id)
    snapshot_files = {item.file_name: item for item in approved_snapshot.files}
    inputs: list[ProcessingInput] = []
    for dataset in load_olist_contract().datasets:
        snapshot_file = snapshot_files.get(dataset.file_name)
        table_name = BRONZE_TABLE_BY_DATASET.get(dataset.dataset_name)
        if snapshot_file is None or table_name is None:
            raise M3ReplayDrillError()
        try:
            source_object = source_object_id(
                source_release_id=source_release_id,
                file_name=dataset.file_name,
                source_object_sha256=snapshot_file.sha256,
            )
            inputs.append(
                ProcessingInput(
                    kind=ProcessingInputKind.BRONZE_RELATION,
                    logical_name=dataset.dataset_name.upper(),
                    physical_ref=PhysicalRelationRef("REVIEWLENS", "BRONZE", table_name),
                    version_id=dataset_run_id(
                        ingestion_batch_id=batch_id,
                        source_object_id=source_object,
                        dataset_name=dataset.dataset_name,
                        contract_version=load_olist_contract().contract_version,
                    ),
                    content_sha256=snapshot_file.sha256,
                )
            )
        except (WarehouseCandidateError, ValueError) as error:
            raise M3ReplayDrillError() from error
    try:
        silver_run = build_processing_run(
            contract_version=CANDIDATE_STRATEGY_VERSION,
            phase=CandidateLayer.SILVER,
            source_release_id=source_release_id,
            ingestion_batch_id=batch_id,
            inputs=inputs,
        )
        silver_candidate = build_candidate_definition(silver_run)
        gold_target = plan_gold_candidate_target(
            silver_run=silver_run,
            silver_candidate=silver_candidate,
        )
    except (WarehouseCandidateError, ValueError) as error:
        raise M3ReplayDrillError() from error
    return M3ReplayDrillPlan(
        source_release_id=source_release_id,
        ingestion_batch_id=batch_id,
        silver_run=silver_run,
        silver_candidate=silver_candidate,
        gold_target=gold_target,
    )


def parse_fingerprint_rows(rows: Sequence[Sequence[object]]) -> tuple[RelationFingerprint, ...]:
    """Parse exactly 28 aggregate-only Snowflake rows without accepting raw values."""

    parsed: list[RelationFingerprint] = []
    try:
        for row in rows:
            if len(row) != 4:
                raise M3ReplayDrillError()
            layer, logical_name, row_count, content_sha256 = row
            parsed.append(
                RelationFingerprint(
                    layer=CandidateLayer(str(layer)),
                    logical_name=str(logical_name),
                    row_count=_row_count(row_count),
                    content_sha256=str(content_sha256).lower(),
                )
            )
        ordered = tuple(sorted(parsed))
        if (
            len(ordered) != len(parsed)
            or len({item.key for item in ordered}) != len(ordered)
            or {item.key for item in ordered} != _EXPECTED_FINGERPRINT_KEYS
        ):
            raise M3ReplayDrillError()
        return ordered
    except (TypeError, ValueError, WarehouseEquivalenceError) as error:
        if isinstance(error, M3ReplayDrillError):
            raise
        raise M3ReplayDrillError() from error


def snapshot_from_fingerprint_rows(
    *,
    plan: M3ReplayDrillPlan,
    mode: CandidateBuildMode,
    rows: Sequence[Sequence[object]],
) -> CandidateEquivalenceSnapshot:
    """Bind aggregate rows to one planned immutable Silver/Gold candidate pair."""

    if not isinstance(plan, M3ReplayDrillPlan) or not isinstance(mode, CandidateBuildMode):
        raise M3ReplayDrillError()
    try:
        return CandidateEquivalenceSnapshot(
            candidate_pair=plan.candidate_pair,
            build_mode=mode,
            source_release_id=plan.source_release_id,
            ingestion_batch_id=plan.ingestion_batch_id,
            semantic_contract_version=SEMANTIC_CATALOG_VERSION,
            relation_fingerprints=parse_fingerprint_rows(rows),
        )
    except WarehouseEquivalenceError as error:
        raise M3ReplayDrillError() from error


def _fingerprint_select(
    *,
    layer: CandidateLayer,
    logical_name: str,
    physical_ref: PhysicalRelationRef,
) -> str:
    return "\n".join(
        (
            f"SELECT '{layer.value}' AS LAYER, '{logical_name}' AS LOGICAL_NAME,",
            "       COUNT(*)::NUMBER(38,0) AS ROW_COUNT,",
            "       SHA2(TO_VARCHAR(HASH_AGG(*)), 256) AS CONTENT_SHA256",
            f"FROM {physical_ref.qualified_name}",
        )
    )


def _row_count(value: object) -> int:
    if isinstance(value, bool):
        raise M3ReplayDrillError()
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, Decimal) and value == value.to_integral_value():
        parsed = int(value)
    else:
        raise M3ReplayDrillError()
    if parsed < 0:
        raise M3ReplayDrillError()
    return parsed


def main(argv: Sequence[str] | None = None) -> None:
    """Print a safe no-provider plan; execution remains an explicit operator action."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--print-plan",
        action="store_true",
        help="print only candidate/source IDs, selectors and aggregate count",
    )
    arguments = parser.parse_args(argv)
    if not arguments.print_plan:
        parser.error("--print-plan is required; this command never executes dbt or Snowflake")
    print(json.dumps(build_approved_m3_replay_drill_plan().safe_summary, sort_keys=True))
