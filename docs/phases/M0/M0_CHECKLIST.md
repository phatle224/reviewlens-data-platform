# M0 Checklist — Product, Data and Architecture Decisions

| Thuộc tính | Giá trị |
|---|---|
| Phase status | `COMPLETE` |
| Completed | 19/19 work items |
| Partial | 0/19 work items |
| Blocked | 0/19 work items |
| Last updated | 2026-08-04 |

`M0` hoàn tất bằng các default an toàn và reversible. Terms đã được review với restrictive decision: chưa được upload Yelp Data thật lên R2/Snowflake, gửi tới OpenRouter hoặc public data/metrics nếu chưa xác nhận academic eligibility/Yelp approval. Non-secret account facts và live synthetic connectivity checks là M1 entry/runtime work, không được ghi giả là đã pass trong M0.

## Checklist theo implementation plan

| Work item | Status | Đã hoàn thành | Evidence / việc còn lại |
|---|---|---|---|
| IMP-M0-001 | `DONE` | Mô hình solo responsibility hats và self-review gate | PRD 1.1, implementation plan 1.1 |
| IMP-M0-002 | `DONE` | Fingerprint outer ZIP; exact 5 JSON files, sizes, row counts và sample fields | [Source profile](./M0_SOURCE_PROFILE.md) |
| IMP-M0-003 | `DONE` | Chốt baseline `FULL_SNAPSHOT`, checksum release identity và conflict rule | [ADR-005](../../ADR/ADR-005-ingestion-release-strategy.md) |
| IMP-M0-004 | `DONE` | Đã đọc bundled Terms 2023/2021 và ghi explicit restrictions cho cloud/LLM/publication | [Security/privacy](./M0_SECURITY_PRIVACY.md) |
| IMP-M0-005 | `DONE` | Classification, DLP, license-term deletion và restrictive retention baseline | [Security/privacy](./M0_SECURITY_PRIVACY.md) |
| IMP-M0-006 | `DONE` | Chốt exact 5 required JSON, derived attributes, optional photos và source fields baseline | [Source profile](./M0_SOURCE_PROFILE.md) |
| IMP-M0-007 | `DONE` | Restaurant scope v1 + UNKNOWN/hybrid rule | [Product/data baseline](./M0_PRODUCT_DATA_BASELINE.md) |
| IMP-M0-008 | `DONE` | SCD/correction/tombstone/time baseline | [ADR-007](../../ADR/ADR-007-scd-time-retention.md) |
| IMP-M0-009 | `DONE` | Metric dictionary v1 và denominator guardrails | [Product/data baseline](./M0_PRODUCT_DATA_BASELINE.md) |
| IMP-M0-010 | `DONE` | ChromaDB local persistence/version/rebuild decision | [ADR-004](../../ADR/ADR-004-chromadb-vector-store.md) |
| IMP-M0-011 | `DONE` | OpenRouter model candidates, version/cost/eval policy và catalog check | [AI evaluation](./M0_AI_EVALUATION_PLAN.md); live key smoke deferred M1 |
| IMP-M0-012 | `DONE` | Local/private auth boundary; public deployment gate | [ADR-006](../../ADR/ADR-006-solo-deployment-auth.md) |
| IMP-M0-013 | `DONE` | Local Docker services + managed R2/Snowflake/OpenRouter topology | [ADR-006](../../ADR/ADR-006-solo-deployment-auth.md) |
| IMP-M0-014 | `DONE` | Versioned Silver/Gold/AI/Chroma refs và active pointer | [ADR-005](../../ADR/ADR-005-ingestion-release-strategy.md) |
| IMP-M0-015 | `DONE` | Capacity, SLO, cost/degrade defaults accepted provisionally | [SLO/budget](./M0_SLO_BUDGET.md); actual account runway recorded M1 |
| IMP-M0-016 | `DONE` | Enrichment schema/evaluation approach và dataset sizing | [AI evaluation](./M0_AI_EVALUATION_PLAN.md) |
| IMP-M0-017 | `DONE` | RAG/SQL question/evaluation/security categories | [AI evaluation](./M0_AI_EVALUATION_PLAN.md) |
| IMP-M0-018 | `DONE` | Threat priorities và negative-test scope | [Security/privacy](./M0_SECURITY_PRIVACY.md), [test cases](./M0_TEST_CASES.md) |
| IMP-M0-019 | `DONE` | PRD/plan đồng bộ, ADR register, solo estimate và M1 entry inputs | [Decision register](./M0_DECISION_REGISTER.md), [user inputs](./M0_USER_INPUTS.md) |

## Artifact checklist

- [x] PRD và implementation plan phiên bản 1.1.
- [x] Source archive SHA-256 và outer inventory.
- [x] Required/derived/optional dataset decision.
- [x] Restaurant scope, SCD, timestamp và metric baselines.
- [x] R2, Snowflake, OpenRouter, ChromaDB ADRs.
- [x] Snapshot ingestion, immutable release và local/private deployment ADRs.
- [x] Security/privacy/retention baseline.
- [x] Capacity/SLO/budget baseline.
- [x] AI/RAG/Text-to-SQL evaluation plan.
- [x] M0 test cases và result status.
- [x] Bundled Yelp Terms review completed; restrictive decision recorded.
- [x] Inner TAR exact inventory, size, row count và sample top-level fields completed.
- [x] Snowflake account/live smoke explicitly deferred to M1 with synthetic-only rule.
- [x] R2 account/live smoke explicitly deferred to M1 with synthetic-only rule.
- [x] OpenRouter key/live smoke explicitly deferred to M1 without exposing secret.
- [x] Private/local, budget và model/sample defaults provisionally accepted; user may override before M1 execution.
- [x] User input template và no-secret instructions đã tạo.

## Exit gate

M0 exit gate result:

1. `TC-M0-017` Terms gate pass hoặc explicit restriction được ghi (`PASS` với restriction).
2. `TC-M0-018` source inner inventory pass.
3. `TC-M0-019` đến `TC-M0-021` được explicitly deferred sang M1 vì cần runtime secrets/account.
4. Safe defaults trong decision register là provisional accepted decisions; user override trước M1 sẽ tạo decision revision.
5. Không còn `BLOCKED` hoặc `PARTIAL`; M0 có đủ evidence để bắt đầu M1 bằng synthetic data.

Kết luận: `PASS — M0 COMPLETE`.
