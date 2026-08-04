# Implementation Plan — ReviewLens Data Platform

> Version 2.0 — Olist migration baseline
>
> Updated: 2026-08-05
>
> Execution model: one solo developer, one local runtime

## 1. How to use this plan

1. Read `docs/PROJECT_STATUS.md`, then the active phase checklist and tests.
2. Pick the smallest dependency-ready work item.
3. Add/update test cases before or with implementation.
4. Implement, run proportional offline/live gates and capture actual evidence.
5. Update checklist, test matrix and project status at session end.
6. Create an ADR when changing a source, security, release, provider or data-grain decision.

Status means evidence, not effort:

- `DONE`: artifact exists and all mandatory verification passed.
- `PARTIAL`: useful scope landed but acceptance remains.
- `BLOCKED`: a specific external/user input prevents progress.
- `DEFERRED`: intentionally moved with a destination and reason.
- `NOT_STARTED`: no implementation yet.

A ticket is ready only when its inputs, grain/security/license impact, acceptance
test and cost scope are known. It is done only when code/docs/tests/evidence and
cleanup are complete; an unrun live test is never recorded as pass.

## 2. Frozen delivery baseline

- Brand: ReviewLens; domain: Olist e-commerce review/delivery intelligence.
- Source: exactly nine Olist CSVs, CC BY-NC-SA 4.0.
- One non-secret `config/config.toml`; secrets only from environment/ignored `.env`.
- Private Cloudflare R2, Snowflake-only warehouse, dbt-snowflake, Airflow.
- OpenRouter chat/embeddings behind adapters; hard project budget 5 USD.
- Local persistent/versioned ChromaDB and loopback/authenticated Streamlit.
- Synthetic Olist-shaped data for CI/public evidence; raw/row-level Olist data outside Git.
- Private Olist R2/Snowflake processing after manifest/privacy gates; external AI
  only after DLP/minimized projection.
- Candidate release isolation and atomic data/index activation.

Dependency path:

```text
M0 decisions
  → M1 foundation
  → M2 Olist source/R2/Bronze
  → M3 Silver/Gold/data release
  → M4 enrichment
  → M5 vector/RAG ─┐
  → M6 Text-to-SQL ├→ M7 application → M8 hardening/demo
                   ┘
```

## 3. Target repository topology

```text
config/config.toml
src/reviewlens/
  config.py
  providers/
  synthetic/
  ingestion/
  audit/
  ai/
  rag/
  text_to_sql/
  app/
airflow/dags/olist_pipeline.py
dbt/reviewlens/
infra/cloudflare_r2/
infra/snowflake/
tests/{unit,contract,integration,live,fixtures,golden}/
docs/{ADR,data,phases,runbooks,images}/
```

Responsibility labels are hats held by the owner: Product, Data Architecture,
Data Engineering, Analytics Engineering, AI/Backend, App, Security/Platform and
QA/Ops.

## 4. Phase overview and demo checkpoints

| Phase | Outcome | Demo checkpoint |
|---|---|---|
| M0 | Product/data/security decisions | D0: PRD, ADRs, Olist manifest/license contract |
| M1 | Reproducible foundation | D0.5: config, private R2/Snowflake smoke, RBAC and tests |
| M2 | Olist → R2 → Bronze | D1: nine-table load, audit, quarantine and reconciliation |
| M3 | Silver/Gold/release | D2: trusted delivery/product/seller dashboard data |
| M4 | Review enrichment | D3: versioned sentiment/aspect/topic/summary with coverage/cost |
| M5 | RAG | D4: grounded qualitative Q&A with citations/refusal |
| M6 | Text-to-SQL | D4.5: safe quantitative Q&A with SQL/table/chart |
| M7 | Integrated app | D5: authenticated Streamlit portfolio experience |
| M8 | Hardening/demo | Final: repeatable full run, rollback, video/screenshots/runbooks |

## 5. M0 — Product, data and architecture decisions

M0 is complete and was re-baselined for Olist on 2026-08-05.

