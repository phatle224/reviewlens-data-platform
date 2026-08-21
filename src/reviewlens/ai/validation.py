"""Fail-closed JSON Schema and semantic validation for enrichment output."""

from __future__ import annotations

import json
import re
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from reviewlens.ai.enrichment import ASPECTS, SENTIMENTS, TOPICS

_RESTRICTED_OUTPUT = re.compile(
    r"(?:\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b|\bhttps?://|"
    r"\b(?:order|customer|seller)[ _-]?id\s*[:=])",
    re.IGNORECASE,
)


class EnrichmentValidationError(ValueError):
    """Stable error that intentionally excludes the response body."""

    code = "AI_ENRICHMENT_RESPONSE_INVALID"

    def __init__(self) -> None:
        super().__init__(self.code)


class AspectSentiment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    aspect: str
    sentiment: str
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_taxonomy(self) -> Self:
        if self.aspect not in ASPECTS or self.sentiment not in SENTIMENTS:
            raise ValueError("unsupported enrichment taxonomy value")
        return self


class ValidatedEnrichment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sentiment: str
    confidence: float = Field(ge=0, le=1)
    aspect_sentiments: tuple[AspectSentiment, ...] = Field(max_length=len(ASPECTS))
    topics: tuple[str, ...] = Field(max_length=len(TOPICS))
    summary: str = Field(min_length=1, max_length=500)
    highlights: tuple[str, ...] = Field(max_length=5)

    @model_validator(mode="after")
    def validate_semantics(self) -> Self:
        if self.sentiment not in SENTIMENTS or any(topic not in TOPICS for topic in self.topics):
            raise ValueError("unsupported enrichment taxonomy value")
        if len({item.aspect for item in self.aspect_sentiments}) != len(self.aspect_sentiments):
            raise ValueError("duplicate aspect")
        if len(set(self.topics)) != len(self.topics):
            raise ValueError("duplicate topic")
        text_fields = (self.summary, *self.highlights)
        if any(not value.strip() or _RESTRICTED_OUTPUT.search(value) for value in text_fields):
            raise ValueError("unsafe output text")
        return self


def validate_enrichment_response(payload: str) -> ValidatedEnrichment:
    """Parse exactly one schema-conforming response without retaining malformed text."""

    try:
        parsed = json.loads(payload)
        if not isinstance(parsed, dict):
            raise ValueError
        return ValidatedEnrichment.model_validate(parsed)
    except (TypeError, ValueError, ValidationError, json.JSONDecodeError):
        raise EnrichmentValidationError() from None
