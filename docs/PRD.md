# PRD — ReviewLens Data Platform

> AI-Powered E-commerce Review Intelligence Platform
>
> Product requirements v2.0 — Olist migration baseline
>
> Updated: 2026-08-05
>
> Owner: Solo developer (Product/Data/AI/App/Ops responsibility hats)

## 1. Product summary

ReviewLens is a local portfolio data platform that transforms the nine-file
Olist Brazilian E-Commerce dataset into:

1. an immutable R2/Snowflake medallion pipeline;
2. trusted order, delivery, payment, product, seller, customer and review marts;
3. structured review enrichment with sentiment, aspects, topics and summaries;
4. grounded RAG answers backed by review/order citations;
5. guarded Text-to-SQL over curated Gold semantic views;
6. a Streamlit dashboard demonstrating data engineering, analytics and AI.

The product runs as one local demo. There is no staging, production or public
live URL. Source code and safe portfolio evidence may be public; raw Olist CSVs,
review text, row-level derived exports, embeddings and vector stores may not.

### 1.1 Problem

- Nine relational CSVs need reliable ingestion, keys, reconciliation and lineage.
- Order/review/product relationships create ambiguous grains and double-count risk.
- Delivery and payment timestamps/values require explicit metric semantics.
- Free-text review comments are useful but untrusted and privacy-sensitive.
- LLM output, embeddings and generated SQL require validation, versioning,
  citations, least privilege and cost controls.
- A portfolio demo must be reproducible and credible without a permanent cloud bill.

### 1.2 Vision

A reviewer should be able to follow one source snapshot from local manifest to
R2, Bronze, Silver, AI, Gold, Chroma and the app; reproduce every metric; inspect
quarantine/lineage; and verify that every AI answer is grounded and every SQL
query is read-only and release-bound.

## 2. Goals, non-goals and success metrics

### 2.1 Goals

| ID | Goal |
|---|---|
| G-01 | Ingest the complete nine-file Olist snapshot idempotently with zero unexplained record loss. |
| G-02 | Produce typed, tested and versioned Silver/Gold models in Snowflake with explicit relational grains. |
| G-03 | Enrich eligible review comments through OpenRouter under DLP, schema, quality and 5 USD budget gates. |
| G-04 | Provide consistent order, delivery, payment, rating, product, seller and geography KPIs. |
| G-05 | Answer qualitative questions with claim-level citations to authoritative review/order evidence. |
| G-06 | Answer quantitative questions through allowlisted, read-only Text-to-SQL. |
| G-07 | Demonstrate observability, lineage, RBAC, reproducibility, rollback and cost governance. |

### 2.2 Non-goals for MVP

- Crawling Olist, marketplaces or live commerce APIs.
- Real-time/streaming ingestion or operational order processing.
- Public anonymous SaaS, multi-tenancy, SSO or production SLA.
- Commercial use of Olist-backed data or artifacts.
- Predictive pricing, fraud scoring or customer targeting.
- Fine-tuning a model or allowing an LLM to execute arbitrary tools/SQL.
- Publishing raw review excerpts, customer/seller IDs, embeddings or full tables.

### 2.3 Success metrics

| Metric | MVP target |
|---|---:|
| Physical reconciliation | 100% explained as accepted/quarantined/parse-failed |
| Duplicate committed effect after replay | 0 |
| Critical dbt tests before publish | 100% pass |
| Valid enrichment outputs after bounded retry | ≥99% submitted eligible comments |
| Vector coverage of valid RAG documents | ≥99.9% |
| Citation precision for accepted factual claims | 100% |
| Unsafe SQL executed in adversarial suite | 0 |
| Warm dashboard p95 | ≤5 seconds on portfolio workload |
| OpenRouter project spend | ≤5 USD hard cap |

## 3. Users and core stories

| Persona | Need | Allowed surface |
|---|---|---|
| Portfolio viewer | Understand architecture, tests and outcomes | Video/screenshots, aggregate dashboard evidence, repository docs |
| Analyst | Explore orders, delivery, payment, products, sellers and review patterns | Gold dashboard, RAG, Text-to-SQL |
| Operator/owner | Run/replay pipeline, inspect DQ/cost and activate/rollback releases | Local operator pages, Airflow, audit views |
| Data/AI engineer hat | Develop contracts, models, prompts, evaluation and indexes | R2/Snowflake/Chroma/OpenRouter through scoped adapters |

