"""Opt-in synthetic-only smoke for M4 structured enrichment; it can incur token cost."""

from __future__ import annotations

import os
import time
from decimal import Decimal
from pathlib import Path

import pytest

from reviewlens.ai.budget import (
    EnrichmentBudget,
    EnrichmentPricing,
    estimate_tokens_from_char_count,
)
from reviewlens.ai.enrichment import (
    MAX_REVIEW_TEXT_CHARACTERS,
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
from reviewlens.ai.prompt import (
    PORTUGUESE_ENRICHMENT_PROMPT_VERSION,
    build_portuguese_enrichment_prompt,
)
from reviewlens.ai.rate_limit import EnrichmentRateLimiter
from reviewlens.config import load_settings, project_root
from reviewlens.providers.openrouter import OpenRouterClient

pytestmark = pytest.mark.live


@pytest.mark.skipif(
    os.getenv("REVIEWLENS_RUN_LIVE_OPENROUTER_ENRICHMENT") != "1",
    reason=(
        "set REVIEWLENS_RUN_LIVE_OPENROUTER_ENRICHMENT=1 for synthetic structured enrichment smoke"
    ),
)
def test_synthetic_structured_enrichment_smoke() -> None:
    settings = load_settings()
    # Pinned to the safe public catalog snapshot captured on 2026-08-21.  This
    # guard is intentionally conservative: 2,000 approved evidence characters,
    # 1,000 control/schema tokens and the provider's 256-token response limit.
    pricing = EnrichmentPricing(
        prompt_usd_per_token=Decimal("0.0000001"),
        completion_usd_per_token=Decimal("0.0000004"),
    )
    budget = EnrichmentBudget(
        hard_budget_usd=Decimal(str(settings.openrouter.hard_budget_usd)),
        daily_warning_usd=Decimal(str(settings.openrouter.daily_warning_usd)),
        ledger_path=project_root() / Path("runtime_state") / "ai_enrichment_budget.json",
    )
    version = EnrichmentVersionInput(
        model_slug=settings.openrouter.enrichment_model,
        provider_policy_version="openrouter-data-collection-deny-v1",
        prompt_version=PORTUGUESE_ENRICHMENT_PROMPT_VERSION,
    )
    projection = project_review_for_ai(
        source_record_hash="f" * 64,
        review_title="Teste sintético",
        review_comment="A entrega foi rápida e o produto chegou em boas condições.",
    )
    client = OpenRouterClient.from_config(settings.openrouter)
    try:
        result = InMemoryEnrichmentExecutor(max_attempts=2).execute(
            work=EnrichmentWork(
                work_id="e" * 64,
                prompt=build_portuguese_enrichment_prompt(
                    projection=projection,
                    version_input=version,
                ),
                version_input=version,
            ),
            transport=BudgetGuardedEnrichmentTransport(
                delegate=RateLimitedOpenRouterEnrichmentTransport(
                    client=client,
                    limiter=EnrichmentRateLimiter(max_requests=1, monotonic=time.monotonic),
                    max_tokens=256,
                ),
                budget=budget,
                pricing=pricing,
                estimate=estimate_tokens_from_char_count(
                    approved_text_characters=MAX_REVIEW_TEXT_CHARACTERS,
                    max_completion_tokens=256,
                    control_overhead_tokens=1_000,
                ),
            ),
        )
    finally:
        client.close()

    assert result.state is EnrichmentWorkState.SUCCEEDED
    assert 1 <= result.attempt_count <= 2
    assert result.result is not None
