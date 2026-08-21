# M4 Test Cases and Results

## Test matrix

| ID | Type | Scenario | Expected result | Status | Evidence |
|---|---|---|---|---|---|
| TC-M4-001 | Schema/version | Construct the pinned enrichment JSON Schema and compute its version key twice | Immutable schema/taxonomy and stable SHA-256 key | `PASS` | `uv run pytest tests/test_m4_enrichment.py tests/test_m4_enrichment_migration.py -q -p no:cacheprovider` — 19 passed, 2026-08-21 |
| TC-M4-002 | Negative/schema | Change one model, policy, prompt, schema or taxonomy input | Version key changes; empty/unsafe version input is denied | `PASS` | Same focused offline suite verifies all five version inputs and unsafe values |
| TC-M4-003 | Ledger/replay | Register the same run/invocation/result-map event twice | Same event is returned; conflicting payload is denied | `PASS` | Deterministic in-memory run/invocation/result map replay test passes |
| TC-M4-004 | Ledger/transition | Attempt skipped, stale or terminal-state transition | Illegal transition is denied without raw/error payload leakage | `PASS` | Unvalidated result and skipped invocation transitions return stable sanitized errors |
| TC-M4-005 | Migration/security | Inspect and replay migration `009` through the adapter fake | Three additive, exact-grant, secret-free ledgers; no raw text/body columns | `PASS` | Static DDL/grant scan and two-pass `SnowflakeClient` fake replay pass; migration not applied live |
| TC-M4-006 | DLP/happy path | Project a synthetic Portuguese review with no identifier | Opaque review reference and DLP-approved text/hash only | `PASS` | Deterministic synthetic Portuguese fixture produces only opaque SHA-256 reference and approved payload |
| TC-M4-007 | DLP/redaction | Synthetic review includes email, URL, phone or CPF-like number | Identifiers are redacted; raw natural IDs never reach provider payload | `PASS` | Four identifier patterns become placeholders before `ApprovedAIText` boundary |
| TC-M4-008 | DLP/fail closed | Empty, over-limit, secret-like or ambiguous review input | Projection is quarantined with stable sanitized code | `PASS` | Empty/over-limit/direct-ID/secret-like fixtures quarantine and cannot build provider payload |
| TC-M4-009 | DLP/replay | Same permitted source hash/text/policy is projected twice | Same opaque reference/content hash and decision | `PASS` | Projection is deterministic and its representation excludes the synthetic review text |
| TC-M4-010 | Catalog/cost | Snapshot pinned OpenRouter model catalog | Slug/context/price/provider-policy evidence is stored without key or prompt | `PASS` | Public read-only `/models` request through `OpenRouterCatalogClient` on 2026-08-21; [safe snapshot](../../evidence/M4_OPENROUTER_ENRICHMENT_CATALOG_2026-08-21.json) validates slug/context/prices/structured output, no API key or content payload |
| TC-M4-011 | Selector | New, changed, reused, ineligible and quarantined reviews | Deterministic selection counts and no duplicate dispatch | `PASS` | Synthetic hashes cover all five dispositions, reverse-order determinism and conflicting-lineage denial |
| TC-M4-012 | Prompt/security | Portuguese instruction-injection review fixture | Evidence remains delimited data; no tool/instruction escalation | `PASS` | Synthetic injection stays solely inside `REVIEW_UNTRUSTED`; trusted system prompt explicitly denies evidence instructions/tools/schema changes |
| TC-M4-013 | Provider | Structured output fake plus opt-in synthetic live smoke | Pinned model, schema and rate controls respected | `PENDING` | Fake contract passes; `tests/live/test_openrouter_enrichment_live.py` is synthetic-only and awaits explicit token-cost opt-in |
| TC-M4-014 | Validation/retry | Invalid enum/range/ID and transient/permanent provider failures | At most one repair, bounded retry, quarantine/resume safely | `PASS` | Synthetic malformed/unknown/duplicate/restricted outputs fail closed; exact one repair, transient resume/max-attempt quarantine and permanent-error quarantine pass |
| TC-M4-015 | Budget | Estimated/actual spend reaches warning and hard cap | Warning at 0.50 USD/day; new calls stop at 5 USD | `PENDING` | IMP-M4-010 |
| TC-M4-016 | Commit/coverage | Partial valid/invalid result batch | Only validated result commits; coverage/base fact reconcile | `PENDING` | IMP-M4-011 |
| TC-M4-017 | Evaluation | Stratified private golden/holdout is re-run | Reproducible semantic report; holdout remains blind | `PENDING` | IMP-M4-012 |
| TC-M4-018 | Release gate | AI candidate below quality threshold | Candidate cannot publish or alter active data release | `PENDING` | IMP-M4-013 |
| TC-M4-019 | Observability | Aggregate dashboard/reconciliation query | Tokens, cost, latency, errors and coverage reconcile with ledgers | `PENDING` | IMP-M4-014 |
| TC-M4-020 | Recovery | Pause/resume/model-change/purge tabletop | Bounded recovery preserves base facts and auditability | `PENDING` | IMP-M4-015 |

