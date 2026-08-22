# M4 Checklist — DLP-approved review enrichment

| Attribute | Value |
|---|---|
| Phase status | `IN_PROGRESS` |
| Completed | 11/15 work items |
| Partial | 3/15 work items |
| Blocked | 0/15 work items |
| Not started | 1/15 work items |
| Last updated | 2026-08-22 |

## Implementation-plan checklist

| Work item | Status | Required outcome | Evidence / remaining work |
|---|---|---|---|
| IMP-M4-001 | `DONE` | Freeze enrichment JSON Schema, taxonomy and version-key code | `reviewlens.ai.enrichment` freezes schema v1, sentiment/aspect/topic taxonomy and SHA-256 version key across model/provider policy/prompt/schema/taxonomy; TC-M4-001/002 pass offline |
| IMP-M4-002 | `DONE` | Build `AI_ENRICHMENT_RUN/INVOCATION/RESULT_MAP` ledgers | In-memory replay/transition contract and additive secret-free `009_ai_enrichment_ledgers.sql` add exact append-only ledgers/grants; TC-M4-003/004/005 pass offline; migration is intentionally not applied live |
| IMP-M4-003 | `DONE` | Implement review-text DLP/minimization projection | Private pure projection redacts email/URL/phone/CPF-like values, drops natural IDs through opaque hash refs, and quarantines empty/over-limit/direct-ID/secret-like inputs; TC-M4-006…009 pass with synthetic Portuguese fixtures |
| IMP-M4-004 | `DONE` | Snapshot OpenRouter catalog, provider policy and price | Read-only public catalog client validates pinned enrichment slug, context, prompt/completion price and structured-output support; safe evidence snapshot confirms `google/gemini-2.5-flash-lite`, 1,048,576 context and 0.0000001/0.0000004 USD-token prices at 2026-08-21T10:08:04Z; no key/prompt/review is sent |
| IMP-M4-005 | `DONE` | Implement eligible new/changed/reused selector | Private deterministic selector compares hashed review lineage + approved input hash at one enrichment version; emits only `NEW`/`CHANGED` for dispatch, `REUSED` or explicit exclusion, and rejects conflicting hashed lineage |
| IMP-M4-006 | `DONE` | Design Portuguese-aware prompt with delimited untrusted evidence | Two-message Portuguese contract puts stable controls in `SYSTEM` and only DLP-approved evidence in `<REVIEW_UNTRUSTED>` user delimiters; synthetic injection fixture proves review instructions never enter control text |
| IMP-M4-007 | `PARTIAL` | Implement OpenRouter structured-output client and rate limiter | Strict `response_format.json_schema`, data-collection deny/no-fallback route and deterministic 2-per-second limiter pass fakes; opt-in synthetic-only live smoke exists but is not executed because it may incur OpenRouter token cost |
| IMP-M4-008 | `DONE` | Add schema/semantic validation and one repair path | Pydantic strict schema/semantic validator rejects malformed JSON, invalid/duplicate taxonomy, empty/restricted output; executor allows exactly one static-control repair then quarantines invalid output |
| IMP-M4-009 | `DONE` | Add bounded retry, idempotency, permanent-error quarantine and resume | In-memory executor persists retryable/succeeded/quarantined state per work ID; transient errors resume to the bounded max, permanent errors quarantine immediately and terminal calls are idempotent |
| IMP-M4-010 | `DONE` | Token/cost estimator, 0.50 USD warning and 5 USD hard stop | Deterministic token envelope uses catalog-pinned prices; a durable local aggregate-only reservation ledger warns at 0.50 USD/day and blocks before a request would exceed 5 USD. The synthetic live smoke now wraps every provider call in the guard; no live call was made. TC-M4-015 passes offline. |
| IMP-M4-011 | `DONE` | Build committed `AI_REVIEW_ENRICHED` and coverage projection | Private `AI_REVIEW_ENRICHED` DDL (`010`) and an atomic in-memory contract accept only hash-matched `ValidatedEnrichment` linked to a successful result-map; exact replay reuses, changed approved input replaces the current valid result, and coverage is aggregate-only. The base-review count is independent of valid/missing/ineligible AI coverage. Migration is deliberately not applied live; TC-M4-016 passes offline. |
| IMP-M4-012 | `PARTIAL` | Create stratified golden/holdout and semantic evaluator | Deterministic private-label splitter stratifies score/aspect/length/opaque-category/delivery outcome, reserves ≥20% blind holdout, evaluates only declared holdout IDs, and reports macro sentiment/aspect F1, topic micro F1 and schema pass rate. Synthetic regression passes; a real private human-reviewed set of at least 200 rows has not been created, so the real evaluation gate remains open. |
| IMP-M4-013 | `PARTIAL` | Add AI quality gate to release process | Version-bound fake-tested gate requires initial M0 metric thresholds and calls the publish callback only for the exact passing candidate; below-threshold, missing-evaluation and version-mismatch candidates are denied before publish. It is deliberately not yet wired to the live guarded Snowflake release transition because no private human-reviewed golden report or real AI candidate exists. |
| IMP-M4-014 | `DONE` | Add tokens/cost/latency/error/coverage dashboards | Aggregate-only terminal telemetry creates a reproducible dashboard payload for input/output tokens, exact committed USD, total/p95 latency, sanitized error-code counts and base/eligible/valid/missing coverage. It rejects duplicate opaque invocations, version/coverage drift and committed-budget mismatch; no raw content or row-level output is retained. TC-M4-019 passes offline. |
| IMP-M4-015 | `NOT_STARTED` | Write pause/resume/model-change/purge runbook | Recovery drill required |

## Exit gate

Not yet evaluated. M4 completes only when the bounded pilot passes DLP, schema,
semantic, injection, budget and coverage gates; all failures are auditable; and
base review facts remain available when AI enrichment is absent or quarantined.
