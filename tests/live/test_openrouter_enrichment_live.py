"""Opt-in synthetic-only smoke for M4 structured enrichment; it can incur token cost."""

from __future__ import annotations

import os
import time

import pytest

from reviewlens.ai.enrichment import EnrichmentVersionInput, project_review_for_ai
from reviewlens.ai.execution import (
    EnrichmentWork,
    EnrichmentWorkState,
    InMemoryEnrichmentExecutor,
    RateLimitedOpenRouterEnrichmentTransport,
)
from reviewlens.ai.prompt import build_portuguese_enrichment_prompt
from reviewlens.ai.rate_limit import EnrichmentRateLimiter
from reviewlens.config import load_settings
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
    version = EnrichmentVersionInput(
        model_slug=settings.openrouter.enrichment_model,
        provider_policy_version="openrouter-data-collection-deny-v1",
        prompt_version="pt-br-enrichment-untrusted-evidence-v1",
    )
    projection = project_review_for_ai(
        source_record_hash="f" * 64,
        review_title="Teste sintético",
        review_comment="A entrega foi rápida e o produto chegou em boas condições.",
    )
    client = OpenRouterClient.from_config(settings.openrouter)
    try:
        result = InMemoryEnrichmentExecutor(max_attempts=1).execute(
            work=EnrichmentWork(
                work_id="e" * 64,
                prompt=build_portuguese_enrichment_prompt(
                    projection=projection,
                    version_input=version,
                ),
                version_input=version,
            ),
            transport=RateLimitedOpenRouterEnrichmentTransport(
                client=client,
                limiter=EnrichmentRateLimiter(max_requests=1, monotonic=time.monotonic),
                max_tokens=200,
            ),
        )
    finally:
        client.close()

    assert result.state is EnrichmentWorkState.SUCCEEDED
    assert result.attempt_count == 1
    assert result.result is not None
