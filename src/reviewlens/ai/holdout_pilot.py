"""Bounded private OpenRouter pilot for the M4 human-labelled blind holdout.

The pilot reads restricted review text only from an ignored local queue, applies
the existing DLP projection before every provider request, and writes predictions
only to an ignored local path. Console output and errors are aggregate/sanitized.
"""

from __future__ import annotations

import argparse
import json
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from reviewlens.ai.budget import (
    EnrichmentBudget,
    EnrichmentPricing,
    estimate_tokens_from_char_count,
)
from reviewlens.ai.enrichment import (
    MAX_REVIEW_TEXT_CHARACTERS,
    DLPProjection,
    EnrichmentVersionInput,
    project_review_for_ai,
)
from reviewlens.ai.execution import (
    BudgetGuardedEnrichmentTransport,
    EnrichmentWork,
    EnrichmentWorkState,
    InMemoryEnrichmentExecutor,
    RateLimitedOpenRouterEnrichmentTransport,
)
from reviewlens.ai.golden_pack import (
    GoldenAnnotationPackError,
    load_completed_golden_labels,
)
from reviewlens.ai.prompt import (
    PORTUGUESE_ENRICHMENT_PROMPT_VERSION,
    build_portuguese_enrichment_prompt,
)
from reviewlens.ai.rate_limit import EnrichmentRateLimiter
from reviewlens.config import load_settings, project_root
from reviewlens.providers.openrouter import OpenRouterClient

_MAX_COMPLETION_TOKENS = 256
_MAX_PILOT_ATTEMPTS = 2
_CONTROL_OVERHEAD_TOKENS = 1_000
_PROMPT_PRICE_USD = Decimal("0.0000001")
_COMPLETION_PRICE_USD = Decimal("0.0000004")


class HoldoutPilotError(ValueError):
    """Sanitized error code for a private holdout pilot."""

    def __init__(self, code: str) -> None:
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class HoldoutPilotItem:
    """One DLP-approved blind-holdout item; text never appears in representations."""

    opaque_example_id: str
    projection: DLPProjection = field(repr=False)


@dataclass(frozen=True, slots=True)
class HoldoutPilotPreflight:
    """Aggregate-safe pilot readiness outcome."""

    enrichment_version: str
    holdout_count: int
    approved_count: int


@dataclass(frozen=True, slots=True)
class HoldoutPilotRun:
    """Aggregate-safe completed pilot outcome."""

    enrichment_version: str
    prediction_count: int


def preflight_private_holdout(
    *,
    labels_path: Path,
    annotation_queue_path: Path,
    split_seed: str,
    version_input: EnrichmentVersionInput,
) -> tuple[HoldoutPilotPreflight, tuple[HoldoutPilotItem, ...]]:
    """Resolve the exact blind holdout and DLP-approve every item before dispatch."""

    try:
        labels = load_completed_golden_labels(labels_path=labels_path)
        from reviewlens.ai.evaluation import stratified_golden_holdout_split

        split = stratified_golden_holdout_split(labels=labels, split_seed=split_seed)
    except GoldenAnnotationPackError as error:
        raise HoldoutPilotError(str(error)) from error
    queue = _load_private_queue(annotation_queue_path)
    if not set(split.holdout_ids).issubset(queue):
        raise HoldoutPilotError("AI_ENRICHMENT_PILOT_HOLDOUT_QUEUE_INVALID")

    approved: list[HoldoutPilotItem] = []
    for example_id in split.holdout_ids:
        source_hash, review_text = queue[example_id]
        projection = project_review_for_ai(
            source_record_hash=source_hash,
            review_title=None,
            review_comment=review_text,
        )
        if projection.decision.value != "approved":
            raise HoldoutPilotError("AI_ENRICHMENT_PILOT_DLP_INCOMPLETE")
        approved.append(HoldoutPilotItem(opaque_example_id=example_id, projection=projection))
    preflight = HoldoutPilotPreflight(
        enrichment_version=version_input.enrichment_version,
        holdout_count=len(split.holdout_ids),
        approved_count=len(approved),
    )
    return preflight, tuple(approved)


