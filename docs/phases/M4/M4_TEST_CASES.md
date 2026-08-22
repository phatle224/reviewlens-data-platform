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
| TC-M4-013 | Provider | Structured output fake plus opt-in synthetic live smoke | Pinned model, schema and rate controls respected | `PASS` | Fake contracts pass; 40/40 real holdout DLP preflight and one owner-authorized real single-item diagnostic completed with a schema-valid structured result. No row-level output was persisted. |
| TC-M4-014 | Validation/retry | Invalid enum/range/ID and transient/permanent provider failures | At most one repair, bounded retry, quarantine/resume safely | `PASS` | Synthetic malformed/unknown/duplicate/restricted outputs fail closed; exact one repair, transient resume/max-attempt quarantine and permanent-error quarantine pass |
| TC-M4-015 | Budget | Estimated/actual spend reaches warning and hard cap | Warning at 0.50 USD/day; new calls stop at 5 USD | `PASS` | Offline deterministic estimator, durable aggregate-only reservation/settlement and pre-delegate hard-stop tests pass; live smoke is wrapped but remains opt-in/unexecuted |
| TC-M4-016 | Commit/coverage | Partial valid/invalid result batch | Only validated result commits; coverage/base fact reconcile | `PASS` | Synthetic commit contract rejects result-map/hash mismatch before write; exact replay is reused, changed approved input replaces atomically, and aggregate coverage keeps missing/ineligible base reviews in its denominator |
| TC-M4-017 | Evaluation | Stratified private golden/holdout is re-run | Reproducible semantic report; holdout remains blind | `PENDING` | 200 private labels are human-approved and the deterministic split has 40 blind holdout items. The owner-authorized full run stopped fail-closed on `AI_ENRICHMENT_SCHEMA_INVALID`, so no prediction/report exists and no metric may be claimed. The evaluator rejects train/missing/duplicate IDs and stores only aggregate metrics. |
| TC-M4-018 | Release gate | AI candidate below quality threshold | Candidate cannot publish or alter active data release | `PASS` | Synthetic version-bound gate blocks low metrics, missing evaluation and version mismatch before the publish callback; no Snowflake pointer mutation exists in this offline contract |
| TC-M4-019 | Observability | Aggregate dashboard/reconciliation query | Tokens, cost, latency, errors and coverage reconcile with ledgers | `PASS` | Synthetic terminal telemetry is deterministic and reconciles exact committed USD and current valid coverage; duplicate opaque IDs plus budget/version/coverage drift are denied before snapshot creation, 2026-08-22 |
| TC-M4-020 | Recovery | Pause/resume/model-change/purge tabletop | Bounded recovery preserves base facts and auditability | `PASS` | Private-safe runbook contract verifies pause/triage, bounded retryable resume, version-isolated model change and no-direct-delete purge protocol; 27 focused offline tests pass, 2026-08-22 |

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

## Execution log — 2026-08-22 (`IMP-M4-010`)

- Offline M4 cost-control suite: `uv run pytest tests\test_m4_enrichment.py
  tests\test_m4_enrichment_migration.py tests\test_m4_catalog_selection_prompt.py
  tests\test_m4_execution.py tests\test_m4_budget.py tests\test_openrouter.py -q
  -p no:cacheprovider --basetemp
  D:\project\reviewlens-data-platform\.tmp\pytest-m4-010-focused` → **49 passed**.
- `EnrichmentBudget` persists only schema version, opaque reservation IDs, ISO
  dates and aggregate USD amounts under ignored `runtime_state/`; it never stores
  text, prompt, response, model payload or natural identifier. Reservation is
  written before provider delegation and remains counted after an interrupted
  process, so a restart cannot bypass the cap.
- Ruff format/lint and strict mypy pass for the new guard and its tests. The
  live test remains skipped unless the owner sets its explicit opt-in variable;
  no OpenRouter completion, R2, Snowflake or Chroma request was made.
- Full local regression after regenerating the declared artifact lock:
  `uv run pytest -q -p no:cacheprovider --basetemp
  D:\project\reviewlens-data-platform\.tmp\pytest-m4-010-full-3
  --cov=reviewlens --cov-report=term-missing` → **532 passed, 9 opt-in live
  skipped, 86.08% coverage**. `tests\test_deploy.py` also passes after the
  lock refresh.

## Execution log — 2026-08-22 (`IMP-M4-011`)