Core stories:

| ID | Story |
|---|---|
| US-01 | As operator, I can validate a nine-file snapshot before any upload. |
| US-02 | As operator, I can replay a batch without duplicate committed effects. |
| US-03 | As analyst, I can reconcile source rows through Bronze, Silver and Gold. |
| US-04 | As analyst, I can compare delivery time, delay, freight and ratings by period, category, seller and geography. |
| US-05 | As analyst, I can ask what customers praise or complain about and receive grounded citations. |
| US-06 | As analyst, I can ask quantitative questions and receive a safe table/chart plus generated SQL. |
| US-07 | As operator, I can see freshness, quarantine, AI coverage, cost and release status. |
| US-08 | As owner, I can activate or roll back a tested release without mixed versions. |

## 4. Active source, license and privacy contract

### 4.1 Dataset

The only active real source is the
[Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce),
downloaded on 2026-08-05 and licensed under
[CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/).
The exact snapshot is identified in
[OLIST_SOURCE_MANIFEST.md](data/OLIST_SOURCE_MANIFEST.md).

The project MUST preserve attribution, non-commercial use, ShareAlike for
distributed adaptations, change indication and no-endorsement language. The
release process MUST verify [DATA_ATTRIBUTION.md](DATA_ATTRIBUTION.md).

### 4.2 Required files

| Logical dataset | Required file | Grain / minimum key | MVP treatment |
|---|---|---|---|
| Customer | `olist_customers_dataset.csv` | `customer_id`; repeat-buyer key `customer_unique_id` | Minimize/hash identifiers in serving layers; city/state/ZIP policy |
| Geolocation | `olist_geolocation_dataset.csv` | ZIP-prefix occurrence | Build deterministic ZIP centroid/quality model; prevent join multiplication |
| Order item | `olist_order_items_dataset.csv` | `order_id + order_item_id` | Type price/freight/timestamp; relate product/seller |
| Payment | `olist_order_payments_dataset.csv` | `order_id + payment_sequential` | Type method/installments/value; reconcile order value |
| Review | `olist_order_reviews_dataset.csv` | `review_id + order_id` | Score analytics; comment DLP/AI projection |
| Order | `olist_orders_dataset.csv` | `order_id` | Status and purchase/approval/carrier/customer/estimate timestamps |
| Product | `olist_products_dataset.csv` | `product_id` | Correct canonical `*_length` names in Silver; dimensions/DQ |
| Seller | `olist_sellers_dataset.csv` | `seller_id` | Minimized seller dimension and geography |
| Category translation | `product_category_name_translation.csv` | Portuguese category | English label with unknown fallback |

All nine files are required. A missing, duplicated, truncated, checksum-mismatched
or header-incompatible file blocks the candidate source release.

### 4.3 Processing and publishing boundary

- Raw files live locally in ignored `archive/` and privately in R2 only.
- Private R2/Snowflake processing requires the snapshot manifest and privacy scan.
- OpenRouter/embedding receives only `serving_safe_text` plus strictly necessary,
  non-identifying context after versioned DLP/minimization.
- Public evidence uses synthetic rows, aggregates, redacted screenshots and
  architecture/test reports; never raw comments or row-level exports.
- Review content is untrusted prompt data, never system instructions.

## 5. System flows

### 5.1 Batch flow

```text
local Olist CSV bundle
  → validate names/headers/types/checksums/completeness/privacy
  → create canonical source manifest and source_release_id
  → upload immutable source/raw/manifests to private R2
  → COPY INTO immutable Snowflake Bronze + audit/quarantine
  → dbt build isolated Silver candidate
  → DLP-approved review enrichment + validated AI candidate
  → build Gold candidate and RAG documents
  → embed/index into versioned Chroma collection
  → run DQ/AI/RAG/SQL/security/reconciliation gates
  → atomically activate data_release_id + index_version
```

### 5.2 RAG flow

```text
authenticated question + pinned active release
  → classify as qualitative
  → extract/validate allowlisted filters
  → vector search returns chunk_id + score
  → fetch authoritative serving-safe evidence from Snowflake
  → re-check release/policy/filter authorization
  → generate answer from delimited evidence
  → validate claims/citations or refuse
```

### 5.3 Text-to-SQL flow

