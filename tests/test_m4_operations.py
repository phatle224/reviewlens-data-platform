"""Static safety contract for the M4 private enrichment recovery runbook."""

from __future__ import annotations

from pathlib import Path

RUNBOOK = Path("docs/runbooks/M4_AI_ENRICHMENT_OPERATIONS.md")


def _source() -> str:
    return RUNBOOK.read_text(encoding="utf-8")


def test_m4_operations_runbook_covers_pause_resume_model_change_and_purge() -> None:
    source = _source()
    normalized = " ".join(source.lower().split())

    for required in (
        "## 2. Pause và triage",
        "## 3. Resume an toàn",
        "## 4. Model, prompt, schema hoặc taxonomy change",
        "## 5. Purge và retention",
        "## 6. TC-M4-020 tabletop drill đã thực hiện offline",
        "airflow dags pause olist_pipeline",
        "airflow dags unpause olist_pipeline",
        "AI_ENRICHMENT_BUDGET_EXHAUSTED",
        "AI_ENRICHMENT_SCHEMA_INVALID",
        "OPENROUTER_TRANSIENT",
        "FACT_REVIEW_BASE",
        "enrichment_version",
    ):
        assert required in source
    assert "purge tự động" in normalized
    assert "`retryable`" in normalized
    assert "tối đa ba attempts" in normalized
    assert "không gọi openrouter, snowflake, r2 hoặc docker runtime" in normalized
    assert "không được publish và không được gọi release pointer" in normalized


def test_m4_operations_runbook_is_private_safe_and_links_resolve() -> None:
    source = _source()
    normalized = source.lower()

    for forbidden in ("sk-or-", "openrouter_api_key=", "snowflake_password=", "private_key="):
        assert forbidden not in normalized
    assert "không dùng `remove-item -recurse`" in normalized
    assert "purge tự động" in normalized
    assert "dry-run bằng metadata/hashes" in normalized

    for target in (
        "./M1_CREDENTIAL_ROTATION.md",
        "../ADR/ADR-003-openrouter-ai-provider.md",
        "../ADR/ADR-016-m4-enrichment-contract-and-dlp-projection.md",
        "../phases/M4/M4_CHECKLIST.md",
        "../phases/M4/M4_TEST_CASES.md",
        "../PROJECT_STATUS.md",
    ):
        assert (RUNBOOK.parent / target).resolve().exists()