| Work item | Task | Dependency | Acceptance/evidence |
|---|---|---|---|
| IMP-M0-001 | Define solo responsibility hats, decision log and self-review gate | — | No owner `TBD`; session workflow documented |
| IMP-M0-002 | Profile source using metadata/checksums without exposing rows | Source access | Nine-file metadata manifest |
| IMP-M0-003 | Define complete-snapshot, release ID, replay/conflict/absence semantics | M0-002 | ADR-005 |
| IMP-M0-004 | Review source license, storage, transformations, publication, AI transfer | M0-002 | CC BY-NC-SA obligations explicit |
| IMP-M0-005 | Classify order/customer/seller/review/query/log data; define DLP/retention | M0-004 | Security/privacy matrix |
| IMP-M0-006 | Freeze nine required filenames, headers, keys and relationships | M0-002/003 | Olist source contract v1 |
| IMP-M0-007 | Define order analysis scope and review AI eligibility | M0-006 | Delivered/cancelled/unknown fixtures |
| IMP-M0-008 | Define snapshot history, corrections, deletion and timestamp policy | M0-003/006 | ADR-007 |
| IMP-M0-009 | Define KPI grains, formulas, denominators and multi-item allocation | M0-007/008 | Metric dictionary v1 |
| IMP-M0-010 | Freeze Chroma persistence, collection version and rebuild policy | Capacity constraints | ADR-004 |
| IMP-M0-011 | Freeze OpenRouter model candidates, provider policy, quota and budget | M0-004/005 | Model/evaluation baseline |
| IMP-M0-012 | Define app auth, personas and public-exposure boundary | Users defined | ADR-006 |
| IMP-M0-013 | Freeze local Docker + managed R2/Snowflake/OpenRouter topology | M0-012 | ADR-006 |
| IMP-M0-014 | Define versioned Silver/Gold/AI/index candidates and active pointer | M0-008/010/013 | ADR-005 |
| IMP-M0-015 | Define capacity, Snowflake/R2/OpenRouter/Chroma cost and SLO guards | M0-002/010/011 | SLO/budget baseline |
| IMP-M0-016 | Define enrichment schema/taxonomy/confidence/evaluation | M0-007/011 | AI output and golden-set plan |
| IMP-M0-017 | Define RAG/SQL supported questions, ambiguity/refusal and evaluation | M0-009/010/011 | Evaluation taxonomy |
| IMP-M0-018 | Threat-model ingestion, AI, RAG, SQL, auth, release and license | M0-012/014 | Negative-test backlog |
| IMP-M0-019 | Review all decisions, sync PRD/plan and approve M1 entry | M0-001…018 | M0 checklist complete; ADR-008 migration recorded |

Exit: 19/19 done; M0 tests 18 pass and 3 provider-runtime tests deferred to M1.

## 6. M1 — Foundation and developer platform

Objective: a clean clone can validate one local config, run deterministic
Olist-shaped fixtures and test scoped provider foundations without real source data.

