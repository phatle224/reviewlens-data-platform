from __future__ import annotations

import hashlib

import pytest

from reviewlens.ai.enrichment import (
    ASPECTS,
    ENRICHMENT_SCHEMA_VERSION,
    ENRICHMENT_TAXONOMY_VERSION,
    DLPDecision,
    DLPReasonCode,
    EnrichmentVersionInput,
    enrichment_json_schema,
    project_review_for_ai,
)
from reviewlens.ai.ledger import (
    EnrichmentInvocationState,
    EnrichmentLedgerConflict,
    EnrichmentRunState,
    EnrichmentTransitionDenied,
    InMemoryEnrichmentLedger,
)

SOURCE_HASH = "a" * 64
INPUT_HASH = "b" * 64
RESULT_HASH = "c" * 64
SELECTION_HASH = "d" * 64


def _version(**changes: str) -> EnrichmentVersionInput:
    return EnrichmentVersionInput(
        model_slug=changes.get("model_slug", "google/gemini-2.5-flash-lite"),
        provider_policy_version=changes.get("provider_policy_version", "openrouter-deny-v1"),
        prompt_version=changes.get("prompt_version", "pt-enrichment-v1"),
        schema_version=changes.get("schema_version", ENRICHMENT_SCHEMA_VERSION),
        taxonomy_version=changes.get("taxonomy_version", ENRICHMENT_TAXONOMY_VERSION),
    )


def test_m4_schema_taxonomy_and_version_key_are_stable() -> None:
    version = _version()
    schema = enrichment_json_schema()

    assert version.enrichment_version == _version().enrichment_version
    assert schema["$id"] == ENRICHMENT_SCHEMA_VERSION
    assert schema["additionalProperties"] is False
    properties = schema["properties"]
    assert isinstance(properties, dict)
    aspect_items = properties["aspect_sentiments"]
    assert isinstance(aspect_items, dict)
    assert aspect_items["maxItems"] == len(ASPECTS)
    assert set(properties) == {
        "sentiment",
        "confidence",
        "aspect_sentiments",
        "topics",
        "summary",
        "highlights",
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("model_slug", "google/gemini-2.5-flash"),
        ("provider_policy_version", "openrouter-deny-v2"),
        ("prompt_version", "pt-enrichment-v2"),
        ("schema_version", "reviewlens-enrichment-schema-v2"),
        ("taxonomy_version", "reviewlens-enrichment-taxonomy-v2"),
    ],
)
def test_m4_version_key_changes_with_each_pinned_input(field: str, value: str) -> None:
    baseline = _version().enrichment_version
    assert _version(**{field: value}).enrichment_version != baseline


def test_m4_version_key_rejects_unsafe_or_empty_inputs() -> None:
    with pytest.raises(ValueError, match="stable lower-case version"):
        _version(prompt_version="")
    with pytest.raises(ValueError, match="stable lower-case version"):
        _version(model_slug="GOOGLE/GEMINI")


def test_m4_dlp_projects_synthetic_text_with_opaque_reference_only() -> None:
    projection = project_review_for_ai(
        source_record_hash=SOURCE_HASH,
        review_title="Entrega muito rápida",
        review_comment="Produto chegou bem embalado e funciona perfeitamente.",
    )

    approved = projection.to_approved_ai_text()
    assert projection.decision is DLPDecision.APPROVED
    assert projection.reason_code is None
    assert (
        projection.opaque_review_reference
        == hashlib.sha256(f"reviewlens-dlp-minimization-v1:{SOURCE_HASH}".encode()).hexdigest()
    )
    assert approved.policy_version == "reviewlens-dlp-minimization-v1"
    assert (
        approved.text == "Title: Entrega muito rápida\n"
        "Comment: Produto chegou bem embalado e funciona perfeitamente."
    )
    assert SOURCE_HASH not in approved.text


def test_m4_dlp_redacts_recognized_identifiers_before_provider_boundary() -> None:
    projection = project_review_for_ai(
        source_record_hash=SOURCE_HASH,
        review_title="Contato",
        review_comment=(
            "Escreva para pessoa@example.com ou https://example.test; "
            "telefone +55 (11) 91234-5678 CPF 123.456.789-09."
        ),
    )
    approved = projection.to_approved_ai_text()

    assert projection.decision is DLPDecision.APPROVED
    assert projection.redaction_count == 4
    assert "pessoa@example.com" not in approved.text
    assert "example.test" not in approved.text
    assert "91234-5678" not in approved.text
    assert "123.456.789-09" not in approved.text
    assert approved.text.count("[REDACTED_") == 4