- Offline validated-commit and coverage suite: `uv run pytest
  tests\test_m4_commit.py tests\test_m4_enrichment.py
  tests\test_m4_enrichment_migration.py tests\test_m4_catalog_selection_prompt.py
  tests\test_m4_execution.py tests\test_m4_budget.py tests\test_openrouter.py -q
  -p no:cacheprovider --basetemp
  D:\project\reviewlens-data-platform\.tmp\pytest-m4-011-focused` → **54 passed**.
- The static `010_ai_review_enriched.sql` contract is replayed through the
  Snowflake adapter fake and grants only the exact private table privileges to
  `AI_ENRICH_ROLE`. It is not applied to Snowflake. No OpenRouter, R2,
  Snowflake or Chroma request was made.
- Full local regression after artifact-lock refresh: `uv run pytest -q -p
  no:cacheprovider --basetemp
  D:\project\reviewlens-data-platform\.tmp\pytest-m4-011-full
  --cov=reviewlens --cov-report=term-missing` → **537 passed, 9 opt-in live
  skipped, 86.10% coverage**.

## Execution log — 2026-08-22 (`IMP-M4-012`, partial)

- Offline evaluator contract suite: `uv run pytest tests\test_m4_evaluation.py
  tests\test_m4_commit.py tests\test_m4_enrichment.py
  tests\test_m4_enrichment_migration.py tests\test_m4_catalog_selection_prompt.py
  tests\test_m4_execution.py tests\test_m4_budget.py tests\test_openrouter.py -q
  -p no:cacheprovider --basetemp
  D:\project\reviewlens-data-platform\.tmp\pytest-m4-012-focused-3` → **58 passed**.
- The evaluator stores/returns only opaque IDs, structured labels and aggregate
  metrics. It rejects train-ID predictions, incomplete holdouts and fewer than
  five labels; actual Olist labels must live under ignored `private_evaluation/`.
  No real label, review text, OpenRouter, R2, Snowflake or Chroma request was
  made. TC-M4-017 remains `PENDING` until a private human-reviewed set is run.
- Full local regression after artifact-lock refresh: `uv run pytest -q -p
  no:cacheprovider --basetemp
  D:\project\reviewlens-data-platform\.tmp\pytest-m4-012-full
  --cov=reviewlens --cov-report=term-missing` → **541 passed, 9 opt-in live
  skipped, 86.03% coverage**.

## Execution log — 2026-08-22 (`IMP-M4-012`, annotation-pack progress)

- Added `reviewlens-golden-pack`: it joins private local Olist review/order/item/
  product metadata, removes natural IDs from the annotation shape, maps category
  to an opaque bucket, samples deterministically across score/length/category/
  delivery, and writes a queue plus blank structured labels only under ignored
  `private_evaluation/`. The human aspect label is intentionally not inferred by
  the sampler; it becomes part of the later split after review.
- Executed `uv run reviewlens-golden-pack generate --archive-dir archive
  --output-dir private_evaluation\m4_enrichment_v1 --seed
  m4-olist-annotation-v1` → **200 candidates**, `pending_human_review`. Console
  output contained only count/path/status; no review text, natural ID, OpenRouter,
  R2, Snowflake or Chroma call occurred.
- Focused tool/evaluator suite: `uv run pytest tests\test_m4_golden_pack.py
  tests\test_m4_evaluation.py -q -p no:cacheprovider --basetemp
  D:\project\reviewlens-data-platform\.tmp\pytest-m4-012-pack-focused-final`
  → **8 passed**. TC-M4-017 remains pending until all real labels are approved,
  the private holdout is validated, and a version-bound prediction report exists.
- Full local regression after artifact-lock refresh: `uv run pytest -q -p
  no:cacheprovider --basetemp
  D:\project\reviewlens-data-platform\.tmp\pytest-m4-012-pack-full-rerun
  --cov=reviewlens --cov-report=term-missing` → **553 passed, 9 opt-in live
  skipped, 85.69% coverage**.

## Execution log — 2026-08-22 (`IMP-M4-012`, machine-assisted suggestions)

- Owner authorized automatic private suggestions. `reviewlens-golden-pack suggest`
  reads only queue score/delivery metadata and writes 200 `machine_assisted`
  labels with source `offline_score_delivery_heuristic_v1`; it does not send or
  semantically inspect review text, call an LLM, or overwrite the pending label
  template. The completed-golden loader rejects this status by design.
- Executed `uv run reviewlens-golden-pack suggest --annotation-queue-path
  private_evaluation\m4_enrichment_v1\annotation_queue.jsonl --labels-path
  private_evaluation\m4_enrichment_v1\labels.jsonl --output-path
  private_evaluation\m4_enrichment_v1\labels.machine_assisted.jsonl` → **200
  candidates**, `machine_assisted_review_required`. Console output was aggregate
  only; no OpenRouter, R2, Snowflake or Chroma request occurred.