| Work item | Task | Dependency | Acceptance/evidence |
|---|---|---|---|
| IMP-M1-001 | Repository/package/lock/lint/type/test bootstrap | M0 | Clean locked setup and tool commands pass |
| IMP-M1-002 | README, contribution, CODEOWNERS and PR/issue templates | M1-001 | Repository contract tests |
| IMP-M1-003 | Typed single-local config; environment/`.env` secrets only | M1-001 | Precedence, validation and secret-safe summary tests |
| IMP-M1-004 | Deterministic nine-CSV relational synthetic fixture generator | M0-006/007 | Exact headers, FK integrity and checksum determinism |
| IMP-M1-005 | Private R2 bucket/prefix/lifecycle/scoped-token contract | ADR-001 | Static + synthetic put/get/list/delete/anonymous-deny tests |
| IMP-M1-006 | Snowflake database/schemas/X-Small monitor/R2 stage/file formats | M1-005 | Idempotent DDL + synthetic LIST/COPY/reconcile/suspend |
| IMP-M1-007 | Least-privilege owner and eight service roles | M1-006 | Static/live positive and negative permission matrix |
| IMP-M1-008 | Dedicated service identities, app token and rotation/revocation skeleton | M1-007 | No shared/admin runtime identity; rotation smoke |
| IMP-M1-009 | Snowflake-only dbt scaffold, contracts/macros and local profile | M1-006/007 | `dbt parse/compile`; no DuckDB/multi-env profile |
| IMP-M1-010 | Airflow 3 `olist_pipeline` DAG/task/pool scaffold | M1-003/008 | Import has expected graph and no side effects |
| IMP-M1-011 | R2/Snowflake/OpenRouter/Chroma/audit/clock adapters and fakes | M1-001/003 | Provider boundary/error sanitization tests |
| IMP-M1-012 | Authenticated Streamlit shell, health/readiness and error state | M1-003/008 | Anonymous denied; local authenticated smoke |
| IMP-M1-013 | Audit schema migrations for ingestion/process/file/release/AI ledgers | M1-006 | Up/idempotency/compatibility tests |
| IMP-M1-014 | Structured logging, trace IDs and redaction library | M1-011/013 | Seeded secret/PII/review-text leak tests |
| IMP-M1-015 | CI lint/type/unit/contracts/dbt/security/dependency/container gates | M1-001/009/014 | Deliberate failing fixture blocks workflow |
| IMP-M1-016 | Non-root Docker images/entrypoints | M1-010/012/015 | Reproducible build and non-root smoke |
| IMP-M1-017 | Single-local Docker Compose and immutable artifact metadata | M1-016 | Compose config, local deploy and digest test |
| IMP-M1-018 | Metrics sink/health/service-error bootstrap | M1-014/017 | Synthetic metric visible end to end |
| IMP-M1-019 | Foundation runbook: setup, credentials, tests, cost stop and break-glass | M1-001…018 | Clean-machine solo dry run |
| IMP-M1-020 | Migrate active source baseline from Yelp to Olist across contract, config, fixtures, Snowflake, docs and diagram | ADR-008 | Nine-file manifest/license tests, no active Yelp contract, status/docs synchronized |

Exit: all mandatory offline gates pass; synthetic R2→Snowflake and RBAC live
evidence exists; raw Olist files remain ignored and M2 owns their explicit upload.

## 7. M2 — Olist ingestion, R2 and Bronze

Objective: one complete Olist snapshot is validated, privately archived, loaded
to nine immutable Bronze tables and physically reconciled.

| Work item | Task | Dependency | Acceptance/evidence |
|---|---|---|---|
| IMP-M2-001 | Implement machine-readable contracts for nine filenames/headers/types/keys | M1-004/020 | Valid/invalid compatibility fixtures |
| IMP-M2-002 | Discover local snapshot and completion manifest | M2-001 | Missing/extra/partial file scenarios |
| IMP-M2-003 | Build canonical manifest and `source_release_id` conflict detection | M2-002 | Runtime/order fields do not alter ID |
| IMP-M2-004 | Generate source object, batch, dataset-run, attempt and record IDs | M1-011/M2-003 | Determinism/uniqueness tests |
| IMP-M2-005 | Stream CSV parser with row/byte offsets, encoding and multiline quote handling | M2-001 | Large geolocation memory and malformed CSV tests |
| IMP-M2-006 | Validate required/type/range/status/timestamp and file-level constraints | M2-005 | Stable error taxonomy |
| IMP-M2-007 | Canonical record hash and duplicate/replay detection | M2-004/005 | Metadata excluded; same row stable |
| IMP-M2-008 | Run privacy/source-license preflight before real upload | M0-004/005, M2-002 | Manifest/attribution/DLP policy gate |
| IMP-M2-009 | Upload immutable original CSVs and verify R2 checksums | M1-005/008, M2-008 | No overwrite; downloaded hash matches |
| IMP-M2-010 | Write typed Parquet raw/quarantine partitions and manifests | M2-005/006/009 | Round-trip types/Unicode/newlines |
| IMP-M2-011 | Implement ingestion/file/source audit repositories and state transitions | M1-013/M2-004 | Lease/transition/idempotency tests |
| IMP-M2-012 | Quarantine row/file failures with source position and replay selector | M2-006/010/011 | Accepted+rejected+parse-failed reconciliation |
| IMP-M2-013 | Create nine Bronze DDLs/stages/grants with canonical metadata | M1-006/007/009, M2-001 | DDL/schema/RBAC tests |
| IMP-M2-014 | Implement Airflow-managed `COPY INTO` and load-history service | M2-010/013 | Query ID/replay/copy tests |
| IMP-M2-015 | Reconcile local source → R2 → Bronze rows/bytes/checksums | M2-011…014 | Zero unexplained loss |
| IMP-M2-016 | Implement DAG tasks `validate_source`, `upload_to_r2`, `copy_to_bronze` | M2-002…015 | Retry/resume/idempotency tests |
| IMP-M2-017 | Handle late/changed/duplicate-name/backfill and concurrent same-key cases | M2-016 | Scenario suite |
| IMP-M2-018 | Add ingestion metrics, alerts and replay/quarantine runbook | M2-011/015/016 | Operational drill and evidence |

