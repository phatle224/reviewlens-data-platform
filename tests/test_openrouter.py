from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from reviewlens.config import load_settings
from reviewlens.providers.openrouter import (
    AIDataClass,
    ApprovedAIText,
    ChatMessage,
    ChatRole,
    OpenRouterClient,
    OpenRouterProviderError,
    OpenRouterTask,
)


def _client(
    handler: httpx.MockTransport,
    *,
    tmp_path: Path,
    api_key: str = "seeded-openrouter-secret",
) -> OpenRouterClient:
    config = load_settings(environ={}, env_file=tmp_path / ".env").openrouter
    return OpenRouterClient(config, api_key=api_key, http_client=httpx.Client(transport=handler))


def test_openrouter_chat_uses_pinned_model_privacy_route_and_approved_text(
    tmp_path: Path,
) -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers["authorization"]
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "provider-resolved-model",
                "choices": [{"message": {"content": '{"sentiment":"positive"}'}}],
                "usage": {"prompt_tokens": 8, "completion_tokens": 4, "total_tokens": 12},
            },
        )

    client = _client(httpx.MockTransport(handler), tmp_path=tmp_path)
    result = client.chat_completion(
        task=OpenRouterTask.ENRICHMENT,
        messages=(
            ChatMessage(ChatRole.SYSTEM, ApprovedAIText.internal_control("Return JSON.")),
            ChatMessage(ChatRole.USER, ApprovedAIText.synthetic("Synthetic review text.")),
        ),
        max_tokens=128,
    )
    config = load_settings(environ={}, env_file=tmp_path / ".env").openrouter

    assert captured["url"] == f"{config.base_url}/chat/completions"
    assert captured["authorization"] == "Bearer seeded-openrouter-secret"
    assert captured["payload"] == {
        "model": config.enrichment_model,
        "messages": [
            {"role": "system", "content": "Return JSON."},
            {"role": "user", "content": "Synthetic review text."},
        ],
        "max_tokens": 128,
        "temperature": 0,
        "stream": False,
        "provider": {"data_collection": "deny", "allow_fallbacks": False},
    }
    assert result.content == '{"sentiment":"positive"}'
    assert result.model == "provider-resolved-model"
    assert result.usage.total_tokens == 12
    client.close()


def test_openrouter_embeddings_are_ordered_and_never_embed_control_text(tmp_path: Path) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        payload = json.loads(request.content)
        assert payload["input"] == ["synthetic-a", "synthetic-b"]
        assert payload["provider"]["data_collection"] == "deny"
        return httpx.Response(
            200,
            json={
                "model": "resolved-embedding-model",
                "data": [
                    {"index": 1, "embedding": [0.3, 0.4]},
                    {"index": 0, "embedding": [0.1, 0.2]},
                ],
                "usage": {"prompt_tokens": 2, "total_tokens": 2},
            },
        )

    client = _client(httpx.MockTransport(handler), tmp_path=tmp_path)
    result = client.embed(
        (ApprovedAIText.synthetic("synthetic-a"), ApprovedAIText.synthetic("synthetic-b"))
    )
    assert result.embeddings == ((0.1, 0.2), (0.3, 0.4))
    assert result.usage.completion_tokens == 0

    with pytest.raises(ValueError, match="control text"):
        client.embed((ApprovedAIText.internal_control("do not index"),))
    assert calls == 1


def test_openrouter_rejects_restricted_or_unverified_text_before_http(tmp_path: Path) -> None:
    text = "restricted synthetic canary"
    digest = hashlib.sha256(text.encode()).hexdigest()

    with pytest.raises(ValueError, match="restricted text"):
        ApprovedAIText(text, AIDataClass.RESTRICTED, "dlp-v1", digest)
    with pytest.raises(ValueError, match="content hash"):
        ApprovedAIText.dlp_approved(
            text,
            policy_version="dlp-v1",
            content_sha256="0" * 64,
        )

    client = _client(
        httpx.MockTransport(lambda _request: pytest.fail("HTTP must not be called")),
        tmp_path=tmp_path,
    )
    with pytest.raises(ValueError, match="at least one"):
        client.chat_completion(task=OpenRouterTask.RAG, messages=(), max_tokens=1)
    with pytest.raises(ValueError, match="between 1 and 4096"):
        client.chat_completion(
            task=OpenRouterTask.TEXT_TO_SQL,
            messages=(ChatMessage(ChatRole.USER, ApprovedAIText.synthetic("question")),),
            max_tokens=0,
        )


@pytest.mark.parametrize("status_code", [401, 402, 429, 503])
def test_openrouter_errors_are_sanitized(
    status_code: int,
    tmp_path: Path,
) -> None:
    seeded_response = "seeded-provider-body-secret"
    client = _client(
        httpx.MockTransport(lambda _request: httpx.Response(status_code, text=seeded_response)),
        tmp_path=tmp_path,
    )

    with pytest.raises(OpenRouterProviderError) as captured:
        client.embed((ApprovedAIText.synthetic("seeded-prompt-secret"),))

    message = str(captured.value)
    assert message == "OpenRouter embedding failed"
    assert captured.value.status_code == status_code
    assert seeded_response not in message
    assert "seeded-prompt-secret" not in message
    assert "seeded-openrouter-secret" not in message


def test_openrouter_invalid_response_is_sanitized(tmp_path: Path) -> None:
    client = _client(
        httpx.MockTransport(lambda _request: httpx.Response(200, json={"secret": "value"})),
        tmp_path=tmp_path,
    )
    with pytest.raises(OpenRouterProviderError, match="response was invalid"):
        client.chat_completion(
            task=OpenRouterTask.RAG,
            messages=(ChatMessage(ChatRole.USER, ApprovedAIText.synthetic("question")),),
            max_tokens=32,
        )
    with pytest.raises(OpenRouterProviderError, match="response was invalid"):
        client.embed((ApprovedAIText.synthetic("question"),))


def test_openrouter_rejects_embedded_provider_error_and_untrusted_base_url(
    tmp_path: Path,
) -> None:
    client = _client(
        httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={
                    "model": "resolved-model",
                    "choices": [
                        {
                            "message": {"content": "partial seeded response"},
                            "finish_reason": "error",
                            "error": {"message": "seeded upstream secret"},
                        }
                    ],
                },
            )
        ),
        tmp_path=tmp_path,
    )
    with pytest.raises(OpenRouterProviderError) as captured:
        client.chat_completion(
            task=OpenRouterTask.RAG,
            messages=(ChatMessage(ChatRole.USER, ApprovedAIText.synthetic("question")),),
            max_tokens=32,
        )
    assert str(captured.value) == "OpenRouter chat completion failed"
    assert "seeded" not in str(captured.value)

    config = load_settings(environ={}, env_file=tmp_path / ".env").openrouter.model_copy(
        update={"base_url": "https://attacker.invalid/api/v1"}
    )
    with pytest.raises(ValueError, match="OpenRouter base URL"):
        OpenRouterClient(
            config,
            api_key="seeded-openrouter-secret",
            http_client=httpx.Client(
                transport=httpx.MockTransport(lambda _request: httpx.Response(200))
            ),
        )