```text
authenticated quantitative question + pinned release
  → semantic catalog + model SQL proposal
  → AST parse/SELECT-only/allowlist/function/limit/cost validation
  → map logical views to release-bound physical objects
  → execute under TEXT_TO_SQL_ROLE on isolated warehouse
  → return typed table/chart + SQL + trace metadata
```

Questions asking “why/what do comments say?” use RAG. Questions asking
“how many/average/top/trend?” use Text-to-SQL. Ambiguous questions ask for
clarification; no route may silently fabricate an answer.

## 6. Ingestion contract

### 6.1 Batch manifest

The canonical manifest contains:

```text
source_name, source_snapshot_date, source_release_id,
contract_version, manifest_version, created_at,
file_name, dataset_name, required, bytes, sha256,
expected_header, observed_rows, data_class, license_id
```

`source_release_id` hashes sorted content identity fields only. Runtime IDs,
paths and timestamps MUST NOT change it. Same identity is replay; same filename
with changed bytes is a new candidate; conflicting metadata for the same ID is
`SOURCE_RELEASE_CONFLICT`.

### 6.2 Record metadata

Every Bronze record MUST expose:

```text
source_release_id, ingestion_batch_id, dataset_run_id,
source_file_name, source_row_number, source_object_sha256,
record_hash, ingested_at, schema_version, raw_payload
```

### 6.3 R2 layout

```text
source/olist/<source_release_id>/<original filename>
raw/<dataset_name>/source_release_id=<id>/batch_id=<id>/part-*.parquet
quarantine/<dataset_name>/batch_id=<id>/error_code=<code>/part-*.parquet
manifests/source_release_id=<id>/manifest.json
```

Bucket public access is disabled. Writes use create-only/idempotent semantics;
an existing different checksum is never overwritten. Snowflake stage uses
`s3compat://`, scoped credentials and `AUTO_REFRESH=FALSE`; Airflow owns loads.

### 6.4 State machines

- Ingestion: `DISCOVERED → VALIDATED → UPLOADED → BRONZE_LOADED → RECONCILED`.
- Processing: `CREATED → SILVER_BUILT → AI_BUILT → GOLD_BUILT → INDEX_BUILT → TESTED`.
- Release: append-only events `CREATED/ACTIVATED/ROLLED_BACK/INVALIDATED/REVOKED`.

Terminal failure never mutates the active pointer. Retry creates a new attempt,
not duplicate committed data.

## 7. Snowflake medallion model

### 7.1 Schemas and naming

Database `REVIEWLENS`; schemas `BRONZE`, `SILVER`, `AI`, `GOLD`, `AUDIT`,
`QUARANTINE`. Candidate physical schemas/objects are release-addressable.
Serving code resolves logical names through an active pointer and never queries
mutable candidate objects.

### 7.2 Bronze

| Table | Grain |
|---|---|
| `BRZ_OLIST_CUSTOMERS_RAW` | source customer row |
| `BRZ_OLIST_GEOLOCATION_RAW` | source geolocation row |
| `BRZ_OLIST_ORDER_ITEMS_RAW` | source order-item row |
| `BRZ_OLIST_ORDER_PAYMENTS_RAW` | source payment row |
| `BRZ_OLIST_ORDER_REVIEWS_RAW` | source review row |
| `BRZ_OLIST_ORDERS_RAW` | source order row |
| `BRZ_OLIST_PRODUCTS_RAW` | source product row |
| `BRZ_OLIST_SELLERS_RAW` | source seller row |
| `BRZ_PRODUCT_CATEGORY_TRANSLATION_RAW` | source translation row |

Bronze is immutable, replay-safe and traceable to file/row/hash. The ingestion
role can insert but cannot update/delete.

### 7.3 Silver

| Model | Grain and rules |
|---|---|
| `SIL_CUSTOMER` | one conformed `customer_id`; hashed repeat-customer key; normalized location |
| `SIL_GEOLOCATION_ZIP` | one deterministic ZIP-prefix centroid with source count/quality flags |
| `SIL_ORDER` | one `order_id`; typed status/timestamps; analysis-scope and delivery flags |
| `SIL_ORDER_ITEM` | one `order_id + order_item_id`; positive price/freight checks |
| `SIL_ORDER_PAYMENT` | one `order_id + payment_sequential`; method/installment/value checks |
| `SIL_ORDER_REVIEW` | one deterministic review/order row; score 1–5; comment policy flags |
| `SIL_PRODUCT` | one product; corrected length fields, dimensions and translated category |
| `SIL_SELLER` | one seller; normalized location |
| `SIL_CATEGORY_TRANSLATION` | one source category with English/unknown fallback |