- Focused static checks pass: Ruff format/lint and strict mypy over the golden-pack
  implementation/tests; `uv run pytest tests\test_m4_golden_pack.py
  tests\test_m4_evaluation.py -q -p no:cacheprovider --basetemp
  D:\project\reviewlens-data-platform\.tmp\pytest-m4-012-machine-focused`
  → **9 passed**. The test proves that `machine_assisted` labels are rejected by
  the completed-golden loader.
- Final local regression after artifact-lock refresh: `uv run pytest -q -p
  no:cacheprovider --basetemp
  D:\project\reviewlens-data-platform\.tmp\pytest-m4-012-machine-full-rerun
  --cov=reviewlens --cov-report=term-missing` → **554 passed, 9 opt-in live
  skipped, 85.52% coverage**.

## Execution log — 2026-08-22 (`IMP-M4-013`, partial)

- Offline quality-gate suite: `uv run pytest tests\test_m4_evaluation.py
  tests\test_m4_quality.py tests\test_m4_commit.py tests\test_m4_enrichment.py
  tests\test_m4_enrichment_migration.py tests\test_m4_catalog_selection_prompt.py
  tests\test_m4_execution.py tests\test_m4_budget.py tests\test_openrouter.py -q
  -p no:cacheprovider --basetemp
  D:\project\reviewlens-data-platform\.tmp\pytest-m4-013-focused-2` → **61 passed**.
- A candidate must bind to the same `enrichment_version` as its aggregate-only
  evaluation report and meet initial M0 sentiment/aspect/topic/schema gates;
  otherwise the publish callback is not invoked. This is a fake-tested contract
  only: it calls neither a Snowflake owner procedure nor an active pointer, and
  remains partial until a private human-reviewed report and real AI candidate exist.
- Full local regression after artifact-lock refresh: `uv run pytest -q -p
  no:cacheprovider --basetemp
  D:\project\reviewlens-data-platform\.tmp\pytest-m4-013-full
  --cov=reviewlens --cov-report=term-missing` → **544 passed, 9 opt-in live
  skipped, 86.08% coverage**.

## Execution log — 2026-08-22 (`IMP-M4-014`)

- Offline observability contract suite: `uv run pytest tests\test_m4_observability.py
  tests\test_m4_commit.py tests\test_m4_budget.py tests\test_m4_enrichment.py
  tests\test_m4_execution.py tests\test_m4_quality.py -q -p no:cacheprovider
  --basetemp D:\project\reviewlens-data-platform\.tmp\pytest-m4-014-focused`
  → **41 passed**. The snapshot contains aggregate input/output token counts,
  exact committed USD, total/p95 latency, sanitized error-code counters and
  coverage only; it does not retain telemetry input references.
- Ruff format/lint, strict mypy and `dbt parse --warn-error` pass. The
  declared artifact lock was regenerated after the source change; deploy
  contract `tests\test_deploy.py` → **9 passed**. No OpenRouter, R2,
  Snowflake, Chroma or Docker call occurred.
- Full local regression after the lock refresh: `uv run pytest -q -p
  no:cacheprovider --basetemp
  D:\project\reviewlens-data-platform\.tmp\pytest-m4-014-full-rerun
  --cov=reviewlens --cov-report=term-missing` → **547 passed, 9 opt-in live
  skipped, 86.13% coverage**.

## Execution log — 2026-08-22 (`IMP-M4-015`)

- `docs/runbooks/M4_AI_ENRICHMENT_OPERATIONS.md` and a static safety contract
  define the M4 recovery procedure. The drill has four synthetic scenarios:
  pause/triage, bounded same-work retryable resume, versioned model change and
  a purge request that is fail-closed until a separately approved migration and
  restore drill exist. It preserves `FACT_REVIEW_BASE`, immutable raw source,
  release/rollback state and audit lineage; no direct delete command is supplied.
- Offline focused suite: `uv run pytest tests\test_m4_operations.py
  tests\test_m4_execution.py tests\test_m4_budget.py tests\test_m4_commit.py
  tests\test_m4_quality.py tests\test_m4_observability.py -q -p no:cacheprovider
  --basetemp D:\project\reviewlens-data-platform\.tmp\pytest-m4-015-focused-rerun-2`
  → **27 passed**. No OpenRouter, R2, Snowflake, Chroma or Docker runtime call
  occurred.