## Execution log — 2026-08-21 (`IMP-M4-001…003`)

- Focused M4 offline suite: `uv run pytest tests/test_m4_enrichment.py
  tests/test_m4_enrichment_migration.py -q -p no:cacheprovider` → **19 passed**.
- `uv run ruff format --check`, `uv run ruff check` and strict `uv run mypy`
  over the new M4 source/tests pass. No Snowflake, R2, OpenRouter or Chroma
  request was made and fixtures contain synthetic text only.
- Full local regression with an explicit workspace pytest base temp directory:
  `uv run pytest -q -p no:cacheprovider --basetemp
  D:\project\reviewlens-data-platform\.tmp\pytest-m4-full --cov=reviewlens
  --cov-report=term-missing` → **511 passed, 8 opt-in live skipped, 86.05%
  coverage**. The default Windows user temp root was access-denied, so it is not
  used as evidence for this run.

## Execution log — 2026-08-21 (`IMP-M4-004…006`)

- Focused M4 suite: `uv run pytest tests/test_m4_enrichment.py
  tests/test_m4_enrichment_migration.py tests/test_m4_catalog_selection_prompt.py
  -q -p no:cacheprovider --basetemp
  D:\project\reviewlens-data-platform\.tmp\pytest-m4-bundle` → **26 passed**.
- One public metadata-only call through the catalog implementation confirmed the
  configured enrichment model still exists, has a 1,048,576-token context,
  supports structured outputs and has prompt/completion price 0.0000001 /
  0.0000004 USD per token. It used no API key, token-generating endpoint,
  prompt, review, R2, Snowflake or Chroma request.
- Full local regression after the bundle: `uv run pytest -q -p
  no:cacheprovider --basetemp D:\project\reviewlens-data-platform\.tmp\pytest-m4-full-2
  --cov=reviewlens --cov-report=term-missing` → **518 passed, 8 opt-in live
  skipped, 86.12% coverage**.

## Execution log — 2026-08-21 (`IMP-M4-007…009`)

- Focused fake/contract suite includes structured-provider payload, rate limit,
  schema/semantic negative cases, one-repair, retry/resume and terminal replay.
  `uv run pytest ... tests/test_m4_execution.py tests/test_openrouter.py` →
  **46 passed**; it uses only synthetic Portuguese text and performs no
  OpenRouter network call.
- An opt-in live smoke at `tests/live/test_openrouter_enrichment_live.py` sends
  one synthetic review with `max_tokens=200` only when
  `REVIEWLENS_RUN_LIVE_OPENROUTER_ENRICHMENT=1`; it remains `PENDING` until the
  owner explicitly accepts the limited token cost.
- Full local regression: **529 passed, 9 opt-in live skipped, 86.18% coverage**
  using workspace-local pytest temp `...\.tmp\pytest-m4-full-3`.