Orphans remain explainable through unknown members plus DQ flags; critical
contract violations quarantine/block publish. Geolocation and multi-item joins
MUST have tests preventing fact multiplication.

### 7.4 AI

`AI_REVIEW_ENRICHED` grain is one
`review_id + order_id + enrichment_version`. Required fields:

```text
review_id, order_id, source_record_hash, enrichment_version,
model_slug, prompt_version, schema_version, taxonomy_version,
sentiment, confidence, aspect_sentiments[], topics[],
summary, highlights[], dlp_policy_version,
status, error_code, input_hash, token_usage, latency_ms, created_at
```

Allowed sentiments: `positive`, `neutral`, `negative`, `mixed`. Aspects:
`product_quality`, `delivery`, `packaging`, `customer_service`, `price_value`,
`product_description`, `payment`, `other`.

`AI.RAG_DOCUMENT` is a release-bound secure projection containing only
serving-safe text, citation IDs, content hash, policy labels and allowlisted
filter metadata. Chroma returns `chunk_id + score`; authoritative text is fetched
again from Snowflake before answer generation.

### 7.5 Gold

| Object | Grain / purpose |
|---|---|
| `DIM_DATE` | calendar date and derived periods |
| `DIM_CUSTOMER` | minimized customer/repeat-buyer identity |
| `DIM_PRODUCT` | product/category/dimensions |
| `DIM_SELLER` | seller and coarse geography |
| `DIM_GEOGRAPHY` | approved ZIP/city/state hierarchy |
| `FACT_ORDER` | one order with status and delivery intervals |
| `FACT_ORDER_ITEM` | one order item with product/seller/price/freight |
| `FACT_PAYMENT` | one payment sequence |
| `FACT_REVIEW_BASE` | one valid review/order record independent of AI coverage |
| `FACT_REVIEW_ENRICHMENT` | one valid AI result/version |
| `MART_ORDER_DELIVERY` | period × geography/category/seller aggregates |
| `MART_PRODUCT_REVIEW` | product/category × period review/AI metrics with allocation labels |
| `MART_SELLER_PERFORMANCE` | seller × period orders/delivery/review metrics |
| `MART_CUSTOMER_OVERVIEW` | period/geography repeat and order behavior |

Published `FACT_REVIEW` is a left join from base to enrichment so missing AI
never removes a review from score KPIs. Multi-item review attribution uses a
versioned allocation policy and is never presented as a naturally additive fact.

## 8. Functional requirements

### 8.1 Ingestion and quality

| ID | Requirement | Acceptance |
|---|---|---|
| ING-001 | Discover exactly nine files and a completion marker/manifest. | Missing/extra/partial scenarios deterministic. |
| ING-002 | Validate header, encoding, required fields, types, ranges and timestamps. | Valid/invalid fixtures produce stable error codes. |
| ING-003 | Stream/chunk large CSVs with bounded memory. | Geolocation file benchmark stays under accepted memory envelope. |
| ING-004 | Generate stable source, batch, dataset-run, attempt and record IDs. | Reorder/runtime metadata does not change content IDs. |
| ING-005 | Archive immutable source and verify upload checksum. | Download hash equals local manifest; overwrite denied. |
| ING-006 | Quarantine row/file failures with source location and raw reference. | Accepted + rejected + parse-failed reconciles physical input. |
| ING-007 | COPY R2 objects into nine immutable Bronze tables idempotently. | Replay creates zero duplicate committed effect. |
| ING-008 | Support retry/backfill/concurrent same-key guard. | Failure-injection and race tests pass. |

### 8.2 Warehouse and releases

| ID | Requirement | Acceptance |
|---|---|---|
| DWH-001 | Bronze has canonical lineage metadata and immutable grants. | DDL/RBAC/row-lineage tests pass. |
| DWH-002 | Silver keys, types, relationships and DQ flags match contract. | dbt critical tests pass. |
| DWH-003 | Prevent geolocation and multi-item join multiplication. | Known-count fixtures reconcile exactly. |
| DWH-004 | Apply versioned order-analysis scope consistently. | Delivered/cancelled/unknown fixtures pass. |
| DWH-005 | Build Gold at declared grains with metric dictionary v1. | Metric fixture outputs match expected values. |
| DWH-006 | Full refresh and incremental build are equivalent. | Row/hash comparison report has no unexplained delta. |
| DWH-007 | Candidate builds are isolated and publish atomically. | Failed/concurrent candidate cannot change active pointer. |
| DWH-008 | Every serving request pins one data release. | No cross-release read in concurrency tests. |

### 8.3 AI enrichment

| ID | Requirement | Acceptance |
|---|---|---|
| AI-001 | Select only eligible, DLP-approved, new/changed comments. | Counts deterministic by source hash/version. |
| AI-002 | Use pinned model/prompt/schema/taxonomy/provider policy. | Version key changes whenever an input changes. |
| AI-003 | Require JSON Schema and semantic validation before commit. | Invalid enums/ranges/IDs fail closed. |
| AI-004 | Retry only transient/schema-repairable errors with bounded attempts. | No infinite retry; permanent errors auditable. |
| AI-005 | Persist invocation ledger, tokens, latency, cost and sanitized errors. | Spend/retry/coverage reconcile to submitted rows. |
| AI-006 | Stop new calls at 5 USD hard budget. | Budget test blocks dispatch while analytics remains available. |

### 8.4 Embedding and RAG

| ID | Requirement | Acceptance |
|---|---|---|
| EMB-001 | Deterministic chunking; one chunk for normal short comments, sentence split for long text. | Stable IDs and offsets after regeneration. |
| EMB-002 | Pin embedding model, dimension, input policy and chunk version. | Dimension/catalog mismatch blocks index. |
| EMB-003 | Use a separate Chroma collection per index version. | Candidate cannot be queried as active. |
| EMB-004 | Reconcile Snowflake expected chunks with Chroma IDs/checksums. | Coverage ≥99.9%; unexpected/missing IDs block publish. |
| RAG-001 | Validate category/seller/geography/score/date/aspect filters server-side. | Malicious/out-of-scope filters denied. |
| RAG-002 | Fetch authoritative release-bound evidence after vector search. | Chroma content cannot bypass Snowflake policy. |
| RAG-003 | Every accepted factual claim has a resolvable citation. | Citation precision 100%. |
| RAG-004 | Refuse no-evidence/conflicting/unauthorized questions. | Golden refusal precision/recall gate passes. |
| RAG-005 | Treat evidence as untrusted text and resist prompt injection. | Adversarial review corpus cannot alter instructions/tools. |

Citation resolves to internal `review_id`, `order_id`, release ID and permitted
excerpt. The dataset does not guarantee a public row URL, so the app MUST NOT
invent one.

### 8.5 Text-to-SQL

| ID | Requirement | Acceptance |
|---|---|---|
| SQL-001 | Generate SQL only over curated logical Gold semantic views. | Physical/candidate/source objects rejected. |
| SQL-002 | Parse one SELECT AST; deny DDL/DML/CALL/COPY/external functions/comments/multi-statement. | Adversarial corpus executes zero unsafe query. |
| SQL-003 | Enforce function/column/operator allowlists, limit, timeout and row cap. | Cost-abuse and exfiltration probes denied. |
| SQL-004 | Execute with `TEXT_TO_SQL_ROLE`, secondary roles off and isolated warehouse. | Direct write/cross-schema negative tests pass. |
| SQL-005 | Validate metric/time/filter ambiguity before execution. | Ambiguous questions ask for clarification. |
| SQL-006 | Allow at most one bounded repair attempt. | No loops; initial and repaired SQL auditable. |

### 8.6 Dashboard and orchestration

Required pages:

1. Executive Overview — orders, delivered/cancelled, GMV proxy, freight,
   payment reconciliation, rating, delivery and freshness.
2. Delivery & Geography — lead time, delay/on-time, state/city/category trends.
3. Product & Category — order items, price/freight and review/AI insights.
4. Seller Performance — volume, delivery and rating with sample thresholds.
5. Review Explorer/RAG — qualitative answers and citations.
6. Text-to-SQL — question, generated SQL, table/chart and policy result.
7. Data Quality & Operations — batch/release status, quarantine, coverage, cost.