def run_private_holdout_pilot(
    *,
    labels_path: Path,
    annotation_queue_path: Path,
    split_seed: str,
    predictions_path: Path,
) -> HoldoutPilotRun:
    """Call OpenRouter for a preflight-approved maximum 40-item blind holdout."""

    if predictions_path.exists():
        raise HoldoutPilotError("AI_ENRICHMENT_PILOT_OUTPUT_EXISTS")
    settings = load_settings()
    version_input = EnrichmentVersionInput(
        model_slug=settings.openrouter.enrichment_model,
        provider_policy_version="openrouter-data-collection-deny-v1",
        prompt_version=PORTUGUESE_ENRICHMENT_PROMPT_VERSION,
    )
    preflight, items = preflight_private_holdout(
        labels_path=labels_path,
        annotation_queue_path=annotation_queue_path,
        split_seed=split_seed,
        version_input=version_input,
    )
    if preflight.holdout_count != 40 or preflight.approved_count != preflight.holdout_count:
        raise HoldoutPilotError("AI_ENRICHMENT_PILOT_SCOPE_INVALID")

    pricing = EnrichmentPricing(
        prompt_usd_per_token=_PROMPT_PRICE_USD,
        completion_usd_per_token=_COMPLETION_PRICE_USD,
    )
    budget = EnrichmentBudget(
        hard_budget_usd=Decimal(str(settings.openrouter.hard_budget_usd)),
        daily_warning_usd=Decimal(str(settings.openrouter.daily_warning_usd)),
        ledger_path=project_root() / "runtime_state" / "ai_enrichment_budget.json",
    )
    estimate = estimate_tokens_from_char_count(
        approved_text_characters=MAX_REVIEW_TEXT_CHARACTERS,
        max_completion_tokens=_MAX_COMPLETION_TOKENS,
        control_overhead_tokens=_CONTROL_OVERHEAD_TOKENS,
    )
    client = OpenRouterClient.from_config(settings.openrouter)
    predictions: list[dict[str, object]] = []
    try:
        transport = BudgetGuardedEnrichmentTransport(
            delegate=RateLimitedOpenRouterEnrichmentTransport(
                client=client,
                limiter=EnrichmentRateLimiter(max_requests=2, monotonic=time.monotonic),
                max_tokens=_MAX_COMPLETION_TOKENS,
            ),
            budget=budget,
            pricing=pricing,
            estimate=estimate,
        )
        executor = _batch_executor()
        for item in items:
            execution = executor.execute(
                work=EnrichmentWork(
                    work_id=item.opaque_example_id,
                    prompt=build_portuguese_enrichment_prompt(
                        projection=item.projection,
                        version_input=version_input,
                    ),
                    version_input=version_input,
                ),
                transport=transport,
            )
            if execution.state is not EnrichmentWorkState.SUCCEEDED or execution.result is None:
                raise HoldoutPilotError(
                    execution.sanitized_error_code or "AI_ENRICHMENT_PILOT_DISPATCH_INCOMPLETE"
                )
            predictions.append(
                {
                    "opaque_example_id": item.opaque_example_id,
                    **execution.result.model_dump(mode="json"),
                }
            )
    finally:
        client.close()
    _write_private_jsonl(predictions_path, predictions)
    return HoldoutPilotRun(
        enrichment_version=preflight.enrichment_version,
        prediction_count=len(predictions),
    )


def run_private_holdout_diagnostic(
    *,
    labels_path: Path,
    annotation_queue_path: Path,
    split_seed: str,
) -> None:
    """Dispatch exactly one DLP-approved holdout item without persisting output."""

    settings = load_settings()
    version_input = EnrichmentVersionInput(
        model_slug=settings.openrouter.enrichment_model,
        provider_policy_version="openrouter-data-collection-deny-v1",
        prompt_version=PORTUGUESE_ENRICHMENT_PROMPT_VERSION,
    )
    preflight, items = preflight_private_holdout(
        labels_path=labels_path,
        annotation_queue_path=annotation_queue_path,
        split_seed=split_seed,
        version_input=version_input,
    )
    if preflight.holdout_count != 40 or preflight.approved_count != 40:
        raise HoldoutPilotError("AI_ENRICHMENT_PILOT_SCOPE_INVALID")
    pricing = EnrichmentPricing(
        prompt_usd_per_token=_PROMPT_PRICE_USD,
        completion_usd_per_token=_COMPLETION_PRICE_USD,
    )
    budget = EnrichmentBudget(
        hard_budget_usd=Decimal(str(settings.openrouter.hard_budget_usd)),
        daily_warning_usd=Decimal(str(settings.openrouter.daily_warning_usd)),
        ledger_path=project_root() / "runtime_state" / "ai_enrichment_budget.json",
    )
    estimate = estimate_tokens_from_char_count(
        approved_text_characters=MAX_REVIEW_TEXT_CHARACTERS,
        max_completion_tokens=_MAX_COMPLETION_TOKENS,
        control_overhead_tokens=_CONTROL_OVERHEAD_TOKENS,
    )
    client = OpenRouterClient.from_config(settings.openrouter)
    try:
        item = items[0]
        execution = InMemoryEnrichmentExecutor(max_attempts=1).execute(
            work=EnrichmentWork(
                work_id=item.opaque_example_id,
                prompt=build_portuguese_enrichment_prompt(
                    projection=item.projection,
                    version_input=version_input,
                ),
                version_input=version_input,
            ),
            transport=BudgetGuardedEnrichmentTransport(
                delegate=RateLimitedOpenRouterEnrichmentTransport(
                    client=client,
                    limiter=EnrichmentRateLimiter(max_requests=1, monotonic=time.monotonic),
                    max_tokens=_MAX_COMPLETION_TOKENS,
                ),
                budget=budget,
                pricing=pricing,
                estimate=estimate,
            ),
        )
    finally:
        client.close()
    if execution.state is not EnrichmentWorkState.SUCCEEDED or execution.result is None:
        raise HoldoutPilotError(
            execution.sanitized_error_code or "AI_ENRICHMENT_PILOT_DIAGNOSTIC_INCOMPLETE"
        )


