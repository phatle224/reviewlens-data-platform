# M0 Checklist — Product, Data and Architecture Decisions

| Thuộc tính | Giá trị |
|---|---|
| Phase status | `COMPLETE` |
| Completed | 19/19 work items |
| Partial | 0/19 work items |
| Blocked | 0/19 work items |
| Last updated | 2026-08-05 |

M0 was re-baselined on 2026-08-05 after the source migration to Olist. All
active product, data, privacy and architecture decisions now use the nine-file
Olist CSV contract and CC BY-NC-SA 4.0 obligations.

## Checklist theo implementation plan

| Work item | Status | Completed outcome | Evidence |
|---|---|---|---|
| IMP-M0-001 | `DONE` | Solo responsibility hats and self-review gate | PRD, implementation plan |
| IMP-M0-002 | `DONE` | Metadata-only profile of nine local Olist CSVs | [Source profile](./M0_SOURCE_PROFILE.md) |
| IMP-M0-003 | `DONE` | Complete-snapshot, checksum identity and conflict semantics | [ADR-005](../../ADR/ADR-005-ingestion-release-strategy.md) |
| IMP-M0-004 | `DONE` | CC BY-NC-SA obligations and provider/publication boundary | [Attribution](../../DATA_ATTRIBUTION.md), [security](./M0_SECURITY_PRIVACY.md) |
| IMP-M0-005 | `DONE` | Data classification, DLP and retention baseline | [Security/privacy](./M0_SECURITY_PRIVACY.md) |
| IMP-M0-006 | `DONE` | Exact nine-file required source contract | [Source profile](./M0_SOURCE_PROFILE.md) |
| IMP-M0-007 | `DONE` | Order analysis scope and review eligibility v1 | [Product/data baseline](./M0_PRODUCT_DATA_BASELINE.md) |
| IMP-M0-008 | `DONE` | Snapshot history/correction/time baseline | [ADR-007](../../ADR/ADR-007-scd-time-retention.md) |
| IMP-M0-009 | `DONE` | E-commerce metric dictionary and denominator guardrails | [Product/data baseline](./M0_PRODUCT_DATA_BASELINE.md) |
| IMP-M0-010 | `DONE` | ChromaDB persistence/version/rebuild decision | [ADR-004](../../ADR/ADR-004-chromadb-vector-store.md) |
| IMP-M0-011 | `DONE` | OpenRouter model/version/cost/evaluation policy | [AI evaluation](./M0_AI_EVALUATION_PLAN.md) |
| IMP-M0-012 | `DONE` | Local/private authentication boundary | [ADR-006](../../ADR/ADR-006-solo-deployment-auth.md) |
| IMP-M0-013 | `DONE` | Local Docker + managed R2/Snowflake/OpenRouter topology | [ADR-006](../../ADR/ADR-006-solo-deployment-auth.md) |
| IMP-M0-014 | `DONE` | Versioned Silver/Gold/AI/Chroma release pointers | [ADR-005](../../ADR/ADR-005-ingestion-release-strategy.md) |
| IMP-M0-015 | `DONE` | Capacity, SLO and cost/degrade defaults | [SLO/budget](./M0_SLO_BUDGET.md) |
| IMP-M0-016 | `DONE` | E-commerce enrichment schema and evaluation plan | [AI evaluation](./M0_AI_EVALUATION_PLAN.md) |
| IMP-M0-017 | `DONE` | RAG/SQL question categories and refusal/security gates | [AI evaluation](./M0_AI_EVALUATION_PLAN.md) |
| IMP-M0-018 | `DONE` | Threat model and negative-test scope | [Security](./M0_SECURITY_PRIVACY.md), [tests](./M0_TEST_CASES.md) |
| IMP-M0-019 | `DONE` | Olist migration decision and M1 entry inputs synchronized | [ADR-008](../../ADR/ADR-008-olist-primary-dataset.md), [inputs](./M0_USER_INPUTS.md) |

## Artifact checklist

- [x] Olist source snapshot metadata manifest with nine checksums.
- [x] CC BY-NC-SA attribution/non-commercial/ShareAlike notice.
- [x] Required source files, keys, relationships and data risks.
- [x] Order/review scope, history, time and KPI baselines.
- [x] R2, Snowflake, OpenRouter, ChromaDB and local-deployment ADRs.
- [x] Security, privacy, DLP, retention, capacity and AI evaluation gates.
- [x] Olist primary-source migration ADR superseding active Yelp assumptions.

## Exit gate

`PASS — M0 COMPLETE`. Runtime connectivity evidence remains recorded in M1;
M0 does not claim provider access merely from account configuration.