| ID | Requirement | Acceptance |
|---|---|---|
| BI-001 | All pages show active release, freshness, filters and sample/coverage context. | Cross-page filter/release tests pass. |
| BI-002 | Empty/error/partial-AI/backend-unavailable states are explicit. | No state presents mock values as real. |
| BI-003 | Charts/tables reconcile with Gold and declared grain. | Golden fixture and UAT reconciliation pass. |
| ORCH-001 | DAG name is `olist_pipeline`; tasks have dependencies, retries, timeouts and pools. | Import has no network/credential side effect. |
| ORCH-002 | DAG handles no-new-source, retry/resume and candidate failure idempotently. | Scenario suite pass. |
| ORCH-003 | Publish occurs only after data/AI/index/security gates. | Failure injection leaves active release unchanged. |

### 8.7 Observability and audit

| ID | Requirement | Acceptance |
|---|---|---|
| OBS-001 | Structured logs include trace, source/batch/run/release IDs and redact secrets/restricted text. | Seeded secret/PII scan passes. |
| OBS-002 | Audit ledgers record ingestion, files, processing, release events/pointers and AI calls. | State transition and lineage tests pass. |
| OBS-003 | Metrics expose counts, duration, freshness, errors, quarantine, AI tokens/cost and warehouse use. | Synthetic end-to-end metrics visible. |
| OBS-004 | Alerts cover critical DQ, reconciliation, budget and stale release. | Failure fixtures trigger expected alert state. |

## 9. Security and governance requirements

Snowflake roles: `REVIEWLENS_OWNER`, `INGEST_ROLE`, `TRANSFORMER_ROLE`,
`AI_ENRICH_ROLE`, `VECTOR_INDEXER_ROLE`, `GOLD_BUILDER_ROLE`, `ANALYST_ROLE`,
`TEXT_TO_SQL_ROLE`, `RAG_ROLE`. Runtime identities never use admin/owner roles.

| ID | Requirement | Acceptance |
|---|---|---|
| SEC-001 | Least privilege and dedicated service identities. | Positive/negative role suite passes with secondary roles off. |
| SEC-002 | Secrets come only from process environment/ignored `.env` or outside-repo key path. | Config/repository scans expose no secret. |
| SEC-003 | R2 remains private and scoped. | Anonymous/account-list denial tests pass. |
| SEC-004 | Raw/restricted Olist artifacts stay out of Git/public evidence. | Tracked/untracked data-leak scan passes. |
| SEC-005 | DLP/minimization precedes external AI and vectorization. | Restricted-field canary never reaches provider/index. |
| SEC-006 | Attribution, NC, SA and change notice are release gates. | License contract tests and public-artifact review pass. |
| SEC-007 | App binds loopback and requires auth token. | Anonymous/remote-bind negative tests pass. |

## 10. Configuration and deployment

- One non-secret `config/config.toml`; no dev/staging/prod profiles.
- Credentials/passwords/API keys only in process environment or ignored `.env`.
- Local Docker Compose runs Airflow, ChromaDB and Streamlit; R2, Snowflake and
  OpenRouter are managed services accessed through adapters.
- `data_mode = "synthetic"` is the M1/default public-safe mode.
- M2 may explicitly switch to `data_mode = "olist"` after manifest/privacy gates.
- R2 bucket `reviewlens-data-dev`, private APAC/Standard.
- Snowflake Standard/AWS Singapore, X-Small, auto-suspend 60 seconds, resource monitor.
- OpenRouter hard cap 5 USD; Chroma local disk cap 5 GB.

| ID | Requirement | Acceptance |
|---|---|---|
| CFG-001 | Typed config rejects unknown/missing/unsafe settings. | Config unit/property tests pass. |
| CFG-002 | Secret-safe summary never prints credentials or private paths. | Seeded-secret test passes. |
| CFG-003 | Olist license contract cannot be weakened in config. | Commercial/MIT/no-attribution variants fail validation. |
| CFG-004 | Local demo cannot bind non-loopback by default. | Validation rejects unsafe host. |

## 11. Testing and evaluation strategy

Minimum gates:

- unit/property tests for parsing, IDs, state machines, filters and validators;
- contract tests for nine headers, R2 paths, Snowflake DDL/RBAC and app schemas;
- deterministic relational synthetic fixture with valid/invalid/edge variants;
- dbt source/unit/data tests for keys, relationships, grains and metrics;
- replay/backfill/concurrency/failure-injection integration suites;
- golden enrichment, retrieval, RAG refusal/citation and SQL semantic/adversarial sets;
- live tests opt-in, owner-operated, cost-bounded and cleanup/suspend in `finally`;
- secret, dependency, container and raw-data leak scans;
- status/checklist/test evidence updated after each coding session.