def _batch_executor() -> InMemoryEnrichmentExecutor:
    """Create the single-repair executor used only by an approved full batch."""

    return InMemoryEnrichmentExecutor(max_attempts=_MAX_PILOT_ATTEMPTS)


def main(argv: Sequence[str] | None = None) -> int:
    """Run aggregate-safe preflight or the explicitly authorized private pilot."""

    parser = argparse.ArgumentParser(description="ReviewLens private M4 blind-holdout pilot")
    commands = parser.add_subparsers(dest="command", required=True)
    for command in (
        commands.add_parser("preflight"),
        commands.add_parser("diagnose"),
        commands.add_parser("run"),
    ):
        command.add_argument("--labels-path", type=Path, required=True)
        command.add_argument("--annotation-queue-path", type=Path, required=True)
        command.add_argument("--split-seed", required=True)
    run = commands.choices["run"]
    run.add_argument("--predictions-path", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "preflight":
            settings = load_settings()
            version_input = EnrichmentVersionInput(
                model_slug=settings.openrouter.enrichment_model,
                provider_policy_version="openrouter-data-collection-deny-v1",
                prompt_version=PORTUGUESE_ENRICHMENT_PROMPT_VERSION,
            )
            preflight_result, _ = preflight_private_holdout(
                labels_path=args.labels_path,
                annotation_queue_path=args.annotation_queue_path,
                split_seed=args.split_seed,
                version_input=version_input,
            )
            print(
                json.dumps(
                    {
                        "approved_count": preflight_result.approved_count,
                        "holdout_count": preflight_result.holdout_count,
                        "status": "ready_for_authorized_private_pilot",
                    },
                    sort_keys=True,
                )
            )
            return 0
        if args.command == "diagnose":
            run_private_holdout_diagnostic(
                labels_path=args.labels_path,
                annotation_queue_path=args.annotation_queue_path,
                split_seed=args.split_seed,
            )
            print(json.dumps({"status": "private_diagnostic_succeeded"}, sort_keys=True))
            return 0
        pilot_result = run_private_holdout_pilot(
            labels_path=args.labels_path,
            annotation_queue_path=args.annotation_queue_path,
            split_seed=args.split_seed,
            predictions_path=args.predictions_path,
        )
        print(
            json.dumps(
                {
                    "enrichment_version": pilot_result.enrichment_version,
                    "prediction_count": pilot_result.prediction_count,
                    "status": "private_pilot_complete",
                },
                sort_keys=True,
            )
        )
        return 0
    except (GoldenAnnotationPackError, HoldoutPilotError) as error:
        parser.error(str(error))
    return 2


def _load_private_queue(path: Path) -> dict[str, tuple[str, str]]:
    queue: dict[str, tuple[str, str]] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise HoldoutPilotError("AI_ENRICHMENT_PILOT_QUEUE_UNAVAILABLE") from error
    for line in lines:
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            raise HoldoutPilotError("AI_ENRICHMENT_PILOT_QUEUE_INVALID") from error
        if not isinstance(record, dict):
            raise HoldoutPilotError("AI_ENRICHMENT_PILOT_QUEUE_INVALID")
        example_id = record.get("opaque_example_id")
        source_hash = record.get("source_record_hash")
        review_text = record.get("review_text")
        if (
            not isinstance(example_id, str)
            or not _is_hash(example_id)
            or not isinstance(source_hash, str)
            or not _is_hash(source_hash)
            or not isinstance(review_text, str)
            or not review_text.strip()
            or example_id in queue
        ):
            raise HoldoutPilotError("AI_ENRICHMENT_PILOT_QUEUE_INVALID")
        queue[example_id] = (source_hash, review_text)
    return queue


def _write_private_jsonl(path: Path, records: Iterable[dict[str, object]]) -> None:
    try:
        with path.open("x", encoding="utf-8", newline="") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    except OSError as error:
        raise HoldoutPilotError("AI_ENRICHMENT_PILOT_OUTPUT_UNAVAILABLE") from error


def _is_hash(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )
