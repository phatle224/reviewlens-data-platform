from __future__ import annotations

import json
from collections import deque
from pathlib import Path

import httpx
import pytest

from reviewlens.ai.enrichment import (
    EnrichmentVersionInput,
    enrichment_json_schema,
    project_review_for_ai,
)
from reviewlens.ai.execution import (
    EnrichmentTransportError,
    EnrichmentWork,
    EnrichmentWorkState,
    InMemoryEnrichmentExecutor,
    RateLimitedOpenRouterEnrichmentTransport,
)
from reviewlens.ai.prompt import (
    PORTUGUESE_ENRICHMENT_PROMPT_VERSION,
    build_portuguese_enrichment_prompt,
)
from reviewlens.ai.rate_limit import EnrichmentRateLimiter, EnrichmentRateLimitExceeded
from reviewlens.ai.validation import EnrichmentValidationError, validate_enrichment_response
from reviewlens.config import load_settings
from reviewlens.providers.openrouter import OpenRouterClient


def _valid_response(**changes: object) -> str:
    payload: dict[str, object] = {
        "sentiment": "positive",
        "confidence": 0.9,
        "aspect_sentiments": [{"aspect": "delivery", "sentiment": "positive", "confidence": 0.8}],
        "topics": ["delivery_speed"],
        "summary": "Entrega rápida e produto conforme esperado.",
        "highlights": ["Entrega rápida."],
    }
    payload.update(changes)
    return json.dumps(payload)


def _work() -> EnrichmentWork:
    version = EnrichmentVersionInput(
        model_slug="google/gemini-2.5-flash-lite",
        provider_policy_version="openrouter-data-collection-deny-v1",
        prompt_version=PORTUGUESE_ENRICHMENT_PROMPT_VERSION,
    )
    projection = project_review_for_ai(
        source_record_hash="a" * 64,
        review_title="Muito bom",
        review_comment="Entrega rápida e produto correto.",
    )
    return EnrichmentWork(
        work_id="b" * 64,
        prompt=build_portuguese_enrichment_prompt(projection=projection, version_input=version),
        version_input=version,
    )


class ScriptedTransport:
    def __init__(self, outcomes: list[str | EnrichmentTransportError]) -> None:
        self._outcomes: deque[str | EnrichmentTransportError] = deque(outcomes)
        self.repairs: list[bool] = []

    def complete(self, *, prompt: object, repair: bool) -> str:
        del prompt
        self.repairs.append(repair)
        outcome = self._outcomes.popleft()
        if isinstance(outcome, EnrichmentTransportError):
            raise outcome
        return outcome


def test_m4_structured_openrouter_payload_is_pinned_private_and_schema_bound(
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "google/gemini-2.5-flash-lite",
                "choices": [{"message": {"content": _valid_response()}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
            },
        )

    config = load_settings(environ={}, env_file=tmp_path / ".env").openrouter
    client = OpenRouterClient(
        config,
        api_key="synthetic-openrouter-key",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    clock = [0.0]
    transport = RateLimitedOpenRouterEnrichmentTransport(
        client=client,
        limiter=EnrichmentRateLimiter(monotonic=lambda: clock[0]),
    )

    result = transport.complete(prompt=_work().prompt, repair=False)
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert result == _valid_response()
    assert payload["model"] == config.enrichment_model
    assert payload["provider"] == {"data_collection": "deny", "allow_fallbacks": False}
    assert payload["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": "reviewlens_enrichment_v1",
            "strict": True,
            "schema": dict(enrichment_json_schema()),
        },
    }
    client.close()


def test_m4_rate_limiter_blocks_before_a_third_provider_dispatch() -> None:
    now = [0.0]
    limiter = EnrichmentRateLimiter(monotonic=lambda: now[0])
    limiter.acquire()
    limiter.acquire()
    with pytest.raises(EnrichmentRateLimitExceeded, match="AI_ENRICHMENT_RATE_LIMITED"):
        limiter.acquire()
    now[0] = 1.0
    limiter.acquire()


@pytest.mark.parametrize(
    "invalid",
    [
        "not-json",
        _valid_response(sentiment="unknown"),
        _valid_response(topics=["delivery_speed", "delivery_speed"]),
        _valid_response(summary="contact person@example.com"),
        _valid_response(
            aspect_sentiments=[
                {"aspect": "delivery", "sentiment": "positive", "confidence": 0.8},
                {"aspect": "delivery", "sentiment": "neutral", "confidence": 0.5},
            ]
        ),
    ],
)
def test_m4_validation_rejects_invalid_semantic_or_restricted_output_without_echo(
    invalid: str,
) -> None:
    with pytest.raises(EnrichmentValidationError) as captured:
        validate_enrichment_response(invalid)
    assert str(captured.value) == "AI_ENRICHMENT_RESPONSE_INVALID"
    assert invalid not in str(captured.value)


def test_m4_executor_uses_exactly_one_repair_and_then_commits_validated_result() -> None:
    transport = ScriptedTransport(["not-json", _valid_response()])
    executor = InMemoryEnrichmentExecutor()

    result = executor.execute(work=_work(), transport=transport)

    assert result.state is EnrichmentWorkState.SUCCEEDED
    assert result.attempt_count == 2
    assert result.repair_count == 1
    assert result.result is not None
    assert transport.repairs == [False, True]
    assert executor.execute(work=_work(), transport=transport) is result


def test_m4_executor_quarantines_invalid_repair_and_permanent_provider_error() -> None:
    invalid_transport = ScriptedTransport(["not-json", "still-not-json"])
    permanent_transport = ScriptedTransport(
        [EnrichmentTransportError(code="OPENROUTER_400", transient=False)]
    )

    invalid = InMemoryEnrichmentExecutor().execute(work=_work(), transport=invalid_transport)
    permanent = InMemoryEnrichmentExecutor().execute(work=_work(), transport=permanent_transport)

    assert invalid.state is EnrichmentWorkState.QUARANTINED
    assert invalid.sanitized_error_code == "AI_ENRICHMENT_SCHEMA_INVALID"
    assert invalid.attempt_count == 2
    assert permanent.state is EnrichmentWorkState.QUARANTINED
    assert permanent.sanitized_error_code == "OPENROUTER_400"


def test_m4_executor_resumes_transient_failure_with_bounded_attempts() -> None:
    executor = InMemoryEnrichmentExecutor(max_attempts=3)
    transport = ScriptedTransport(
        [
            EnrichmentTransportError(code="OPENROUTER_429", transient=True),
            _valid_response(),
        ]
    )
    first = executor.execute(work=_work(), transport=transport)
    resumed = executor.execute(work=_work(), transport=transport)

    assert first.state is EnrichmentWorkState.RETRYABLE
    assert first.attempt_count == 1
    assert resumed.state is EnrichmentWorkState.SUCCEEDED
    assert resumed.attempt_count == 2


def test_m4_executor_quarantines_after_bounded_transient_attempts() -> None:
    executor = InMemoryEnrichmentExecutor(max_attempts=2)
    transport = ScriptedTransport(
        [
            EnrichmentTransportError(code="OPENROUTER_503", transient=True),
            EnrichmentTransportError(code="OPENROUTER_503", transient=True),
        ]
    )
    assert (
        executor.execute(work=_work(), transport=transport).state is EnrichmentWorkState.RETRYABLE
    )
    terminal = executor.execute(work=_work(), transport=transport)
    assert terminal.state is EnrichmentWorkState.QUARANTINED
    assert terminal.attempt_count == 2