- Full local regression: `uv run pytest -q -p no:cacheprovider --basetemp
  D:\project\reviewlens-data-platform\.tmp\pytest-m4-015-full
  --cov=reviewlens --cov-report=term-missing` → **549 passed, 9 opt-in live
  skipped, 86.13% coverage**.

## Execution log — 2026-08-22 (`IMP-M4-012`, golden set human annotation completed)

- Completed human-in-the-loop annotation for all 200 items in `private_evaluation/m4_enrichment_v1/labels.jsonl` (200/200 marked `approved`).
- Validation command: `uv run reviewlens-golden-pack validate --labels-path private_evaluation\m4_enrichment_v1\labels.jsonl --split-seed m4-eval-holdout-v1`
  Output: `{"dataset_sha256": "0443fcbf381ba2b94ff69a72b29c9adeb814587815b151625a64038ed86217c6", "holdout_count": 40, "label_count": 200, "split_seed_sha256": "fa56914938ea13a121b8439623d44d91a9cf140aacf413601b005ae76201fecd", "status": "ready_for_private_predictions"}`
- Focused golden set & evaluation test suite: `uv run pytest tests/test_m4_golden_pack.py tests/test_m4_evaluation.py -q -p no:cacheprovider --basetemp D:\project\reviewlens-data-platform\.tmp\pytest-m4-012-annotation` → **9 passed**.
- Project status validator: `python .agents/skills/reviewlens-dev-workflow/scripts/validate_project_status.py --root .` → **PASS: 0 errors, 0 warning(s)**.

## Execution log — 2026-08-23 (`IMP-M4-007/012`, owner-authorized private pilot)

- DLP preflight approved **40/40** blind-holdout items with no provider request.
- One bounded real dispatch (200 completion tokens maximum, no retry) failed closed on the first item. No prediction/report was written; the aggregate-only budget ledger records **0.0004600 USD** and no pending reservation. No review, prompt or response body was logged.
- Offline diagnostics now retain only a sanitized provider HTTP status for a separately approved retry. `tests/test_openrouter.py tests/test_m4_execution.py tests/test_m4_holdout_pilot.py` → **22 passed**.

## Execution log — 2026-08-23 (`IMP-M4-007`, single-item diagnostic retry)

- Owner authorized exactly one DLP-approved real diagnostic retry. It completed with `private_diagnostic_succeeded`, confirming the pinned provider path returned a schema-valid structured result. The diagnostic intentionally persisted no prediction, review, prompt or response body.
- Aggregate budget ledger after both dispatches: **0.0006900 USD**, no pending reservation. TC-M4-013 is now `PASS`; full 40-item prediction/evaluation remains a separate owner-approved operation.

## Execution log — 2026-08-23 (`IMP-M4-012`, private prediction evaluator)

- Revalidated the human-approved private set: `uv run reviewlens-golden-pack
  validate --labels-path private_evaluation\m4_enrichment_v1\labels.jsonl
  --split-seed m4-eval-holdout-v1` → **200 labels**, **40 blind holdout**,
  `ready_for_private_predictions`. Output was aggregate-only.
- Added `reviewlens-golden-pack evaluate`: it requires exact holdout prediction
  IDs, validates each structured result, rejects training/missing/duplicate IDs,
  and writes an immutable aggregate-only report. It never reads the annotation
  queue or contacts a provider.
- Focused contract suite: `uv run pytest tests\test_m4_golden_pack.py
  tests\test_m4_evaluation.py tests\test_m4_quality.py -q -p no:cacheprovider
  --basetemp D:\project\reviewlens-data-platform\.tmp\pytest-m4-012-evaluator-focused`
  → **14 passed**. A real prediction/report remains pending owner authorization
  for the separate bounded provider pilot.

## Execution log — 2026-08-23 (`IMP-M4-012`, owner-authorized 40-item pilot)

- A fresh DLP preflight passed **40/40** blind-holdout items and verified that
  the private prediction path was absent before the one authorized batch.
- The batch stopped fail-closed with the sanitized code
  `AI_ENRICHMENT_SCHEMA_INVALID`. It did not create a prediction file or an
  evaluation report, and it made no automatic retry. No review, prompt,
  provider response body or row-level output was logged.
- The aggregate-only budget ledger is **0.0011500 USD** with no pending
  reservation. TC-M4-017 remains `PENDING`: the expected 40-prediction
  aggregate report was not produced. Any recovery dispatch requires fresh
  owner approval.
