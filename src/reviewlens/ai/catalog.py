"""Read-only OpenRouter model catalog snapshot for the enrichment release gate."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlparse

import httpx

from reviewlens.config import OpenRouterConfig

ENRICHMENT_PROVIDER_POLICY_VERSION = "openrouter-data-collection-deny-v1"


class OpenRouterCatalogError(RuntimeError):
    """Sanitized catalog failure that never includes provider response content."""


@dataclass(frozen=True, slots=True)
class EnrichmentModelCatalogSnapshot:
    captured_at: str
    model_slug: str
    context_length: int
    prompt_usd_per_token: Decimal
    completion_usd_per_token: Decimal
    supports_structured_outputs: bool
    provider_policy_version: str = ENRICHMENT_PROVIDER_POLICY_VERSION

    def to_public_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["prompt_usd_per_token"] = format(self.prompt_usd_per_token, "f")
        payload["completion_usd_per_token"] = format(self.completion_usd_per_token, "f")
        return payload


class OpenRouterCatalogClient:
    """Public metadata client: no API key, prompt, review or completion is sent."""

    def __init__(self, config: OpenRouterConfig, *, http_client: httpx.Client) -> None:
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

    @classmethod
    def from_config(cls, config: OpenRouterConfig) -> OpenRouterCatalogClient:
        return cls(config, http_client=httpx.Client(timeout=httpx.Timeout(30.0, connect=10.0)))

    def close(self) -> None:
        self._client.close()

    def snapshot_enrichment_model(
        self, *, captured_at: datetime | None = None
    ) -> EnrichmentModelCatalogSnapshot:
        try:
            response = self._client.get(f"{self._config.base_url.rstrip('/')}/models")
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            raise OpenRouterCatalogError("OpenRouter catalog request failed") from None
        try:
            models = payload["data"]
            model = next(item for item in models if item["id"] == self._config.enrichment_model)
            pricing = model["pricing"]
            parameters = set(model.get("supported_parameters", []))
            snapshot = EnrichmentModelCatalogSnapshot(
                captured_at=(captured_at or datetime.now(UTC)).isoformat().replace("+00:00", "Z"),
                model_slug=model["id"],
                context_length=_positive_int(model["context_length"]),
                prompt_usd_per_token=_price(pricing["prompt"]),
                completion_usd_per_token=_price(pricing["completion"]),
                supports_structured_outputs=(
                    "structured_outputs" in parameters and "response_format" in parameters
                ),
            )
        except (KeyError, StopIteration, TypeError, ValueError, InvalidOperation):
            raise OpenRouterCatalogError(
                "OpenRouter enrichment catalog contract was invalid"
            ) from None
        if not snapshot.supports_structured_outputs:
            raise OpenRouterCatalogError(
                "OpenRouter enrichment model lacks structured-output support"
            )
        return snapshot

    @staticmethod
    def write_public_snapshot(snapshot: EnrichmentModelCatalogSnapshot, path: Path) -> None:
        """Write safe catalog metadata only; caller controls an explicitly reviewed path."""

        import json

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(snapshot.to_public_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def _positive_int(value: object) -> int:
    if not isinstance(value, int) or value < 1:
        raise ValueError
    return value


def _price(value: object) -> Decimal:
    if not isinstance(value, str):
        raise ValueError
    price = Decimal(value)
    if not price.is_finite() or price < 0:
        raise ValueError
    return price
