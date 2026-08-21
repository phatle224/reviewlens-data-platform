"""Bounded, resumable structured-enrichment execution using sanitized outcomes."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from reviewlens.ai.enrichment import EnrichmentVersionInput, enrichment_json_schema
from reviewlens.ai.prompt import EnrichmentPrompt, build_single_repair_prompt
from reviewlens.ai.rate_limit import EnrichmentRateLimiter
from reviewlens.ai.validation import (
    EnrichmentValidationError,
    ValidatedEnrichment,
    validate_enrichment_response,
)
from reviewlens.providers.openrouter import OpenRouterClient, OpenRouterProviderError


class EnrichmentWorkState(StrEnum):
    PENDING = "pending"
    RETRYABLE = "retryable"
    SUCCEEDED = "succeeded"
    QUARANTINED = "quarantined"


class EnrichmentTransportError(RuntimeError):
    def __init__(self, *, code: str, transient: bool) -> None:
        if not code or len(code) > 128:
            raise ValueError("provider error code must be sanitized")
        super().__init__(code)
        self.code = code
        self.transient = transient


class StructuredEnrichmentTransport(Protocol):
    def complete(self, *, prompt: EnrichmentPrompt, repair: bool) -> str: ...


class RateLimitedOpenRouterEnrichmentTransport:
    """Provider adapter that rate-limits before sending an approved prompt."""

    def __init__(
        self,
        *,
        client: OpenRouterClient,
        limiter: EnrichmentRateLimiter,
        max_tokens: int = 400,
    ) -> None:
        self._client = client
        self._limiter = limiter
        self._max_tokens = max_tokens

    def complete(self, *, prompt: EnrichmentPrompt, repair: bool) -> str:
        self._limiter.acquire()
        selected_prompt = build_single_repair_prompt(prompt) if repair else prompt
        try:
            completion = self._client.structured_enrichment_completion(
                messages=selected_prompt.messages,
                response_schema=structured_output_schema(),
                max_tokens=self._max_tokens,
            )
        except OpenRouterProviderError:
            raise EnrichmentTransportError(code="OPENROUTER_TRANSIENT", transient=True) from None
        return completion.content


@dataclass(frozen=True, slots=True)
class EnrichmentWork:
    work_id: str
    prompt: EnrichmentPrompt = field(repr=False)
    version_input: EnrichmentVersionInput


@dataclass(frozen=True, slots=True)
class EnrichmentExecution:
    work_id: str
    state: EnrichmentWorkState
    attempt_count: int
    repair_count: int
    sanitized_error_code: str | None = None
    result: ValidatedEnrichment | None = field(default=None, repr=False)


class InMemoryEnrichmentExecutor:
    """Records resumable state; malformed/provider payloads never leave this boundary."""

    def __init__(self, *, max_attempts: int = 3, max_repairs: int = 1) -> None:
        if max_attempts < 1 or max_repairs != 1:
            raise ValueError("execution requires positive attempts and exactly one repair path")
        self._max_attempts = max_attempts
        self._max_repairs = max_repairs
        self._executions: dict[str, EnrichmentExecution] = {}

    def execute(
        self, *, work: EnrichmentWork, transport: StructuredEnrichmentTransport
    ) -> EnrichmentExecution:
        prior = self._executions.get(work.work_id)
        if prior is not None and prior.state in {
            EnrichmentWorkState.SUCCEEDED,
            EnrichmentWorkState.QUARANTINED,
        }:
            return prior
        current = prior or EnrichmentExecution(
            work_id=work.work_id,
            state=EnrichmentWorkState.PENDING,
            attempt_count=0,
            repair_count=0,
        )
        return self._attempt(work=work, transport=transport, current=current, repair=False)

    def _attempt(
        self,
        *,
        work: EnrichmentWork,
        transport: StructuredEnrichmentTransport,
        current: EnrichmentExecution,
        repair: bool,
    ) -> EnrichmentExecution:
        try:
            response = transport.complete(prompt=work.prompt, repair=repair)
            result = validate_enrichment_response(response)
        except EnrichmentValidationError:
            attempted = current.attempt_count + 1
            if (
                not repair
                and current.repair_count < self._max_repairs
                and attempted < self._max_attempts
            ):
                repaired = EnrichmentExecution(
                    work_id=work.work_id,
                    state=EnrichmentWorkState.PENDING,
                    attempt_count=attempted,
                    repair_count=current.repair_count + 1,
                )
                return self._attempt(work=work, transport=transport, current=repaired, repair=True)
            return self._store(
                EnrichmentExecution(
                    work_id=work.work_id,
                    state=EnrichmentWorkState.QUARANTINED,
                    attempt_count=attempted,
                    repair_count=current.repair_count,
                    sanitized_error_code="AI_ENRICHMENT_SCHEMA_INVALID",
                )
            )
        except EnrichmentTransportError as error:
            attempted = current.attempt_count + 1
            if error.transient and attempted < self._max_attempts:
                return self._store(
                    EnrichmentExecution(
                        work_id=work.work_id,
                        state=EnrichmentWorkState.RETRYABLE,
                        attempt_count=attempted,
                        repair_count=current.repair_count,
                        sanitized_error_code=error.code,
                    )
                )
            return self._store(
                EnrichmentExecution(
                    work_id=work.work_id,
                    state=EnrichmentWorkState.QUARANTINED,
                    attempt_count=attempted,
                    repair_count=current.repair_count,
                    sanitized_error_code=error.code,
                )
            )
        return self._store(
            EnrichmentExecution(
                work_id=work.work_id,
                state=EnrichmentWorkState.SUCCEEDED,
                attempt_count=current.attempt_count + 1,
                repair_count=current.repair_count,
                result=result,
            )
        )

    def _store(self, execution: EnrichmentExecution) -> EnrichmentExecution:
        self._executions[execution.work_id] = execution
        return execution


def structured_output_schema() -> dict[str, object]:
    """Return the exact frozen schema at the provider boundary."""

    return dict(enrichment_json_schema())
