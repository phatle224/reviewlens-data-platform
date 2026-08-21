"""Synthetic offline contracts for validated enrichment commit and coverage."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from reviewlens.ai.commit import (
    BaseReviewCoverageInput,
    EnrichmentCommitDisposition,
    EnrichmentCommitError,
    InMemoryValidatedEnrichmentStore,
    ValidatedEnrichmentCommit,
    build_enrichment_coverage_projection,
)
from reviewlens.ai.ledger import EnrichmentResultMap
from reviewlens.ai.validation import ValidatedEnrichment, validate_enrichment_response
from reviewlens.providers.snowflake import SnowflakeClient, split_sql_statements

MIGRATION_PATH = Path("infra/snowflake/010_ai_review_enriched.sql")
VERSION = "v" * 64


def _result(*, sentiment: str = "positive") -> ValidatedEnrichment:
    return validate_enrichment_response(
        json.dumps(
            {
                "sentiment": sentiment,
                "confidence": 0.9,
                "aspect_sentiments": [
                    {"aspect": "delivery", "sentiment": sentiment, "confidence": 0.8}
                ],
                "topics": ["delivery_speed"],
                "summary": "Synthetic delivery outcome.",
                "highlights": ["Synthetic highlight."],
            }
        )
    )


def _result_hash(result: ValidatedEnrichment) -> str:
    canonical = json.dumps(result.model_dump(mode="json"), separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _commit(
    *,
    review_id: str = "synthetic-review-1",
    order_id: str = "synthetic-order-1",
    source_record_hash: str = "a" * 64,
    input_sha256: str = "b" * 64,
    result: ValidatedEnrichment | None = None,
) -> ValidatedEnrichmentCommit:
    validated = result or _result()
    result_map = EnrichmentResultMap(
        result_map_id="c" * 64,
        enrichment_run_id="d" * 64,
        source_record_hash=source_record_hash,
        enrichment_version=VERSION,
        invocation_id="e" * 64,
        result_sha256=_result_hash(validated),
    )
    return ValidatedEnrichmentCommit(
        review_id=review_id,
        order_id=order_id,
        source_record_hash=source_record_hash,
        enrichment_version=VERSION,
        input_sha256=input_sha256,
        result_map=result_map,
        model_slug="google/gemini-2.5-flash-lite",
        prompt_version="pt-br-enrichment-untrusted-evidence-v1",
        schema_version="reviewlens-enrichment-schema-v1",
        taxonomy_version="reviewlens-enrichment-taxonomy-v1",
        dlp_policy_version="reviewlens-dlp-minimization-v1",
        result=validated,
    )


def test_m4_validated_commit_is_idempotent_and_exposes_only_hashes_to_selector() -> None:
    store = InMemoryValidatedEnrichmentStore()
    candidate = _commit()

    first = store.commit(candidate)
    replay = store.commit(candidate)
    selected = candidate.to_selection_committed()

    assert first.disposition is EnrichmentCommitDisposition.INSERTED
    assert replay.disposition is EnrichmentCommitDisposition.REUSED
    assert store.commits == (candidate,)
    assert selected.review_lineage_sha256 == candidate.review_lineage_sha256
    assert selected.source_record_hash == "a" * 64
    assert "synthetic-review-1" not in repr(candidate)
    assert "Synthetic delivery outcome." not in repr(candidate)


def test_m4_commit_rejects_unvalidated_or_mismatched_result_before_any_write() -> None:
    store = InMemoryValidatedEnrichmentStore()
    valid = _result()
    candidate = _commit(result=valid)
    mismatched_map = EnrichmentResultMap(
        result_map_id="c" * 64,
        enrichment_run_id="d" * 64,
        source_record_hash="a" * 64,
        enrichment_version=VERSION,
        invocation_id="e" * 64,
        result_sha256="f" * 64,
    )
    with pytest.raises(EnrichmentCommitError, match="AI_ENRICHMENT_RESULT_NOT_VALIDATED"):
        ValidatedEnrichmentCommit(
            review_id=candidate.review_id,
            order_id=candidate.order_id,
            source_record_hash=candidate.source_record_hash,
            enrichment_version=candidate.enrichment_version,
            input_sha256=candidate.input_sha256,
            result_map=mismatched_map,
            model_slug=candidate.model_slug,
            prompt_version=candidate.prompt_version,
            schema_version=candidate.schema_version,
            taxonomy_version=candidate.taxonomy_version,
            dlp_policy_version=candidate.dlp_policy_version,
            result=valid,
        )

    assert store.commits == ()


def test_m4_changed_validated_input_replaces_current_result_without_partial_rows() -> None:
    store = InMemoryValidatedEnrichmentStore()
    first = _commit()
    changed = _commit(
        source_record_hash="f" * 64,
        input_sha256="9" * 64,
        result=_result(sentiment="negative"),
    )

    store.commit(first)
    outcome = store.commit(changed)

    assert outcome.disposition is EnrichmentCommitDisposition.REPLACED
    assert store.commits == (changed,)


def test_m4_coverage_keeps_all_base_reviews_when_ai_is_missing_or_ineligible() -> None:
    committed = _commit(source_record_hash="f" * 64, input_sha256="9" * 64)
    second_eligible = "1" * 64
    projection = build_enrichment_coverage_projection(
        base_reviews=(
            BaseReviewCoverageInput(
                review_lineage_sha256=committed.review_lineage_sha256,
                source_record_hash=committed.source_record_hash,
                ai_eligible=True,
            ),
            BaseReviewCoverageInput(
                review_lineage_sha256=second_eligible,
                source_record_hash="2" * 64,
                ai_eligible=True,
            ),
            BaseReviewCoverageInput(
                review_lineage_sha256="3" * 64,
                source_record_hash="4" * 64,
                ai_eligible=False,
            ),
        ),
        commits=(committed,),
        enrichment_version=VERSION,
    )

    assert projection.base_review_count == 3
    assert projection.eligible_review_count == 2
    assert projection.valid_enrichment_count == 1
    assert projection.missing_eligible_review_count == 1
    assert str(projection.coverage_ratio) == "0.5"
    assert "synthetic-review-1" not in repr(projection)


class _RecordingCursor:
    def __init__(self, statements: list[str]) -> None:
        self._statements = statements
        self.sfqid = "synthetic-query-id"

    def execute(self, command: str) -> _RecordingCursor:
        self._statements.append(command)
        return self

    def fetchall(self) -> list[tuple[object, ...]]:
        return []

    def close(self) -> None:
        return None


class _RecordingConnection:
    def __init__(self) -> None:
        self.statements: list[str] = []

    def cursor(self) -> _RecordingCursor:
        return _RecordingCursor(self.statements)

    def close(self) -> None:
        return None


def test_m4_committed_enrichment_migration_is_private_exact_and_idempotent() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    upper = source.upper()
    connection = _RecordingConnection()
    client = SnowflakeClient(connection)
    expected = split_sql_statements(source)

    assert "CREATE TABLE IF NOT EXISTS REVIEWLENS.AI.AI_REVIEW_ENRICHED" in upper
    assert "PRIMARY KEY (REVIEW_ID, ORDER_ID, ENRICHMENT_VERSION)" in upper
    assert "REVIEW_LINEAGE_SHA256 VARCHAR(64) NOT NULL" in upper
    assert "M4_ENRICHED_SCHEMA_COMPATIBILITY" in upper
    assert "CREATE OR REPLACE" not in upper
    assert not any(token in upper for token in ("REVIEW_TEXT", "PROMPT_TEXT", "RAW_PAYLOAD"))
    assert not any(token in upper for token in ("API_KEY", "PRIVATE_KEY", "PASSWORD", "EMBEDDING"))
    assert tuple(
        " ".join(statement.upper().split())
        for statement in expected
        if statement.lstrip().upper().startswith("GRANT ")
    ) == (
        "GRANT USAGE ON SCHEMA REVIEWLENS.AI TO ROLE AI_ENRICH_ROLE",
        "GRANT SELECT, INSERT, UPDATE ON TABLE REVIEWLENS.AI.AI_REVIEW_ENRICHED "
        "TO ROLE AI_ENRICH_ROLE",
    )

    client.apply_sql_file(MIGRATION_PATH, operation="M4 committed enrichment migration")
    client.apply_sql_file(MIGRATION_PATH, operation="M4 committed enrichment migration replay")
    assert tuple(connection.statements) == expected + expected