Golden AI minimums: enrichment 200 rows, retrieval 50 questions, RAG security
40 cases, SQL semantic 50 and SQL adversarial 50, with at least 20% blind holdout.

## 12. Milestones

| Phase | Outcome |
|---|---|
| M0 | Olist product/data/security/architecture decisions and source manifest |
| M1 | Reproducible foundation, config, credentials, roles, adapters, CI/Compose |
| M2 | Nine-file Olist ingestion → R2 → Bronze with audit/quarantine/reconciliation |
| M3 | Versioned Silver/Gold, metric dictionary and atomic data release |
| M4 | DLP-approved review enrichment and AI quality/cost gates |
| M5 | Versioned embeddings/Chroma and grounded RAG |
| M6 | Curated semantic catalog and guarded Text-to-SQL |
| M7 | Streamlit dashboard plus integrated analytics/RAG/SQL flows |
| M8 | End-to-end orchestration, hardening, evidence, demo and runbooks |

## 13. System acceptance criteria

The MVP is accepted only when:

1. a clean clone bootstraps from documented commands without secrets/data in Git;
2. the nine-file manifest validates and raw upload is private/immutable;
3. source → Bronze → Silver → Gold reconciles with no unexplained loss;
4. replay/backfill/failure/concurrent candidate tests protect active release;
5. dashboard values reconcile to Gold and show release/freshness/coverage;
6. enrichment meets schema/quality/budget/DLP gates;
7. Chroma IDs/checksums reconcile and RAG citations/refusals pass;
8. Text-to-SQL adversarial suite executes zero unsafe query;
9. service-role negative permission tests and secret/data leak scans pass;
10. attribution/non-commercial/ShareAlike notice is included in public evidence;
11. live resources are cleaned up/suspended and cost evidence is recorded;
12. local video/screenshots demonstrate the full approved vertical slice.

## 14. Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Multi-item review attribution duplicates metrics | High | Separate order-grain facts; versioned allocation; no additive claim |
| Geolocation ZIP join multiplies facts | High | Deterministic centroid model and row-count tests |
| Nullable/Portuguese review text reduces AI quality | Medium | Score-only analytics, language-aware prompt/eval, empty-text exclusion |
| Review contains identifiers or prompt injection | High | DLP/minimization, untrusted delimiters, no tools, adversarial tests |
| CC BY-NC-SA obligations omitted | High | Config + attribution + release checklist gate |
| Snowflake trial expires | Medium | X-Small/60s/monitor; prioritize M2/M3 vertical slice; export code/evidence |
| OpenRouter model/pricing changes | Medium | Runtime catalog snapshot, pinned version, hard budget, evaluation gate |
| Chroma local data loss | Medium | Rebuild from Snowflake map; versioned collections; backup active metadata |
| Generated SQL causes write/cost leak | High | AST allowlist + RBAC + isolated warehouse + timeout/row cap |

## 15. Decision log

| ID | Date | Decision | Status |
|---|---|---|---|
| DEC-001 | 2026-08-04 | Cloudflare R2 replaces AWS S3 | Accepted |
| DEC-002 | 2026-08-04 | Snowflake is the only warehouse | Accepted |
| DEC-003 | 2026-08-04 | OpenRouter provides chat/embedding through adapters | Accepted |
| DEC-004 | 2026-08-04 | ChromaDB is local, persistent and versioned | Accepted |
| DEC-005 | 2026-08-04 | One local/private runtime; no staging/production | Accepted |
| DEC-006 | 2026-08-04 | Candidate builds publish through atomic release pointers | Accepted |
| DEC-007 | 2026-08-05 | Least-privilege nine-role Snowflake hierarchy | Accepted |
| DEC-008 | 2026-08-05 | Olist replaces Yelp as the only active source | Accepted; [ADR-008](ADR/ADR-008-olist-primary-dataset.md) |
| DEC-009 | 2026-08-05 | CC BY-NC-SA release obligations and DLP-before-AI boundary | Accepted |

## 16. Definition of Done

A feature is `DONE` only when code/artifact exists, tests and relevant negative
gates pass, requirement/work/test IDs are traceable, security/license/cost impact
is recorded, docs/checklist/status are updated, and no required live test is
represented as pass without actual execution evidence.
