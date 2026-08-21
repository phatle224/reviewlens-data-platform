"""Offline cost-control tests for the bounded M4 enrichment pilot."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from reviewlens.ai.budget import (
    EnrichmentBudget,
    EnrichmentBudgetExceeded,
    EnrichmentBudgetStatus,
    EnrichmentPricing,
    TokenEstimate,
    estimate_tokens_from_char_count,
)
from reviewlens.ai.execution import BudgetGuardedEnrichmentTransport
from reviewlens.ai.prompt import EnrichmentPrompt


def _pricing() -> EnrichmentPricing:
    return EnrichmentPricing(
        prompt_usd_per_token=Decimal("0.1"),
        completion_usd_per_token=Decimal("0.4"),
    )


def test_m4_token_estimator_is_deterministic_and_accounts_for_controls() -> None:
    estimate = estimate_tokens_from_char_count(
        approved_text_characters=17,
        max_completion_tokens=200,
        control_overhead_tokens=600,
    )

    assert estimate == TokenEstimate(prompt_tokens=605, completion_tokens=200)
    assert estimate.cost_usd(_pricing()) == Decimal("140.5")


def test_m4_budget_warns_at_daily_threshold_and_persists_actual_settlement(tmp_path: Path) -> None:
    ledger_path = tmp_path / "runtime_state" / "ai_enrichment_budget.json"
    budget = EnrichmentBudget(
        hard_budget_usd=Decimal("5.0"),
        daily_warning_usd=Decimal("0.5"),
        ledger_path=ledger_path,
    )
    pricing = EnrichmentPricing(Decimal("0.1"), Decimal("0.4"))
    estimate = TokenEstimate(prompt_tokens=1, completion_tokens=1)

    reservation = budget.reserve(estimate=estimate, pricing=pricing, on_day=date(2026, 8, 22))
    budget.commit(
        reservation,
        actual=TokenEstimate(prompt_tokens=1, completion_tokens=1),
        pricing=pricing,
    )

    assert reservation.status is EnrichmentBudgetStatus.WARNING
    assert EnrichmentBudget(
        hard_budget_usd=Decimal("5.0"),
        daily_warning_usd=Decimal("0.5"),
        ledger_path=ledger_path,
    ).committed_usd == Decimal("0.5")


def test_m4_budget_hard_stop_blocks_before_delegate_and_releases_failed_call() -> None:
    budget = EnrichmentBudget(
        hard_budget_usd=Decimal("5.0"),
        daily_warning_usd=Decimal("0.5"),
    )
    pricing = EnrichmentPricing(Decimal("1"), Decimal("0"))
    exact_cap = TokenEstimate(prompt_tokens=5, completion_tokens=0)
    first = budget.reserve(estimate=exact_cap, pricing=pricing, on_day=date(2026, 8, 22))
    budget.commit(first)
    with pytest.raises(EnrichmentBudgetExceeded, match="AI_ENRICHMENT_BUDGET_EXHAUSTED"):
        budget.reserve(
            estimate=TokenEstimate(prompt_tokens=1, completion_tokens=0),
            pricing=pricing,
            on_day=date(2026, 8, 22),
        )

    class FailingTransport:
        calls = 0

        def complete(self, *, prompt: EnrichmentPrompt, repair: bool) -> str:
            del prompt, repair
            self.calls += 1
            raise RuntimeError("synthetic provider failure")

    blocked_delegate = FailingTransport()
    blocked_guarded = BudgetGuardedEnrichmentTransport(
        delegate=blocked_delegate,
        budget=budget,
        pricing=pricing,
        estimate=TokenEstimate(prompt_tokens=1, completion_tokens=0),
        today=lambda: date(2026, 8, 22),
    )
    with pytest.raises(EnrichmentBudgetExceeded, match="AI_ENRICHMENT_BUDGET_EXHAUSTED"):
        blocked_guarded.complete(prompt=EnrichmentPrompt(version="test", messages=()), repair=False)
    assert blocked_delegate.calls == 0

    release_budget = EnrichmentBudget(
        hard_budget_usd=Decimal("1.0"),
        daily_warning_usd=Decimal("0.5"),
    )
    delegate = FailingTransport()
    guarded = BudgetGuardedEnrichmentTransport(
        delegate=delegate,
        budget=release_budget,
        pricing=pricing,
        estimate=TokenEstimate(prompt_tokens=1, completion_tokens=0),
        today=lambda: date(2026, 8, 22),
    )
    with pytest.raises(RuntimeError, match="synthetic provider failure"):
        guarded.complete(prompt=EnrichmentPrompt(version="test", messages=()), repair=False)

    assert delegate.calls == 1
    assert release_budget.reserved_usd == Decimal("0")