Exit: nine source/Bronze counts reconcile, invalid rows are explainable, replay
is idempotent, no raw data is Git-visible, and the warehouse is suspended after demo.

## 8. M3 — Conformed Silver, Gold and atomic release

Objective: build trusted Olist relational models and business marts in isolated
candidates, then atomically activate one tested data release.

| Work item | Task | Dependency | Acceptance/evidence |
|---|---|---|---|
| IMP-M3-001 | Processing-run/input and candidate physical-reference ledger | M1-013/M2 | 1:N reprocess lineage tests |
| IMP-M3-002 | Versioned Silver candidate build/cleanup strategy | M3-001/ADR-005 | Concurrent isolation tests |
| IMP-M3-003 | dbt Bronze sources, freshness, contracts and docs | M2-013/014 | dbt source tests |
| IMP-M3-004 | Build `SIL_CUSTOMER`, minimized repeat-customer key and geography | M3-002/003 | Type/dedup/privacy tests |
| IMP-M3-005 | Build `SIL_GEOLOCATION_ZIP` deterministic centroid/quality model | M3-002/003 | No join multiplication fixtures |
| IMP-M3-006 | Build `SIL_ORDER` with status/time/scope/delivery flags | M0-007/008, M3-002/003 | Status/time/interval fixtures |
| IMP-M3-007 | Build `SIL_ORDER_ITEM` and `SIL_ORDER_PAYMENT` | M3-002/003/006 | Key/range/reconciliation tests |
| IMP-M3-008 | Build `SIL_PRODUCT`, translation and `SIL_SELLER` | M3-002/003/005 | Corrected length/category/location tests |
| IMP-M3-009 | Build `SIL_ORDER_REVIEW` and DLP eligibility flags | M0-005/007, M3-006 | Score/text/orphan/dedup tests |
| IMP-M3-010 | Reusable dbt DQ macros, severity and quarantine outputs | M3-004…009 | Critical selector blocks publish |
| IMP-M3-011 | Unknown members, late dimensions and deterministic corrections | M3-004…010 | Reorder/late/orphan deterministic |
| IMP-M3-012 | Create conformed date/customer/product/seller/geography dimensions | M3-004…011 | Grain/history/as-of tests |
| IMP-M3-013 | Create order/item/payment/review base facts | M3-006…012 | Key/count/reconciliation tests |
| IMP-M3-014 | Implement multi-item review attribution policy/bridge | M0-009/M3-013 | No silent double count |
| IMP-M3-015 | Build delivery, product-review, seller and customer marts | M3-012…014 | Metric dictionary fixtures |
| IMP-M3-016 | Build curated release-bound dashboard/SQL semantic views | M3-015 | Approved columns/metrics only |
| IMP-M3-017 | Candidate Gold build/test target | M3-015/016 | Candidate never mutates serving |
| IMP-M3-018 | Release events, immutable definition and CAS active pointer | M1-013/M3-017 | Failure/rollback/race tests |
| IMP-M3-019 | Request resolver pins explicit Silver/Gold physical refs | M3-018 | No mixed-release concurrency |
| IMP-M3-020 | Full-vs-incremental equivalence, metrics/lineage and runbook | M3-004…019 | Hash comparison + two-run drill |

Exit: all grains/metrics reconcile, critical dbt tests pass, failed candidates do
not affect serving and a tested release can activate/rollback atomically.