@pytest.mark.parametrize(
    ("title", "comment", "reason"),
    [
        (None, None, DLPReasonCode.EMPTY_TEXT),
        ("x" * 2_001, None, DLPReasonCode.TEXT_TOO_LONG),
        (None, "order_id=12345", DLPReasonCode.DIRECT_IDENTIFIER),
        (None, "minha senha é nao-registre", DLPReasonCode.SECRET_LIKE),
    ],
)
def test_m4_dlp_quarantines_ambiguous_or_unsafe_text(
    title: str | None, comment: str | None, reason: DLPReasonCode
) -> None:
    projection = project_review_for_ai(
        source_record_hash=SOURCE_HASH,
        review_title=title,
        review_comment=comment,
    )

    assert projection.decision is DLPDecision.QUARANTINED
    assert projection.reason_code is reason
    assert projection.content_sha256 is None
    with pytest.raises(ValueError, match="cannot cross"):
        projection.to_approved_ai_text()


def test_m4_dlp_is_deterministic_and_safe_to_represent() -> None:
    first = project_review_for_ai(
        source_record_hash=SOURCE_HASH,
        review_title="bom",
        review_comment="não exponha esta frase privada",
    )
    second = project_review_for_ai(
        source_record_hash=SOURCE_HASH,
        review_title="bom",
        review_comment="não exponha esta frase privada",
    )

    assert first == second
    assert "não exponha" not in repr(first)


def test_m4_ledger_replays_same_run_invocation_and_result_map() -> None:
    ledger = InMemoryEnrichmentLedger()
    run = ledger.register_run(
        source_release_id="olist-release-v1",
        enrichment_version=_version().enrichment_version,
        selection_sha256=SELECTION_HASH,
    )
    assert (
        ledger.register_run(
            source_release_id="olist-release-v1",
            enrichment_version=_version().enrichment_version,
            selection_sha256=SELECTION_HASH,
        )
        is run
    )
    assert (
        ledger.transition_run(run.enrichment_run_id, target=EnrichmentRunState.RUNNING).state
        is EnrichmentRunState.RUNNING
    )
    invocation = ledger.register_invocation(
        enrichment_run_id=run.enrichment_run_id,
        source_record_hash=SOURCE_HASH,
        input_sha256=INPUT_HASH,
        attempt_number=1,
    )
    assert (
        ledger.register_invocation(
            enrichment_run_id=run.enrichment_run_id,
            source_record_hash=SOURCE_HASH,
            input_sha256=INPUT_HASH,
            attempt_number=1,
        )
        is invocation
    )
    ledger.transition_invocation(
        invocation.invocation_id, target=EnrichmentInvocationState.DISPATCHED
    )
    ledger.transition_invocation(
        invocation.invocation_id, target=EnrichmentInvocationState.SUCCEEDED
    )
    result = ledger.record_result_map(
        invocation_id=invocation.invocation_id, result_sha256=RESULT_HASH
    )
    assert (
        ledger.record_result_map(invocation_id=invocation.invocation_id, result_sha256=RESULT_HASH)
        is result
    )
    assert len(ledger.runs) == len(ledger.invocations) == len(ledger.result_maps) == 1


def test_m4_ledger_denies_invalid_transitions_and_result_conflict() -> None:
    ledger = InMemoryEnrichmentLedger()
    run = ledger.register_run(
        source_release_id="olist-release-v1",
        enrichment_version=_version().enrichment_version,
        selection_sha256=SELECTION_HASH,
    )
    invocation = ledger.register_invocation(
        enrichment_run_id=run.enrichment_run_id,
        source_record_hash=SOURCE_HASH,
        input_sha256=INPUT_HASH,
        attempt_number=1,
    )
    with pytest.raises(EnrichmentTransitionDenied, match="AI_ENRICHMENT_RESULT_NOT_VALIDATED"):
        ledger.record_result_map(invocation_id=invocation.invocation_id, result_sha256=RESULT_HASH)
    with pytest.raises(EnrichmentTransitionDenied, match="AI_ENRICHMENT_TRANSITION_DENIED"):
        ledger.transition_invocation(
            invocation.invocation_id, target=EnrichmentInvocationState.SUCCEEDED
        )
    ledger.transition_invocation(
        invocation.invocation_id, target=EnrichmentInvocationState.DISPATCHED
    )
    ledger.transition_invocation(
        invocation.invocation_id, target=EnrichmentInvocationState.SUCCEEDED
    )
    ledger.record_result_map(invocation_id=invocation.invocation_id, result_sha256=RESULT_HASH)
    second = ledger.register_invocation(
        enrichment_run_id=run.enrichment_run_id,
        source_record_hash=SOURCE_HASH,
        input_sha256="e" * 64,
        attempt_number=2,
    )
    ledger.transition_invocation(second.invocation_id, target=EnrichmentInvocationState.DISPATCHED)
    ledger.transition_invocation(second.invocation_id, target=EnrichmentInvocationState.SUCCEEDED)
    with pytest.raises(EnrichmentLedgerConflict, match="AI_ENRICHMENT_IDEMPOTENCY_CONFLICT"):
        ledger.record_result_map(invocation_id=second.invocation_id, result_sha256=RESULT_HASH)
