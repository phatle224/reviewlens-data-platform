"""Typed, privacy-gated OpenRouter chat and embedding adapter."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from reviewlens.config import OpenRouterConfig


class AIDataClass(StrEnum):
    INTERNAL_CONTROL = "internal_control"
    SYNTHETIC = "synthetic"
    DLP_APPROVED = "dlp_approved"
    RESTRICTED = "restricted"


@dataclass(frozen=True, slots=True)
class ApprovedAIText:
    """Text carrying the transfer decision required at the provider boundary."""

    text: str
    data_class: AIDataClass
    policy_version: str
    content_sha256: str

    def __post_init__(self) -> None:
        if not self.text:
            raise ValueError("AI text cannot be empty")
        if self.data_class is AIDataClass.RESTRICTED:
            raise ValueError("restricted text cannot cross the external AI boundary")
        if not self.policy_version:
            raise ValueError("AI text requires a policy version")
        actual_hash = hashlib.sha256(self.text.encode("utf-8")).hexdigest()
        if self.content_sha256 != actual_hash:
            raise ValueError("AI text content hash does not match the approved payload")

    @classmethod
    def internal_control(cls, text: str) -> ApprovedAIText:
        return cls._trusted(text, AIDataClass.INTERNAL_CONTROL, "internal-control-v1")

    @classmethod
    def synthetic(cls, text: str) -> ApprovedAIText:
        return cls._trusted(text, AIDataClass.SYNTHETIC, "synthetic-v1")

    @classmethod
    def dlp_approved(
        cls,
        text: str,
        *,
        policy_version: str,
        content_sha256: str,
    ) -> ApprovedAIText:
        return cls(text, AIDataClass.DLP_APPROVED, policy_version, content_sha256)

    @classmethod
    def _trusted(
        cls,
        text: str,
        data_class: AIDataClass,
        policy_version: str,
    ) -> ApprovedAIText:
        return cls(
            text=text,
            data_class=data_class,
            policy_version=policy_version,
            content_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        )


class ChatRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: ChatRole
    content: ApprovedAIText


class OpenRouterTask(StrEnum):
    ENRICHMENT = "enrichment"
    RAG = "rag"
    TEXT_TO_SQL = "text_to_sql"


@dataclass(frozen=True, slots=True)
class TokenUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass(frozen=True, slots=True)
class ChatCompletion:
    content: str
    model: str
    usage: TokenUsage


@dataclass(frozen=True, slots=True)
class EmbeddingBatch:
    embeddings: tuple[tuple[float, ...], ...]
    model: str
    usage: TokenUsage


class OpenRouterProviderError(RuntimeError):
    """Sanitized failure that excludes prompts, responses and credentials."""


class _UsagePayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)


class _MessagePayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    content: str = Field(min_length=1)


class _ChoicePayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    message: _MessagePayload
    finish_reason: str | None = None
    error: dict[str, object] | None = None


class _ChatPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    model: str
    choices: list[_ChoicePayload] = Field(min_length=1)
    usage: _UsagePayload = Field(default_factory=_UsagePayload)


class _EmbeddingItemPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    index: int = Field(ge=0)
    embedding: list[float] = Field(min_length=1)


class _EmbeddingPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    model: str
    data: list[_EmbeddingItemPayload] = Field(min_length=1)
    usage: _UsagePayload = Field(default_factory=_UsagePayload)


class OpenRouterClient:
    """Minimal OpenRouter boundary with pinned models and deny-collection routing."""

    def __init__(
        self,
        config: OpenRouterConfig,
        *,
        api_key: str,
        http_client: httpx.Client,
    ) -> None:
        if not api_key:
            raise ValueError("OpenRouter API key cannot be empty")
        parsed_url = urlparse(config.base_url)
        if (
            parsed_url.scheme != "https"
            or parsed_url.netloc != "openrouter.ai"
            or parsed_url.path.rstrip("/") != "/api/v1"
            or parsed_url.params
            or parsed_url.query
            or parsed_url.fragment
        ):
            raise ValueError("OpenRouter base URL must be https://openrouter.ai/api/v1")
        self._config = config
        self._client = http_client
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    @classmethod
    def from_config(cls, config: OpenRouterConfig) -> OpenRouterClient:
        config.require_live_credentials()
        if config.api_key is None:
            raise ValueError("OpenRouter API key is not configured")
        client = httpx.Client(timeout=httpx.Timeout(30.0, connect=10.0))
        return cls(
            config,
            api_key=config.api_key.get_secret_value(),
            http_client=client,
        )

    def close(self) -> None:
        self._client.close()

    def chat_completion(
        self,
        *,
        task: OpenRouterTask,
        messages: Sequence[ChatMessage],
        max_tokens: int,
    ) -> ChatCompletion:
        if not messages:
            raise ValueError("OpenRouter chat requires at least one approved message")
        if not 1 <= max_tokens <= 4096:
            raise ValueError("OpenRouter max_tokens must be between 1 and 4096")
        payload = {
            "model": self._model_for(task),
            "messages": [
                {"role": message.role.value, "content": message.content.text}
                for message in messages
            ],
            "max_tokens": max_tokens,
            "temperature": 0,
            "stream": False,
            "provider": {"data_collection": "deny", "allow_fallbacks": False},
        }
        response_data = self._post("chat/completions", payload, operation="chat completion")
        try:
            parsed = _ChatPayload.model_validate(response_data)
        except ValidationError:
            raise OpenRouterProviderError("OpenRouter chat response was invalid") from None
        choice = parsed.choices[0]
        if choice.error is not None or choice.finish_reason == "error":
            raise OpenRouterProviderError("OpenRouter chat completion failed")
        usage = self._usage(parsed.usage)
        return ChatCompletion(choice.message.content, parsed.model, usage)

    def embed(self, texts: Sequence[ApprovedAIText]) -> EmbeddingBatch:
        if not texts:
            raise ValueError("OpenRouter embedding requires at least one approved text")
        if any(text.data_class is AIDataClass.INTERNAL_CONTROL for text in texts):
            raise ValueError("internal control text cannot be embedded as evidence")
        payload = {
            "model": self._config.embedding_model,
            "input": [text.text for text in texts],
            "encoding_format": "float",
            "provider": {"data_collection": "deny", "allow_fallbacks": False},
        }
        response_data = self._post("embeddings", payload, operation="embedding")
        try:
            parsed = _EmbeddingPayload.model_validate(response_data)
            ordered = sorted(parsed.data, key=lambda item: item.index)
            if [item.index for item in ordered] != list(range(len(texts))):
                raise ValueError
            embeddings = tuple(tuple(item.embedding) for item in ordered)
        except (ValidationError, ValueError):
            raise OpenRouterProviderError("OpenRouter embedding response was invalid") from None
        return EmbeddingBatch(embeddings, parsed.model, self._usage(parsed.usage))

    def _model_for(self, task: OpenRouterTask) -> str:
        return {
            OpenRouterTask.ENRICHMENT: self._config.enrichment_model,
            OpenRouterTask.RAG: self._config.rag_model,
            OpenRouterTask.TEXT_TO_SQL: self._config.sql_model,
        }[task]

    def _post(self, path: str, payload: object, *, operation: str) -> object:
        url = f"{self._config.base_url.rstrip('/')}/{path}"
        try:
            response = self._client.post(url, headers=self._headers, json=payload)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError):
            raise OpenRouterProviderError(f"OpenRouter {operation} failed") from None

    @staticmethod
    def _usage(payload: _UsagePayload) -> TokenUsage:
        return TokenUsage(
            prompt_tokens=payload.prompt_tokens,
            completion_tokens=payload.completion_tokens,
            total_tokens=payload.total_tokens,
        )