## 9. M4 — DLP-approved review enrichment

| Work item | Task | Dependency | Acceptance/evidence |
|---|---|---|---|
| IMP-M4-001 | Freeze enrichment JSON Schema, taxonomy and version-key code | M0-016/M1-011 | Schema/version unit tests |
| IMP-M4-002 | Build `AI_ENRICHMENT_RUN/INVOCATION/RESULT_MAP` ledgers | M1-013 | Idempotency/transition tests |
| IMP-M4-003 | Implement review-text DLP/minimization projection | M0-005/M3-009 | Identifier canary blocked/redacted |
| IMP-M4-004 | Snapshot OpenRouter catalog, provider policy and price | M0-011 | Slug/context/price evidence |
| IMP-M4-005 | Implement eligible new/changed/reused selector | M3-009/019, M4-001/003 | Deterministic counts |
| IMP-M4-006 | Design Portuguese-aware prompt with delimited untrusted evidence | M4-001/003 | Injection fixtures |
| IMP-M4-007 | Implement OpenRouter structured-output client and rate limiter | M1-011/M4-004 | Fakes + opt-in synthetic live smoke |
| IMP-M4-008 | Add schema/semantic validation and one repair path | M4-006/007 | Invalid enum/range/ID tests |
| IMP-M4-009 | Add bounded retry, idempotency, permanent-error quarantine and resume | M4-002/007/008 | Failure-injection tests |
| IMP-M4-010 | Token/cost estimator, 0.50 USD warning and 5 USD hard stop | M4-004/007 | Budget exhaustion test |
| IMP-M4-011 | Build committed `AI_REVIEW_ENRICHED` and coverage projection | M4-002…010 | No partial result leaks |
| IMP-M4-012 | Create stratified golden/holdout and semantic evaluator | M0-016/M4-011 | Metric report reproducible |
| IMP-M4-013 | Add AI quality gate to release process | M3-018/M4-012 | Bad candidate cannot publish |
| IMP-M4-014 | Add tokens/cost/latency/error/coverage dashboards | M1-018/M4-002 | Ledgers reconcile |
| IMP-M4-015 | Write pause/resume/model-change/purge runbook | M4-009…014 | Recovery drill |

Exit: DLP, schema, semantic, injection, budget and coverage gates pass for the
bounded pilot; failures remain auditable and do not remove base review facts.

## 10. M5 — Embeddings, ChromaDB and grounded RAG

| Work item | Task | Dependency | Acceptance/evidence |
|---|---|---|---|
| IMP-M5-001 | Provision persistent local Chroma and writer/reader boundaries | M1-008/017 | Restart and negative access tests |
| IMP-M5-002 | Freeze chunk/embedding/index version keys and catalog dimension | M0-010/M4-004 | Dimension/version tests |
| IMP-M5-003 | Build release-bound secure `AI.RAG_DOCUMENT` projection | M3-019/M4-011 | DLP/release leakage tests |
| IMP-M5-004 | Deterministic short/long review chunker with offsets/citations | M5-002/003 | Stable IDs/checksums |
| IMP-M5-005 | Batch embedding adapter with cache/retry/budget ledger | M1-011/M5-002/004 | Partial-failure/resume tests |
| IMP-M5-006 | Upsert versioned Chroma candidate collection | M5-001/005 | Idempotent duplicate tests |
| IMP-M5-007 | Reconcile expected chunk IDs/checksums and enforce coverage | M5-003/006 | ≥99.9%, no unexpected IDs |
| IMP-M5-008 | Validate server-side category/seller/geography/score/date/aspect filters | M5-003 | Filter leakage tests |
| IMP-M5-009 | Retrieval returns IDs/scores then fetches Snowflake evidence | M5-006/008 | Chroma cannot bypass policy |
| IMP-M5-010 | Prompt/context builder separates instructions from evidence | M5-009 | Injection/token-budget tests |
| IMP-M5-011 | Generate answer with claim-level citation/refusal validation | M5-010 | Citation/no-evidence/conflict tests |
| IMP-M5-012 | Build retrieval/RAG golden and security evaluation | M0-017/M5-011 | Recall@8/groundedness/refusal report |
| IMP-M5-013 | Atomic index activation bound to data release | M3-018/M5-007/012 | No mixed data/index version |
| IMP-M5-014 | Backup/rebuild/GC/purge and rollback runbook | M5-001/013 | Recovery/revocation drill |
| IMP-M5-015 | Add RAG latency/quality/cost/index-health metrics | M1-018/M5-011 | Dashboard/alerts visible |

