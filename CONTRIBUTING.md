# Contributing to ReviewLens

This is a solo portfolio repository, but every change follows a reviewable delivery contract.

## Before coding

1. Read `docs/PROJECT_STATUS.md` and the active phase checklist/test matrix.
2. Select the smallest dependency-ready implementation item.
3. Define or update its test cases before or alongside the code.
4. Use synthetic fixtures for cloud, AI, CI and public artifacts.

## Local workflow

```powershell
uv sync --locked --cache-dir .uv-cache
uv run ruff format src tests
uv run ruff check src tests
uv run mypy src tests
uv run pytest --cov=reviewlens --cov-report=term-missing
```

Never commit `.env`, provider credentials, private keys, Olist source CSVs, real review text, embeddings, vector data or row-level derived Olist artifacts. The Olist license requires attribution, non-commercial use and ShareAlike; changes affecting data or public artifacts must preserve `docs/DATA_ATTRIBUTION.md`.

## Pull request evidence

Every pull request should identify:

- Implementation-plan and PRD requirement IDs.
- Scope and data-policy impact.
- Commands actually run and their results.
- Deferred live checks and the reason they remain deferred.
- Documentation, checklist and status updates.

Use `DONE` only when the artifact exists and verification passes. A missing live check remains `PENDING`, `DEFERRED` or `FAIL` as appropriate.
