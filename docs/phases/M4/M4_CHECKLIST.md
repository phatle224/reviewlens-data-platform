# M4 Checklist — DLP-approved review enrichment

| Attribute | Value |
|---|---|
| Phase status | `IN_PROGRESS` |
| Completed | 3/15 work items |
| Partial | 0/15 work items |
| Blocked | 0/15 work items |
| Not started | 12/15 work items |
| Last updated | 2026-08-21 |

## Implementation-plan checklist

| Work item | Status | Required outcome | Evidence / remaining work |
|---|---|---|---|
| IMP-M4-001 | `DONE` | Freeze enrichment JSON Schema, taxonomy and version-key code | `reviewlens.ai.enrichment` freezes schema v1, sentiment/aspect/topic taxonomy and SHA-256 version key across model/provider policy/prompt/schema/taxonomy; TC-M4-001/002 pass offline |
| IMP-M4-002 | `DONE` | Build `AI_ENRICHMENT_RUN/INVOCATION/RESULT_MAP` ledgers | In-memory replay/transition contract and additive secret-free `009_ai_enrichment_ledgers.sql` add exact append-only ledgers/grants; TC-M4-003/004/005 pass offline; migration is intentionally not applied live |
| IMP-M4-003 | `DONE` | Implement review-text DLP/minimization projection | Private pure projection redacts email/URL/phone/CPF-like values, drops natural IDs through opaque hash refs, and quarantines empty/over-limit/direct-ID/secret-like inputs; TC-M4-006…009 pass with synthetic Portuguese fixtures |
| IMP-M4-004 | `NOT_STARTED` | Snapshot OpenRouter catalog, provider policy and price | Requires an opt-in catalog request; no real review text |
| IMP-M4-005 | `NOT_STARTED` | Implement eligible new/changed/reused selector | Depends on M4-001/003 and pinned release refs |
| IMP-M4-006 | `NOT_STARTED` | Design Portuguese-aware prompt with delimited untrusted evidence | Depends on projection contract; injection fixtures required |
| IMP-M4-007 | `NOT_STARTED` | Implement OpenRouter structured-output client and rate limiter | Adapter exists from M1; M4 adds structured output, fakes and opt-in synthetic smoke |
| IMP-M4-008 | `NOT_STARTED` | Add schema/semantic validation and one repair path | Invalid output must fail closed; maximum one repair |
| IMP-M4-009 | `NOT_STARTED` | Add bounded retry, idempotency, permanent-error quarantine and resume | Requires ledger and provider error classification |
| IMP-M4-010 | `NOT_STARTED` | Token/cost estimator, 0.50 USD warning and 5 USD hard stop | Requires catalog price evidence; dispatch must stop at cap |
| IMP-M4-011 | `NOT_STARTED` | Build committed `AI_REVIEW_ENRICHED` and coverage projection | Validated results only; base review fact never removed |
| IMP-M4-012 | `NOT_STARTED` | Create stratified golden/holdout and semantic evaluator | Private/restricted label workflow; ≥20% blind holdout |
| IMP-M4-013 | `NOT_STARTED` | Add AI quality gate to release process | Bad AI candidate cannot publish |
| IMP-M4-014 | `NOT_STARTED` | Add tokens/cost/latency/error/coverage dashboards | Ledger aggregates reconcile without raw content |
| IMP-M4-015 | `NOT_STARTED` | Write pause/resume/model-change/purge runbook | Recovery drill required |

## Exit gate

Not yet evaluated. M4 completes only when the bounded pilot passes DLP, schema,
semantic, injection, budget and coverage gates; all failures are auditable; and
base review facts remain available when AI enrichment is absent or quarantined.