Exit: index reconciliation, retrieval, citation, refusal, injection and version
binding gates pass; RAG never falls back to an ungrounded answer.

## 11. M6 — Guarded Text-to-SQL

| Work item | Task | Dependency | Acceptance/evidence |
|---|---|---|---|
| IMP-M6-001 | Build versioned semantic catalog from curated Gold views | M3-016/019 | Catalog snapshot/column allowlist |
| IMP-M6-002 | Define supported question, ambiguity and refusal contract | M0-017/M6-001 | Taxonomy fixtures |
| IMP-M6-003 | Implement prompt/schema returning SQL + assumptions/filters | M6-001/002 | Structured-output tests |
| IMP-M6-004 | Parse exactly one SELECT AST; deny DDL/DML/CALL/COPY/comments/multi-statement | M6-003 | Adversarial corpus |
| IMP-M6-005 | Enforce object/column/function/operator allowlists | M6-001/004 | Bypass negative tests |
| IMP-M6-006 | Resolve logical views to pinned release physical refs | M3-019/M6-005 | Candidate/current-name rejection |
| IMP-M6-007 | Add row cap, timeout and static cost guard | M6-004/005 | Cost-abuse tests |
| IMP-M6-008 | Harden Snowflake session/role/query tag/secondary-role settings | M1-007/008 | Runtime identity negative tests |
| IMP-M6-009 | Implement read-only execution and typed table/chart result | M6-006…008 | Empty/error/result contract |
| IMP-M6-010 | Allow at most one validated repair attempt | M6-009 | No-loop audit test |
| IMP-M6-011 | Build semantic/adversarial golden evaluator | M6-002…010 | Accuracy/security report |
| IMP-M6-012 | Add SQL trace, latency, rejection and warehouse-cost metrics | M1-018/M6-009 | Audit/metrics reconciliation |
| IMP-M6-013 | Write policy/catalog/model update and incident runbook | M6-011/012 | Recovery tabletop |

Exit: semantic target is met and zero unsafe query executes under the actual
service identity; every request pins one release and has an audit trail.

## 12. M7 — Streamlit analytics and integrated consumption

| Work item | Task | Dependency | Acceptance/evidence |
|---|---|---|---|
| IMP-M7-001 | Finalize authenticated app/service contracts and error taxonomy | M1-012/M3/M5/M6 | Contract tests |
| IMP-M7-002 | Implement auth/session expiry/rate-limit and operator separation | M1-008/012 | Negative authorization tests |
| IMP-M7-003 | Build release resolver and freshness/coverage banner | M3-019 | One request/one release tests |
| IMP-M7-004 | Implement shared date/geography/category/product/seller/score/aspect filters | M3-016 | Cross-page consistency tests |
| IMP-M7-005 | Build Executive Overview | M3-015/016 | Gold reconciliation |
| IMP-M7-006 | Build Delivery & Geography page | M3-015/M7-004 | Delay/on-time fixtures |
| IMP-M7-007 | Build Product & Category page | M3-014/015/M7-004 | Multi-item allocation labels/test |
| IMP-M7-008 | Build Seller Performance page | M3-015/M7-004 | Sample/rank fixtures |
| IMP-M7-009 | Build Review Explorer and RAG tab | M5/M7-001 | Citation/refusal UI tests |
| IMP-M7-010 | Build Text-to-SQL tab with SQL/table/chart/policy state | M6/M7-001 | Safe result rendering tests |
| IMP-M7-011 | Build DQ/Operations page for batch/release/quarantine/AI/cost | M2/M3/M4/M1-018 | Operator UAT |
| IMP-M7-012 | Implement explicit empty/error/partial/backend-unavailable states | M7-005…011 | State matrix tests |
| IMP-M7-013 | Add caching keyed by release/auth/filter/policy versions | M7-003/004 | Cross-release/auth leak tests |
| IMP-M7-014 | Add app telemetry without raw prompt/review leakage | M1-014/018 | Redaction tests |
| IMP-M7-015 | Run accessibility/responsive/performance and analytics UAT | M7-005…014 | UAT + p95 evidence |

