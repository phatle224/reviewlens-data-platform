"""M4 offline contracts for structured review enrichment and DLP projection."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Final

from reviewlens.providers.openrouter import ApprovedAIText

ENRICHMENT_SCHEMA_VERSION: Final = "reviewlens-enrichment-schema-v1"
ENRICHMENT_TAXONOMY_VERSION: Final = "reviewlens-enrichment-taxonomy-v1"
DLP_POLICY_VERSION: Final = "reviewlens-dlp-minimization-v1"
MAX_REVIEW_TEXT_CHARACTERS: Final = 2_000

SENTIMENTS: Final = ("positive", "neutral", "negative", "mixed")
ASPECTS: Final = (
    "product_quality",
    "delivery",
    "packaging",
    "customer_service",
    "price_value",
    "product_description",
    "payment",
    "other",
)
TOPICS: Final = (
    "delivery_speed",
    "delivery_condition",
    "product_quality",
    "product_match",
    "packaging",
    "customer_service",
    "price_value",
    "payment_experience",
    "other",
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_VERSION = re.compile(r"^[a-z][a-z0-9.-]{2,127}$")
_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_URL = re.compile(r"\b(?:https?://|www\.)[^\s<>()]+", re.IGNORECASE)
_CPF = re.compile(r"\b\d{3}[.\s-]?\d{3}[.\s-]?\d{3}[-\s]?\d{2}\b")
_PHONE = re.compile(r"(?<!\d)(?:\+?55[\s.-]?)?(?:\(?\d{2}\)?[\s.-]?)?9?\d{4}[\s.-]?\d{4}(?!\d)")
_DIRECT_IDENTIFIER = re.compile(r"\b(?:order|customer|seller|review)[ _-]?id\s*[:=]", re.IGNORECASE)
_SECRET_LIKE = re.compile(
    r"\b(?:password|senha|api[ _-]?key|access[ _-]?token|private[ _-]?key)\b",
    re.IGNORECASE,
)


class DLPDecision(StrEnum):
    APPROVED = "approved"
    QUARANTINED = "quarantined"


class DLPReasonCode(StrEnum):
    EMPTY_TEXT = "DLP_EMPTY_TEXT"
    TEXT_TOO_LONG = "DLP_TEXT_TOO_LONG"
    DIRECT_IDENTIFIER = "DLP_DIRECT_IDENTIFIER"
    SECRET_LIKE = "DLP_SECRET_LIKE"  # noqa: S105 - sanitized classification code, never a secret


@dataclass(frozen=True, slots=True)
class EnrichmentVersionInput:
    model_slug: str
    provider_policy_version: str
    prompt_version: str
    schema_version: str = ENRICHMENT_SCHEMA_VERSION
    taxonomy_version: str = ENRICHMENT_TAXONOMY_VERSION

    def __post_init__(self) -> None:
        for name, value in (
            ("model_slug", self.model_slug),
            ("provider_policy_version", self.provider_policy_version),
            ("prompt_version", self.prompt_version),
            ("schema_version", self.schema_version),
            ("taxonomy_version", self.taxonomy_version),
        ):
            valid = _VERSION.fullmatch(value)
            if name == "model_slug":
                valid = re.fullmatch(r"^[a-z0-9][a-z0-9._/-]{2,255}$", value)
            if not valid:
                raise ValueError(f"{name} must be a stable lower-case version value")

    @property
    def enrichment_version(self) -> str:
        canonical = json.dumps(
            {
                "model_slug": self.model_slug,
                "prompt_version": self.prompt_version,
                "provider_policy_version": self.provider_policy_version,
                "schema_version": self.schema_version,
                "taxonomy_version": self.taxonomy_version,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def enrichment_json_schema() -> Mapping[str, object]:
    """Return a detached JSON Schema so callers cannot mutate the frozen contract."""

    schema: dict[str, object] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": ENRICHMENT_SCHEMA_VERSION,
        "type": "object",
        "additionalProperties": False,
        "required": [
            "sentiment",
            "confidence",
            "aspect_sentiments",
            "topics",
            "summary",
            "highlights",
        ],
        "properties": {
            "sentiment": {"type": "string", "enum": list(SENTIMENTS)},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "aspect_sentiments": {
                "type": "array",
                "maxItems": len(ASPECTS),
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["aspect", "sentiment", "confidence"],
                    "properties": {
                        "aspect": {"type": "string", "enum": list(ASPECTS)},
                        "sentiment": {"type": "string", "enum": list(SENTIMENTS)},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    },
                },
            },
            "topics": {
                "type": "array",
                "uniqueItems": True,
                "maxItems": len(TOPICS),
                "items": {"type": "string", "enum": list(TOPICS)},
            },
            "summary": {"type": "string", "minLength": 1, "maxLength": 500},
            "highlights": {
                "type": "array",
                "maxItems": 5,
                "items": {"type": "string", "minLength": 1, "maxLength": 240},
            },
        },
    }
    return MappingProxyType(schema)


@dataclass(frozen=True, slots=True)
class DLPProjection:
    decision: DLPDecision
    policy_version: str
    opaque_review_reference: str
    content_sha256: str | None
    redaction_count: int
    reason_code: DLPReasonCode | None = None
    _approved_text: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if not _VERSION.fullmatch(self.policy_version):
            raise ValueError("policy_version must be a stable lower-case version value")
        if not _SHA256.fullmatch(self.opaque_review_reference):
            raise ValueError("opaque_review_reference must be a SHA-256 digest")
        if self.decision is DLPDecision.APPROVED:
            if (
                self.reason_code is not None
                or self._approved_text is None
                or self.content_sha256 is None
            ):
                raise ValueError("approved projection requires minimized text and its hash")
            actual = hashlib.sha256(self._approved_text.encode("utf-8")).hexdigest()
            if self.content_sha256 != actual:
                raise ValueError("projection content hash does not match minimized text")
        elif (
            self.content_sha256 is not None
            or self._approved_text is not None
            or self.reason_code is None
        ):
            raise ValueError("quarantined projection must not retain approved content")

    def to_approved_ai_text(self) -> ApprovedAIText:
        if self.decision is not DLPDecision.APPROVED or self._approved_text is None:
            raise ValueError("quarantined review projection cannot cross the AI boundary")
        return ApprovedAIText.dlp_approved(
            self._approved_text,
            policy_version=self.policy_version,
            content_sha256=self.content_sha256 or "",
        )


def project_review_for_ai(
    *,
    source_record_hash: str,
    review_title: str | None,
    review_comment: str | None,
    policy_version: str = DLP_POLICY_VERSION,
) -> DLPProjection:
    """Minimize private review text for an external AI provider, or quarantine it.

    The original review text and natural review/order identifiers intentionally do
    not appear on the returned object. This function is deterministic and makes
    no network call.
    """

    if not _SHA256.fullmatch(source_record_hash):
        raise ValueError("source_record_hash must be a lower-case SHA-256 digest")
    if not _VERSION.fullmatch(policy_version):
        raise ValueError("policy_version must be a stable lower-case version value")
    opaque_reference = hashlib.sha256(f"{policy_version}:{source_record_hash}".encode()).hexdigest()
    raw_text = _join_review_text(review_title, review_comment)
    if not raw_text:
        return _quarantined(policy_version, opaque_reference, DLPReasonCode.EMPTY_TEXT)
    if len(raw_text) > MAX_REVIEW_TEXT_CHARACTERS:
        return _quarantined(policy_version, opaque_reference, DLPReasonCode.TEXT_TOO_LONG)
    if _DIRECT_IDENTIFIER.search(raw_text):
        return _quarantined(policy_version, opaque_reference, DLPReasonCode.DIRECT_IDENTIFIER)
    if _SECRET_LIKE.search(raw_text):
        return _quarantined(policy_version, opaque_reference, DLPReasonCode.SECRET_LIKE)

    minimized_text, redactions = _redact(raw_text)
    content_sha256 = hashlib.sha256(minimized_text.encode("utf-8")).hexdigest()
    return DLPProjection(
        decision=DLPDecision.APPROVED,
        policy_version=policy_version,
        opaque_review_reference=opaque_reference,
        content_sha256=content_sha256,
        redaction_count=redactions,
        _approved_text=minimized_text,
    )


def _join_review_text(title: str | None, comment: str | None) -> str:
    parts = []
    if title and title.strip():
        parts.append(f"Title: {title.strip()}")
    if comment and comment.strip():
        parts.append(f"Comment: {comment.strip()}")
    return "\n".join(parts)


def _redact(text: str) -> tuple[str, int]:
    redactions = 0

    def replace(match: re.Match[str], replacement: str) -> str:
        nonlocal redactions
        redactions += 1
        return replacement

    text = _EMAIL.sub(lambda match: replace(match, "[REDACTED_EMAIL]"), text)
    text = _URL.sub(lambda match: replace(match, "[REDACTED_URL]"), text)
    text = _CPF.sub(lambda match: replace(match, "[REDACTED_CPF]"), text)
    text = _PHONE.sub(lambda match: replace(match, "[REDACTED_PHONE]"), text)
    return text, redactions


def _quarantined(
    policy_version: str,
    opaque_reference: str,
    reason_code: DLPReasonCode,
) -> DLPProjection:
    return DLPProjection(
        decision=DLPDecision.QUARANTINED,
        policy_version=policy_version,
        opaque_review_reference=opaque_reference,
        content_sha256=None,
        redaction_count=0,
        reason_code=reason_code,
    )