Exit: all three consumption modes share one active release, reconcile to Gold,
enforce auth/policy and present honest failure/coverage states.

## 13. M8 — End-to-end orchestration, hardening and portfolio launch

| Work item | Task | Dependency | Acceptance/evidence |
|---|---|---|---|
| IMP-M8-001 | Complete `olist_pipeline` task graph, retries, timeouts and ownership | M2…M7 | DAG import/dependency tests |
| IMP-M8-002 | Wire source→Bronze→Silver→AI→Gold→index→publish with gates | M8-001 | Full fixture E2E |
| IMP-M8-003 | Add no-source/replay/backfill/resume/concurrent-run scenarios | M8-002 | Idempotency suite |
| IMP-M8-004 | Inject parser/dbt/AI/index/publish failures | M8-002 | Active release remains consistent |
| IMP-M8-005 | Run security suite: secrets, RBAC, R2, DLP, RAG, SQL, auth, dependency/container | M1…M7 | Zero critical finding |
| IMP-M8-006 | Run license/attribution and public-artifact data-leak review | ADR-008 | No raw/restricted leak; notice present |
| IMP-M8-007 | Benchmark full structured snapshot and bounded AI sample | M8-002 | Memory/latency/cost report |
| IMP-M8-008 | Validate Snowflake/R2/OpenRouter/Chroma hard/degrade actions | M8-007 | Suspend/pause/GC drills |
| IMP-M8-009 | Validate backup/rebuild/rollback/revocation and restore suppression | M3/M5 | Recovery drill evidence |
| IMP-M8-010 | Complete operator, replay, AI, RAG, SQL, cost-stop and break-glass runbooks | M8-003…009 | Solo dry run |
| IMP-M8-011 | Produce architecture/data lineage/test/evaluation/cost documentation | All | Links and evidence resolve |
| IMP-M8-012 | Record local demo video and redacted screenshots | M7/M8 gates | No raw/secret leak |
| IMP-M8-013 | Run clean-machine clone/setup/full synthetic demo | M8-010…012 | Reproducibility evidence |
| IMP-M8-014 | Final portfolio UAT, risk acceptance and repository release tag | M8-001…013 | All acceptance criteria pass |

Exit: all mandatory gates pass, resources are cleaned/suspended, public artifacts
are license-safe and the complete demo is reproducible from documented commands.

## 14. Test strategy by layer

| Layer | Minimum evidence |
|---|---|
| Config/repository | typed validation, precedence, secret/raw-data scans, clean bootstrap |
| Source/ingestion | nine headers, multiline CSV, checksums, replay, quarantine, bounded memory |
| Warehouse | dbt keys/relationships/grains/time/scope/metric/allocation/incremental tests |
| Release | candidate isolation, CAS activation, rollback, revocation and concurrency |
| AI | DLP canaries, schema/semantic golden, retry/idempotency, model/catalog/cost |
| RAG | chunk/reconcile, filter leakage, retrieval, citation, refusal, injection |
| Text-to-SQL | semantic execution plus AST/RBAC/session/cost adversarial suite |
| App | auth, release pinning, filters, states, reconciliation, accessibility/p95 |
| Ops | alerts, cleanup/suspend, backup/rebuild and full E2E failure injection |

## 15. Solo sequencing recommendation

Within the active M1, complete service identities (`IMP-M1-008`), then provider
adapters (`IMP-M1-011`), dbt (`IMP-M1-009`), Airflow (`IMP-M1-010`) and audit/
logging/CI/containers. Do not upload the real snapshot merely because credentials
work; M2-001…008 must first make the source contract, manifest and privacy gate
executable. Prefer the vertical slice order D1→D5 and keep every live command
opt-in, bounded and cleanup-safe.
