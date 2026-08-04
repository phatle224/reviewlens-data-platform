# Implementation Plan — ReviewLens Data Platform

| Thuộc tính | Giá trị |
|---|---|
| Phiên bản | 1.1 |
| Trạng thái | Draft đã đồng bộ cho solo implementation với Snowflake + R2 + OpenRouter + ChromaDB |
| Ngày cập nhật | 2026-08-04 |
| Nguồn yêu cầu | [PRD ReviewLens](./PRD.md) |
| Sơ đồ gốc | [Architecture plan](./images/plan.png) |
| Delivery Owner | Solo Developer |
| Technical Lead | Solo Developer |

Tài liệu này chuyển PRD thành trình tự triển khai có thể đưa trực tiếp vào epic, story và task. PRD vẫn là nguồn yêu cầu chính thức; khi implementation plan và PRD khác nhau, solo developer phải cập nhật quyết định/ADR và đồng bộ cả hai tài liệu trước khi code tiếp.

---

## 1. Cách sử dụng kế hoạch

### 1.1 Quy ước

| Ký hiệu | Ý nghĩa |
|---|---|
| `M0`…`M8` | Milestone/gate triển khai |
| `IMP-Mx-nnn` | Work item có thể tạo thành issue/task |
| `S` | Khoảng 0,5–1 net engineering day |
| `M` | Khoảng 2–3 net engineering days |
| `L` | Khoảng 4–5 net engineering days; nên tách thành subtask khi vào sprint |
| `XL` | Lớn hơn 5 net engineering days hoặc có uncertainty cao; bắt buộc spike/breakdown trước khi commit sprint |
| `Gate` | Không được bắt đầu phần phụ thuộc khi chưa đạt điều kiện này |

Effort chỉ là planning range, không phải cam kết lịch. Sau M0, solo developer phải re-estimate dựa trên source volume thật, Snowflake credit/trial còn lại, R2 topology, OpenRouter model/cost và capacity cá nhân.

### 1.2 Definition of Ready cho một ticket

Ticket chỉ được đưa vào sprint khi có:

- Requirement ID trong PRD và outcome cần đạt.
- Input/output contract hoặc mock/fixture tương ứng.
- Dependency đã hoàn thành hoặc có kế hoạch mock rõ ràng.
- Acceptance test có thể chạy được, không chỉ mô tả “hoạt động đúng”.
- Owner hat và self-review checklist; external review chỉ bắt buộc nếu project được public hoặc xử lý dữ liệu theo điều khoản yêu cầu bên thứ ba phê duyệt.
- Security/privacy/cost impact nếu ticket xử lý dữ liệu hoặc gọi external provider.
- Migration, rollback hoặc backward-compatibility note nếu thay schema/config.

### 1.3 Definition of Done cho một ticket

- Code, configuration, DDL/dbt/prompt thay đổi đã review.
- Unit/contract/integration/security tests liên quan pass.
- Requirement ID và test evidence được link trong issue/PR.
- Logs, metrics, error taxonomy và correlation IDs đã có.
- Documentation/runbook/data dictionary được cập nhật.
- Không chứa secret hoặc dữ liệu thật trái approval.
- Deploy được lên environment mục tiêu và có rollback path.

---

## 2. Delivery strategy

### 2.1 Nguyên tắc triển khai

1. **Chốt quyết định trước khi dựng hạ tầng khó đổi.** M0 phải giải quyết source semantics, restaurant population, license, privacy, SCD, ChromaDB persistence, auth, retention, SLO và budget.
2. **Synthetic-first.** Chỉ dùng fixture tổng hợp cho đến khi Security/Legal duyệt dữ liệu Yelp thật và external transfer.
3. **Vertical slice sớm.** M2 phải chạy được một dataset nhỏ Source → R2 → Snowflake Bronze → audit; M3 mở rộng thành Source → Gold; sau đó mới thêm AI.
4. **Idempotency trước performance.** Replay/crash semantics phải đúng trước khi tối ưu throughput.
5. **Build candidate, rồi mới publish.** Silver, AI, vector và Gold luôn dùng explicit version/reference; chỉ finalizer được đổi active release pointer.
6. **Security là code path.** Auth, RBAC, AST validation, DLP, release binding và negative tests không phải công việc “hardening cuối dự án”.
7. **Evaluation là release gate.** Model/prompt/index/semantic catalog không được rollout chỉ vì output parse được.

### 2.2 Dependency graph

```text
M0 Decisions
  ↓
M1 Foundation
  ↓
M2 Ingestion + Bronze
  ↓
M3 Versioned Silver + Core Gold + Release framework
  ├──────────────→ M6 Text-to-SQL ──────┐
  ↓                                      │
M4 AI Enrichment                         │
  ↓                                      │
M5 Embedding + RAG ──────────────────────┤
                                         ↓
                              M7 Dashboard + Integration
                                         ↓
                              M8 Production Hardening
```

Critical path mặc định: `M0 → M1 → M2 → M3 → M4 → M5 → M7 → M8`.

M6 có thể chạy song song với M4/M5 ngay khi Gold semantic views ở M3 ổn định. UI shell, auth spike, observability bootstrap và CI có thể bắt đầu từ M1 nhưng chỉ hoàn tất ở M7/M8.

### 2.3 Phạm vi thời gian tham khảo

| Mô hình đội | Planning range cho toàn bộ P0 |
|---|---|
| 5–6 người, có thể chạy 2–3 stream song song | Khoảng 28–36 tuần |
| 3 người, ít khả năng song song | Khoảng 48–64 tuần |
| Một developer full-time — full production-grade P0 | Khoảng 60–80+ tuần; nên cắt scope theo vertical slice |
| Một developer full-time — portfolio MVP có bounded sample | Khoảng 20–28 tuần nếu ưu tiên D1→D5 và hoãn production-only controls |

Range trên giả định cloud accounts và source sample sẵn có. Legal approval, procurement, network setup, labeling golden set hoặc thiếu Snowflake/Airflow experience có thể kéo dài critical path.

### 2.4 Frozen stack baseline cho MVP

| Boundary | Lựa chọn bắt buộc | Không implement trong MVP |
|---|---|---|
| Object storage | Cloudflare R2 Standard, private bucket, S3-compatible SDK | AWS S3/IAM/KMS/S3 event integration |
| Warehouse | Snowflake cho dev/staging/portfolio; `dbt-snowflake` | DuckDB/local warehouse fallback |
| Ingestion | Airflow batch `COPY INTO` từ R2 `s3compat://` stage, manual discovery/manifest | Snowpipe hoặc metadata auto-refresh |
| AI gateway | OpenRouter chat và embeddings qua Python adapter | Snowflake external function gọi provider trực tiếp |
| Vector store | ChromaDB local, persistent versioned collections | Cortex Search hoặc pgvector |

Các giá trị `R2_ACCOUNT_ID`, endpoint, Snowflake account/role/warehouse, OpenRouter model slug và ChromaDB path đến từ typed environment config/secret backend. Không ghi secret thật vào plan, `.env.example`, test fixture hoặc log. Snowflake trial/credit expiry được kiểm tra từ chính account và theo dõi như operational constraint; backlog không dựa vào một thời hạn trial cố định.

---

## 3. Solo topology và ownership hats

| Vai trò | Trách nhiệm chính | Milestone tập trung |
|---|---|---|
| Product Owner | Scope, restaurant population, KPI, UAT, product metrics | M0, M3, M7, M8 |
| Technical Lead/Data Architect | ADR, data/release model, cross-stream integration | M0–M8 |
| Data Engineer | Source, R2, Snowflake Bronze, Airflow, audit, replay/backfill | M1–M3, M8 |
| Analytics Engineer | dbt Silver/Gold, metric dictionary, tests, lineage | M0, M3, M7 |
| AI/Backend Engineer | Enrichment, embedding, RAG, Text-to-SQL services | M4–M6 |
| Frontend/App Engineer | Streamlit, auth integration, dashboard, AI UX | M1, M5–M7 |
| Platform/DevOps | IaC, environments, CI/CD, secrets, observability | M1, M8 |
| Security/Legal | License, data transfer, auth, DLP, retention, threat review | M0, M1, M4–M6, M8 |
| QA/Data QA | Fixtures, E2E, load, regression/evaluation evidence | M2–M8 |

Toàn bộ role trong bảng là các “mũ trách nhiệm” do cùng solo developer đảm nhiệm; cột `Owner` trong backlog không đại diện cho các thành viên khác nhau. Với portfolio private/local, các gate được ghi dưới dạng decision record và self-attestation có evidence. Nếu ứng dụng public, có user thật hoặc dữ liệu/điều khoản yêu cầu review độc lập, security/legal/launch approval phải được thực hiện bởi người phù hợp bên ngoài project.

---

## 4. Cấu trúc repository mục tiêu

```text
reviewlens-data-platform/
├── .github/
│   └── workflows/                 # CI, image build, deploy/promotion
├── apps/
│   └── streamlit/
│       ├── pages/                 # Dashboard, RAG, Text-to-SQL, DQ health
│       ├── components/
│       └── tests/
├── contracts/
│   ├── source/                    # Versioned source schemas
│   ├── ai/                        # Enrichment JSON Schemas
│   ├── serving/                   # RAG/SQL/application contracts
│   └── fixtures/                  # Valid/invalid synthetic samples
├── dags/
│   ├── yelp_pipeline.py
│   ├── task_groups/
│   └── tests/
├── dbt/
│   └── reviewlens/
│       ├── models/
│       │   ├── bronze_sources/
│       │   ├── silver/
│       │   ├── ai_intermediate/
│       │   ├── gold/
│       │   └── semantic/
│       ├── macros/
│       ├── seeds/
│       ├── snapshots/
│       └── tests/
├── docs/
│   ├── ADR/
│   ├── runbooks/
│   ├── data-dictionary/
│   ├── PRD.md
│   └── IMPLEMENTATION_PLAN.md
├── infra/
│   ├── cloudflare_r2/
│   ├── snowflake/
│   ├── chromadb/
│   ├── airflow/
│   ├── app/
│   └── monitoring/
├── prompts/
│   ├── enrichment/
│   ├── rag/
│   └── text_to_sql/
├── src/
│   └── reviewlens/
│       ├── config/
│       ├── ingestion/
│       ├── audit/
│       ├── enrichment/
│       ├── embeddings/
│       ├── rag/
│       ├── text_to_sql/
│       ├── serving/
│       ├── security/
│       └── observability/
├── tests/
│   ├── unit/
│   ├── contract/
│   ├── integration/
│   ├── e2e/
│   ├── evaluation/
│   ├── security/
│   └── load/
├── docker/
├── scripts/                        # Safe admin/backfill/reconciliation helpers
├── pyproject.toml
├── Makefile-or-task-runner
├── README.md
└── CODEOWNERS
```

Không bắt buộc dùng đúng tên công cụ quản lý dependency/task runner trước khi ADR tooling được duyệt, nhưng ranh giới module và test type nên được giữ ổn định.

---

## 5. Milestone overview

| Milestone | Outcome | Phụ thuộc | Effort tham khảo | Exit gate |
|---|---|---|---|---|
| M0 | Quyết định và contract được duyệt | PRD | 1–3 tuần | Không còn OQ P0 hoặc temporary default trái policy |
| M1 | Foundation, environments, CI, RBAC và skeleton chạy được | M0 | 2–4 tuần | Synthetic smoke test + negative permission tests pass |
| M2 | Source → R2 → Snowflake Bronze idempotent, audit/quarantine đầy đủ | M1 | 3–5 tuần | Replay/reconciliation/backfill tests pass |
| M3 | Versioned Silver/Gold, KPI và release framework | M2 | 4–6 tuần | dbt gates, metric fixtures, concurrency isolation pass |
| M4 | Incremental LLM enrichment có ledger/evaluation | M3 | 3–5 tuần | AI schema/semantic/cost/security gates pass |
| M5 | Versioned embeddings và grounded RAG | M4 | 3–5 tuần | Citation/groundedness/index/security gates pass |
| M6 | Safe, release-bound Text-to-SQL | M3 | 3–5 tuần | Semantic/adversarial/RBAC tests pass |
| M7 | Dashboard và ba consumption flows tích hợp | M3, M5, M6 | 3–5 tuần | Business UAT + `E2E-FIXTURE-001` pass |
| M8 | Production readiness, SLO, DR, cost, runbooks | M7 | 3–5 tuần | `E2E-SCALE-001` + solo launch evidence; external sign-off nếu public |

### 5.1 Demo checkpoints cho solo developer

| Checkpoint | Có thể demo | Chưa được coi là production-ready |
|---|---|---|
| D1 sau M2 | Business/review synthetic → R2 → Snowflake Bronze + audit/quarantine | Chưa có trusted analytics/AI |
| D2 sau M3 | Core rating/review/city/category dashboard từ versioned Gold | Chưa activate release thiếu AI/vector gates |
| D3 sau M4 | Sentiment/aspect/topic enrichment trên approved subset | Chưa có grounded chatbot/index |
| D4 sau M5/M6 | RAG có citation và safe Text-to-SQL trên staging | Chưa đạt full UAT/SLO/DR |
| D5 sau M7 | Hoàn chỉnh trải nghiệm MVP bằng `E2E-FIXTURE-001` | Chưa launch trước M8 |

Solo developer nên ưu tiên D1→D5 theo vertical slice, dùng bounded approved sample. Snowflake là warehouse duy nhất ngay từ dev; R2, Airflow, ChromaDB và Streamlit có thể chạy bằng account/service hoặc Docker local tương ứng. Không được bỏ SQL guardrails, data transfer approval hoặc auth nếu ứng dụng được expose cho người khác.

---

## 6. M0 — Product, data và architecture decisions

### 6.1 Mục tiêu

Loại bỏ các quyết định có thể làm thay đổi data model, security boundary, chi phí hoặc hạ tầng. M0 không tạo production pipeline; chỉ có spike/fixture synthetic cần thiết để ra quyết định.

Execution artifacts và trạng thái thực tế được quản lý tại [docs/phases/M0](./phases/M0/README.md). Mỗi phase tiếp theo MUST áp dụng cùng convention checklist + test cases trong [phase delivery convention](./phases/README.md).

### 6.2 Backlog M0

| ID | Công việc và artifact | Owner | Phụ thuộc | Verify / PRD | Size |
|---|---|---|---|---|---|
| IMP-M0-001 | Ghi nhận solo developer giữ Product/Technical/Data/AI/App/Ops hats; tạo decision log và self-review checklist, chỉ định external reviewer nếu project public | Product | — | Không còn owner `TBD`; mô hình solo được ghi rõ | S |
| IMP-M0-002 | Inventory source bằng approved sample/metadata; nếu chưa được phép dùng dữ liệu thật thì dùng published schema + synthetic equivalent | Data Eng/Security | Access approval | Profile report không vi phạm COMP-001; OQ-01/02/03 | M |
| IMP-M0-003 | Xác định `FULL_SNAPSHOT` hay `PARTIAL_FEED`, cadence, completion marker, source release ID và absence/deletion semantics | Data Architect | M0-002 | ADR-SOURCE-SEMANTICS; CON-002/005 | M |
| IMP-M0-004 | Legal review: ingest, storage, transformation, redistribution, citation, embedding và external LLM transfer | Legal/Security | M0-002 | Signed approval hoặc explicit restrictions; COMP-001 | L |
| IMP-M0-005 | Data classification cho business/review/user/tip/photo/query/log; retention và deletion obligations | Security/Data | M0-004 | Classification matrix + ADR-RETENTION; COMP-002 | L |
| IMP-M0-006 | Chốt required/optional/derived datasets và source contract version 1 skeleton | Data Architect | M0-002/003 | Contract inventory; CON-001 | M |
| IMP-M0-007 | Chốt restaurant inclusion taxonomy, `UNKNOWN`, hybrid rule và test examples | Product/Analytics | M0-002 | Versioned restaurant scope v1; OQ-16/DWH-012 | M |
| IMP-M0-008 | Chốt SCD/correction/tombstone strategy cho business/user và time semantics/DST | Data Architect | M0-003/006 | ADR-SCD + timestamp policy; DWH-010 | L |
| IMP-M0-009 | Chốt grain, formulas, timezone, denominator, sample threshold và owner cho KPI | Product/Analytics | M0-007/008 | Metric dictionary v1 + fixtures spec; DWH-006 | L |
| IMP-M0-010 | Khóa thiết kế ChromaDB local: persistence path, collection-per-index-version, metadata filters, backup/rebuild và retention | Architect/AI/Platform | Local capacity/budget constraints | ADR-VECTOR-CHROMA; OQ-06, EMB requirements | M |
| IMP-M0-011 | Khóa OpenRouter chat/embedding model slugs, provider routing, retention/training setting, quota và token budget | AI/Security/Finance | M0-004/005 | ADR-AI-OPENROUTER; OQ-09/11 | L |
| IMP-M0-012 | Chọn app authentication approach, persona/group mapping, SSO/RLS/masking scope | Security/App | Product users defined | ADR-AUTH; APP-008…010 | L |
| IMP-M0-013 | Chốt nơi chạy Airflow/Streamlit/ChromaDB, Docker volumes, registry, secret backend và network path tới R2/Snowflake/OpenRouter | Platform/Architect | Local/cloud constraints | ADR-DEPLOYMENT; OQ-10 | L |
| IMP-M0-014 | Chốt release strategy: versioned Silver/Gold schemas, AI map, vector index, events và active pointer | Data Architect | M0-008/010/013 | ADR-RELEASE; REL-001…007 | L |
| IMP-M0-015 | Khóa capacity envelope và budget thresholds cho Snowflake credits/trial expiry, R2 storage/operations, OpenRouter token và local ChromaDB disk | Product/Platform/Finance | M0-002/010/011/013 | Capacity sheet + approved SLO; NFR-001…004 | M |
| IMP-M0-016 | Định nghĩa enrichment taxonomy/schema/confidence và labeling/evaluation protocol | Product/AI/QA | M0-007/011 | AI output contract draft + labeling guide | L |
| IMP-M0-017 | Định nghĩa RAG/SQL supported question sets, no-evidence/ambiguity behavior và eval plan | Product/AI/Analytics | M0-009/010/011 | Eval specifications + question taxonomy | M |
| IMP-M0-018 | Threat model cho ingestion, RAG prompt injection, Text-to-SQL exfiltration, auth, release/purge | Security/Architect | M0-012/014 | Threat model + security test backlog | L |
| IMP-M0-019 | Solo review toàn bộ ADR/OQ, cập nhật PRD/plan và re-estimate M1–M8; lưu evidence thay cho meeting sign-off | Solo Developer | M0-001…018 | M0 decision/evidence checklist | M |

### 6.3 Exit criteria M0

- OQ-01…13, OQ-15 và OQ-16 có quyết định được owner phê duyệt; OQ-14 không chặn Streamlit MVP.
- Không dùng temporary default cho license, authentication, privacy, deletion hoặc retention.
- Có sample/source profile và synthetic fixtures đủ để phát triển khi data thật chưa được phép.
- Có ADR tối thiểu: source semantics, SCD/time, R2 storage, Snowflake-only warehouse, ChromaDB, OpenRouter, auth, deployment, release, retention.
- Snowflake account/region/edition đã được xác nhận; expiry/credit từ account được ghi lại, `X-SMALL` và auto-suspend baseline được chốt. Không tồn tại DuckDB profile hoặc warehouse fallback.
- Có capacity/SLO/budget baseline và milestone estimates cập nhật.

---

## 7. M1 — Foundation, environments và developer platform

### 7.1 Mục tiêu

Tạo nền móng có thể build/test/deploy lặp lại, đồng thời khóa ranh giới quyền trước khi có dữ liệu thật.

### 7.2 Backlog M1

| ID | Công việc và artifact | Owner | Phụ thuộc | Verify / PRD | Size |
|---|---|---|---|---|---|
| IMP-M1-001 | Khởi tạo repo structure, package metadata, dependency lock, lint/type/test commands | Tech Lead | M0-019 | Fresh clone chạy bootstrap/test command thành công | M |
| IMP-M1-002 | Tạo `README`, contribution guide, CODEOWNERS, PR/issue templates có requirement/test fields | Tech Lead | M1-001 | Sample PR qua checklist | S |
| IMP-M1-003 | Tạo centralized typed config cho dev/staging/prod; không chứa secret | Backend/Platform | M1-001, ADRs | Config validation tests; CFG-001/002 | M |
| IMP-M1-004 | Tạo synthetic source fixture generator và checked-in small fixture pack | QA/Data Eng | M0-006/007 | Deterministic regenerate + checksums | M |
| IMP-M1-005 | Provision private Cloudflare R2 Standard bucket/prefixes, scoped API token, lifecycle và public-access denial bằng IaC/config | Platform | ADR-STORAGE | Policy/connectivity tests; CON-003 | L |
| IMP-M1-006 | Provision Snowflake databases, schemas, `X-SMALL` warehouses, resource monitors và R2 S3-compatible external stages (`AUTO_REFRESH=FALSE`) | Platform/Data | M1-005, ADR-DEPLOYMENT | Idempotent deploy + R2 `LIST`/`COPY INTO` smoke; expiry/credits documented | L |
| IMP-M1-007 | Implement Snowflake roles: ingest, transformer, AI enrich, Gold builder, analyst, RAG và SQL; ChromaDB writer/reader credentials tách khỏi Snowflake RBAC | Security/Data | M1-006 | Positive/negative grant and credential suite; SEC-001 | L |
| IMP-M1-008 | Configure Snowflake/R2/OpenRouter/ChromaDB service credentials, app auth, secret backend và key rotation skeleton | Security/Platform | M0-012/013 | No shared/admin identity; secret retrieval/rotation smoke | L |
| IMP-M1-009 | Scaffold Snowflake-only dbt project, profiles-by-environment, naming macros, model contracts và CI schema isolation | Analytics Eng | M1-006 | `dbt parse/compile` bằng `dbt-snowflake`; không có DuckDB profile | M |
| IMP-M1-010 | Scaffold Airflow DAG `yelp_pipeline`, task interfaces, pools, config và local/staging deploy | Data Eng/Platform | M1-003/008 | DAG import test; no side effect | M |
| IMP-M1-011 | Scaffold Python adapters cho R2 S3-compatible storage, Snowflake, OpenRouter chat/embeddings, ChromaDB, audit và clock/ID generation | Backend/Data | M1-001/003 | Unit tests với fakes; provider boundaries không hard-code model/secret | L |
| IMP-M1-012 | Scaffold Streamlit app, authenticated shell, health/readiness page và error boundary | App/Security | M0-012, M1-003 | Anonymous denied; authenticated smoke | L |
| IMP-M1-013 | Tạo audit schema migrations cho ingestion/process/file/release event/pointer/invocation ledgers | Data Architect | ADR-RELEASE, M1-006 | Migration up/down/compatibility test | L |
| IMP-M1-014 | Tạo structured logging, trace/correlation library và redaction filter dùng chung | Platform/Backend | M0-005/018 | Seeded secret/PII log tests | M |
| IMP-M1-015 | Tạo CI workflow: lint, type, unit, contracts, dbt compile, secret/dependency/container scan | Platform | M1-001/009 | Deliberate failing fixture blocks merge; DEP-001 | L |
| IMP-M1-016 | Tạo Docker images/runtime entrypoints cho ingestion/Airflow/app components | Platform | M1-001/010/012 | Reproducible image build + non-root smoke | M |
| IMP-M1-017 | Tạo environment deployment skeleton và immutable artifact tagging | Platform | M1-015/016 | Deploy dev + artifact digest + rollback smoke | L |
| IMP-M1-018 | Bootstrap metrics sink/dashboards cho health, CI/deploy và service errors | Platform | M1-014/017 | Synthetic metric/log visible end-to-end | M |
| IMP-M1-019 | Viết foundation/runbook: bootstrap, Snowflake/R2/OpenRouter credentials, Chroma volume, local test, deploy, cost stop và break-glass | Platform/Tech Lead | M1-001…018 | Clean-machine solo dry run | M |

### 7.3 Exit criteria M1

- Fresh checkout có thể bootstrap, chạy tests và build image bằng tài liệu.
- Dev environment provision được từ code; staging/prod config tách biệt.
- Snowflake là warehouse dev đang hoạt động; R2 external stage `LIST`/`COPY INTO` pass, warehouse auto-suspend và resource monitor đã bật.
- Snowflake negative permission tests pass; không service nào dùng admin/shared identity.
- App không anonymous; secret/PII không xuất hiện trong repo/image/log fixtures.
- DAG/dbt/app skeleton deploy được nhưng chưa xử lý dữ liệu thật nếu compliance gate chưa mở.

---

## 8. M2 — Ingestion, Cloudflare R2 và Snowflake Bronze

### 8.1 Mục tiêu

Hoàn thiện luồng idempotent `source → validate → archive/Parquet → Bronze → audit/quarantine`, hỗ trợ replay, late file và backfill.

### 8.2 Backlog M2

| ID | Công việc và artifact | Owner | Phụ thuộc | Verify / PRD | Size |
|---|---|---|---|---|---|
| IMP-M2-001 | Hoàn thiện source contracts cho 7 dataset, required/optional/derived và compatibility rules | Data Eng/Architect | M0-006, M1-004 | Contract fixtures valid/invalid; CON-001 | L |
| IMP-M2-002 | Implement source discovery, completion marker và manifest loader | Data Eng | M2-001 | Partial upload/file missing tests; ING-001 | M |
| IMP-M2-003 | Implement canonical manifest fingerprint và `SOURCE_RELEASE_CONFLICT` detection | Data Eng | M2-002 | Ordering/runtime fields không đổi ID; conflict fixture fails | M |
| IMP-M2-004 | Implement IDs: source object, batch, dataset run, ingestion attempt và stable metadata | Data Eng | M1-011, M2-003 | Deterministic/uniqueness tests; CON-002 | M |
| IMP-M2-005 | Implement Python streaming JSON/JSONL parser với bounded Pandas/chunk processing, line/byte offsets và Unicode/emoji | Data Eng | M2-001 | Malformed/long/full-size memory tests | L |
| IMP-M2-006 | Implement schema/type/range/empty/truncate validation và error taxonomy | Data Eng | M2-001/005 | ING-002/008 fixtures pass | L |
| IMP-M2-007 | Implement canonical record hashing và duplicate/replay detection | Data Eng | M2-004/005 | Same payload stable hash; metadata excluded | M |
| IMP-M2-008 | Implement immutable source archive upload và checksum verification | Data Eng/Platform | M1-005/008 | Download checksum equals source; no overwrite | M |
| IMP-M2-009 | Implement Parquet/Snappy writer theo dataset/date/batch với schema metadata | Data Eng | M2-005/006 | Round-trip types/Unicode/nested data | L |
| IMP-M2-010 | Implement R2 raw/quarantine/manifest writers qua S3-compatible SDK và private-access/lifecycle checks | Data Eng | M2-008/009 | Path/policy contract tests; CON-003 | M |
| IMP-M2-011 | Implement `AUDIT.INGESTION_RUN`, `SOURCE_RELEASE_OBJECT`, `FILE_LOAD` repositories/state transitions | Data Eng | M1-013, M2-004 | Allowed/invalid transition + lease tests | L |
| IMP-M2-012 | Implement row/file quarantine, raw reference, error code và replay selection | Data Eng | M2-006/010/011 | Physical reconciliation includes parse failures | L |
| IMP-M2-013 | Tạo Bronze DDL, file formats, R2 `s3compat://` stages và canonical metadata columns cho 7 tables | Data/Analytics | M1-006/009, M2-001 | DDL/grant/schema/stage tests | L |
| IMP-M2-014 | Implement Airflow-managed `COPY INTO` service và load history/idempotency | Data Eng | M2-010/013 | Copy/replay/query ID tests; DWH-001/002 | L |
| IMP-M2-015 | Implement source → R2 → Snowflake Bronze reconciliation theo row/bytes/checksum | Data Eng/QA | M2-011…014 | Zero unexplained loss; OBS-002 | M |
| IMP-M2-016 | Implement Airflow tasks `validate_source`, `upload_to_r2`, `copy_to_bronze` | Data Eng | M2-002…015 | Task retry/resume/idempotency tests | L |
| IMP-M2-017 | Implement late-arriving file, changed-same-name, duplicate-content-name và backfill flows | Data Eng/QA | M2-016 | ING-005/006 scenario suite | L |
| IMP-M2-018 | Implement no-new-source behavior và concurrent same-key guard | Data Eng | M2-016 | `NO_NEW_SOURCE` no side effect; ORCH-002/008 | M |
| IMP-M2-019 | Tạo ingestion operational metrics/alerts và DQ/quarantine queries | Platform/Data | M2-011/015/016 | Counts, duration, errors, freshness visible | M |
| IMP-M2-020 | Viết ingestion replay/backfill/quarantine/runbook | Data Eng/Ops | M2-017/019 | Tabletop recovery drill | M |

### 8.3 Exit criteria M2

- `E2E-INGESTION-FIXTURE` chạy cả 7 dataset synthetic từ file tới Bronze.
- `physical = accepted + parsed_quarantined + parse_failed` cho mọi dataset/file parse được.
- Replay cùng source không tăng Bronze row; same-name/new-content và backfill tạo lineage đúng.
- Source archive/Parquet/quarantine/manifest đúng path, encryption và lifecycle policy.
- Bronze không update/delete qua `INGEST_ROLE`; rebuild input từ archive/Bronze được chứng minh.

---

## 9. M3 — Versioned Silver, core Gold và release framework

### 9.1 Mục tiêu

Biến Bronze thành trusted data models có test và xây release-addressable Gold không bị nhiễm giữa concurrent source/backfill runs.

### 9.2 Backlog M3

| ID | Công việc và artifact | Owner | Phụ thuộc | Verify / PRD | Size |
|---|---|---|---|---|---|
| IMP-M3-001 | Implement `AUDIT.PROCESSING_RUN` và `PROCESSING_INPUT`; tạo `processing_run_id` | Data Eng | M1-013, M2 audit | Ingestion 1:N processing/reprocess lineage test | M |
| IMP-M3-002 | Implement versioned `SILVER_RUN_<processing_run_id>` clone/build/cleanup strategy | Data/Platform | ADR-RELEASE, M3-001 | Concurrent run isolation; DWH-013/REL-006 | L |
| IMP-M3-003 | Khai báo dbt Bronze sources, freshness và metadata tests | Analytics Eng | M2-013/014 | dbt source tests/docs pass | M |
| IMP-M3-004 | Xây `SIL_BUSINESS` và normalized `SIL_ATTRIBUTES` | Analytics Eng | M2 contracts, M3-002/003 | Type/dedup/nested fixtures pass | L |
| IMP-M3-005 | Xây `SIL_REVIEW` với key, stars/text/date, orphan và DQ flags | Analytics Eng | M3-002/003 | Unique/range/relationship fixtures pass | L |
| IMP-M3-006 | Xây minimized/pseudonymous `SIL_USER` | Analytics/Security | M0-005, M3-002/003 | Restricted fields absent; join stable | M |
| IMP-M3-007 | Xây `SIL_CHECKIN`, explode event timestamps và timezone assumptions | Analytics Eng | M0-008, M3-002/003 | Offset/naive/DST/dedup fixtures | L |
| IMP-M3-008 | Xây `SIL_TIP`; giữ photo Bronze-only và coverage metadata | Analytics Eng | M3-002/003 | Key/hash/relationship tests | M |
| IMP-M3-009 | Implement restaurant scope v1 trong Silver | Analytics/Product | M0-007, M3-004 | In/out/unknown/hybrid fixtures; DWH-012 | L |
| IMP-M3-010 | Tạo reusable dbt DQ macros, critical/warning severity và quarantine outputs | Analytics Eng | M3-004…009 | Intentional critical fail blocks selector | L |
| IMP-M3-011 | Implement unknown member, late dimension và deterministic dedup rules | Analytics Eng | M3-004…010 | Reordered/late/orphan results deterministic | M |
| IMP-M3-012 | Tạo `DIM_DATE`, `DIM_BUSINESS`, `DIM_USER` theo SCD/time ADR | Analytics Eng | M0-008, M3-004/006/009 | SCD/correction/as-of fixtures | L |
| IMP-M3-013 | Tạo `FACT_REVIEW_BASE` và `FACT_CHECKIN` chỉ cho in-scope restaurants | Analytics Eng | M3-005/007/009/012 | Grain/key/count reconciliation | L |
| IMP-M3-014 | Tạo category/aspect/topic supporting bridge/child structures; aspect/topic dùng placeholder contract đến M4 | Analytics Eng | M3-009/013 | No double-count category fixtures | M |
| IMP-M3-015 | Tạo core `MART_BUSINESS_PERFORMANCE`, `MART_CATEGORY_TRENDS`, `MART_CITY_OVERVIEW` | Analytics Eng | M3-012…014 | Metric dictionary fixtures | XL |
| IMP-M3-016 | Tạo release-bound semantic views cho dashboard/Text-to-SQL | Analytics Eng | M3-015 | Only approved columns/metrics exposed | L |
| IMP-M3-017 | Implement versioned `GOLD_RELEASE_<data_release_id>` clone/build/test target | Data/Analytics | ADR-RELEASE, M3-002/015 | Candidate không mutate serving target | L |
| IMP-M3-018 | Implement `DATA_RELEASE_EVENT`, immutable `DATA_RELEASE` definition và CAS `ACTIVE_RELEASE_POINTER` | Data/Backend | M1-013, M3-017 | Failure/rollback/concurrent activation tests | XL |
| IMP-M3-019 | Implement release binding resolver cho explicit Silver/Gold physical refs | Backend/Data | M3-002/017/018 | One request/run resolves one version | L |
| IMP-M3-020 | Implement `INVALIDATED`/`REVOKED` activation guard skeleton | Security/Data | M0-005, M3-018 | Revoked candidate cannot activate/rollback | M |
| IMP-M3-021 | Implement Airflow `dbt_build_silver`, `dbt_test_silver`, core Gold build/test wiring | Data/Analytics | M3-002…020 | Fail-closed selector/dependency tests | L |
| IMP-M3-022 | Chứng minh incremental vs full refresh equivalence cho Silver/Gold | Analytics/QA | M3-004…017 | Hash/row comparison report; DWH-009 | L |
| IMP-M3-023 | Chạy two-run interleaving test cho release thường và backfill | QA/Data | M3-021/022 | Zero cross-run contamination; ORCH-011 | L |
| IMP-M3-024 | Publish dbt docs, lineage, model owner và core data dictionary | Analytics Eng | M3-004…023 | Public model description/test/owner coverage 100% | M |

### 9.3 Exit criteria M3

- Mỗi processing run có isolated Silver target và explicit lineage về source objects/Bronze.
- Hai runs khác nhau chạy xen kẽ không làm AI/Gold input bị trộn.
- Core review/rating KPI dùng mọi valid in-scope review, không phụ thuộc LLM.
- Restaurant scope, SCD, timezone, orphan và category double-count rules có fixtures pass.
- Candidate Gold không làm thay đổi active serving data; activation/rollback/revocation guard đã có test.
- dbt critical tests, docs và full-vs-incremental equivalence pass.
- M3 chỉ chứng minh core candidate/release framework bằng fixture; không activate production release thiếu M4/M5 AI/vector gates.

---

## 10. M4 — LLM review enrichment

### 10.1 Mục tiêu

Làm giàu review thuộc restaurant scope theo kiểu incremental, có structured output, durable invocation ledger, bounded retry, privacy gate và semantic evaluation.

### 10.2 Backlog M4

| ID | Công việc và artifact | Owner | Phụ thuộc | Verify / PRD | Size |
|---|---|---|---|---|---|
| IMP-M4-001 | Hoàn thiện enrichment JSON Schema: sentiment, aspect, topic, summary, highlights, confidence, versions | AI/Product | M0-016 | Schema examples và compatibility tests; AI-002 | L |
| IMP-M4-002 | Hoàn thiện closed topic taxonomy, aspect mapping và `enrichment_version` composer | AI/Product | M4-001 | Deterministic version hash; taxonomy review | M |
| IMP-M4-003 | Viết/version system prompt và structured-output prompt; review text được đóng gói như untrusted data | AI/Security | M0-018, M4-001/002 | Prompt injection unit/red-team fixtures | L |
| IMP-M4-004 | Implement DLP/redaction/tokenization preprocessor cho provider payload | Security/AI | M0-004/005/011 | Seeded PII không lọt payload/log; SEC-003 | L |
| IMP-M4-005 | Implement provider adapter với timeout, token cap, usage/cost response và fake provider | AI Eng | M1-011, ADR-AI | Contract tests; model không hard-code | L |
| IMP-M4-006 | Implement eligible review selector từ explicit `silver_physical_ref`, restaurant scope và target version | AI/Data | M3-005/009/019, M4-002 | New/changed/reused counts deterministic | L |
| IMP-M4-007 | Implement `AI_INVOCATION_LEDGER`, operation key, lease/outbox và exactly-one committed effect | AI/Data | M1-013, M4-005/006 | Crash injection trước/sau provider response; AI-011 | XL |
| IMP-M4-008 | Implement batch worker, bounded concurrency, rate-limit pool, checkpoint và backpressure | AI Eng | M4-005/007 | 429/timeout/worker restart tests; AI-004/005 | L |
| IMP-M4-009 | Implement JSON Schema + semantic + confidence validator | AI Eng | M4-001/002/008 | Enum/range/label-score/low-confidence fixtures | L |
| IMP-M4-010 | Implement restricted candidate storage, `AI.REVIEW_ENRICHED` history và `AI.REVIEW_ENRICHMENT_ERRORS` | AI/Data | M4-007/009 | Only `VALID` enters enriched; invalid traceable | L |
| IMP-M4-011 | Implement `AI.REVIEW_RELEASE_MAP` unique per candidate release/review | AI/Data | M3-018/019, M4-010 | Re-enrichment/rollback version tests; AI-008 | M |
| IMP-M4-012 | Implement bounded repair/retry, retryable taxonomy, DLQ và replay command | AI Eng | M4-008…010 | Max attempts/confidence/error transitions pass | L |
| IMP-M4-013 | Implement permanent-error denominator, 1% publish gate và enrichment coverage metrics | AI/Data | M4-006/010/011 | Empty batch, cache reuse, threshold boundary tests | M |
| IMP-M4-014 | Implement token/latency/cost metrics theo batch/review/model/prompt | AI/Platform | M4-005/007 | Cost reconciliation và budget dimension | M |
| IMP-M4-015 | Tạo human-labeled enrichment set và annotation/adjudication report | QA/Product/AI | M0-016, real-data approval | ≥500 stratified labels hoặc approved revised sample | XL |
| IMP-M4-016 | Implement evaluation harness: sentiment/aspect/topic F1, summary faithfulness, slice/regression | AI/QA | M4-015 | Baseline report đạt/ghi exception rõ; AI-010 | L |
| IMP-M4-017 | Implement Airflow `enrich_reviews` và `validate_enrichment` với pool/retry/final status | Data/AI | M4-006…014 | DAG failure/resume/no-duplicate tests | L |
| IMP-M4-018 | Viết AI operations runbook: quota, 429, DLQ, re-enrichment, model/prompt rollback | AI/Ops | M4-012…017 | Tabletop/provider outage drill | M |
| IMP-M4-019 | Xây `FACT_REVIEW_ENRICHMENT`, release-bound `FACT_REVIEW` left join và AI metric marts/tests bằng dbt | Analytics/AI | M3-013…017, M4-010/011/013 | Core counts không đổi khi AI lỗi; AI denominator/coverage đúng | L |

### 10.3 Exit criteria M4

- Committed review không đổi không gọi provider lại; ambiguous crash call được ledger ghi nhận/costed.
- Chỉ valid + semantic/confidence-pass output vào enriched history/release map.
- Model/prompt/taxonomy/output schema đều versioned và regression-tested.
- Seeded prompt injection/PII tests pass; external transfer đúng approval.
- Golden set đạt baseline được duyệt; permanent failure gate và coverage hoạt động đúng.
- Core Gold và AI-enriched Gold được join theo release map; review/rating KPI không mất row vì enrichment failure.

---

## 11. M5 — Embedding, vector index và RAG

### 11.1 Mục tiêu

Xây versioned vector artifacts và RAG service chỉ trả grounded answer từ serving-safe review evidence của một pinned release.

### 11.2 Backlog M5

| ID | Công việc và artifact | Owner | Phụ thuộc | Verify / PRD | Size |
|---|---|---|---|---|---|
| IMP-M5-001 | Provision ChromaDB local persistent volume, service boundary và per-environment/per-index-version collection namespace | Platform/AI | M0-010/013, M1-007/008 | Persistence restart, connectivity và negative access tests | L |
| IMP-M5-002 | Implement deterministic chunking v1, offsets, content hash và chunking version | AI Eng | M4-010 | Short/long/Unicode/repeated review fixtures | L |
| IMP-M5-003 | Tạo release-bound secure `AI.RAG_DOCUMENT` projection chỉ cho in-scope/redacted evidence | Data/Security | M3-009, M4-011 | PII/nonrestaurant/candidate records absent | L |
| IMP-M5-004 | Implement `embedding_compute_key` và restricted embedding-input preparation | AI/Security | M4-004, M5-002 | Content/policy/version hash fixtures | M |
| IMP-M5-005 | Implement `EMBEDDING_INVOCATION_LEDGER` và OpenRouter Embeddings adapter/cache với configured model slug/dimension validation | AI Eng | M4-007 pattern, M5-004 | Catalog/model/dimension check + crash/reuse/no-duplicate committed result | L |
| IMP-M5-006 | Implement `document_metadata_hash`, `policy_version` và `vector_upsert_key` | AI/Data | M5-002/003/004 | Metadata-only change causes upsert, not provider call | M |
| IMP-M5-007 | Implement `VECTOR_UPSERT_LEDGER` và idempotent ChromaDB upsert/supersede/delete | AI Eng | M5-001/005/006 | Replay/crash/collection-version tests; EMB-003/007 | L |
| IMP-M5-008 | Implement versioned ChromaDB collection build, explicit collection ref, candidate isolation và retention | AI/Platform | M3 release framework, M5-007 | Candidate collection invisible; old collection retained for rollback | L |
| IMP-M5-009 | Implement reconciliation giữa Snowflake expected map và ChromaDB documents/vector version/metadata | AI/Data | M5-003/008 | Coverage ≥99.9%; stale/missing repair path | L |
| IMP-M5-010 | Implement metadata filters: business, city/state, category, stars, date và policy labels | AI Eng | M5-003/008 | Filter leakage negative tests; EMB-004 | M |
| IMP-M5-011 | Implement ChromaDB retrieval service trả `chunk_id + score`, rồi fetch authoritative evidence từ Snowflake và re-check authorization | AI/Backend | M5-003/008/010 | ChromaDB không lộ raw input; auth tests | L |
| IMP-M5-012 | Implement query normalization/filter extraction với strict server validation | AI/Backend | M5-011, APP contracts | Malformed/unauthorized filter tests | M |
| IMP-M5-013 | Implement RAG prompt/context builder và evidence budget | AI Eng | M4-003, M5-011/012 | Evidence separation/injection tests | L |
| IMP-M5-014 | Implement answer generator, no-evidence refusal và contradiction handling | AI Eng | M5-013 | Answer/no-answer/conflict golden cases | L |
| IMP-M5-015 | Implement claim citations, evidence resolver và internal stable links | Backend/App | M5-003/014 | Every factual claim resolves; broken citation blocks answer | L |
| IMP-M5-016 | Implement RAG service contract, request pinning, auth/rate limit và trace metadata | Backend/Security | M3-019/020, M5-011…015 | APP-001…007/RAG-001…007 integration tests | XL |
| IMP-M5-017 | Tạo RAG Streamlit tab tối thiểu với filters, freshness, citations, disclaimer và states | App Eng | M1-012, M5-016 | UI component/E2E smoke | L |
| IMP-M5-018 | Tạo versioned RAG golden set: answerable/no-evidence/conflict/filter/injection | QA/Product/AI | M0-017, M5-012…015 | 50–100+ approved questions | L |
| IMP-M5-019 | Implement RAG evaluation: Recall@k, claim citation, groundedness, relevance, refusal precision/recall | AI/QA | M5-018 | Report đạt approved thresholds | L |
| IMP-M5-020 | Implement Airflow `build_embeddings`, index reconcile, rồi handoff tới release-bound `dbt_build_gold/dbt_test_gold` | Data/AI/Analytics | M4-019, M5-005…009, M3-018 | Failure keeps old pointer/index; task order matches PRD | L |
| IMP-M5-021 | Implement RAG metrics: latency, retrieval count, refusal, citation error, cost; privacy-safe feedback hook | AI/Platform | M5-016/019 | Metrics correlate request→release→index/model | M |
| IMP-M5-022 | Viết ChromaDB collection rebuild/rollback, OpenRouter outage và citation incident runbooks | AI/Ops | M5-008…021 | Restart/rollback/rebuild drill | M |

### 11.3 Exit criteria M5

- Embedding compute và index upsert dùng key/ledger tách biệt; metadata-only change không tái embed.
- ChromaDB search không trả raw embedding input; evidence authoritative đến từ authorized Snowflake `AI.RAG_DOCUMENT`.
- Request pin release/index, citation resolve đúng và nonrestaurant/revoked/candidate data không lọt.
- RAG evaluation và prompt-injection/security corpus đạt threshold.
- Index reconciliation, rebuild, rollback và old-release retention được kiểm chứng.

---

## 12. M6 — Safe Text-to-SQL

### 12.1 Mục tiêu

Cho phép câu hỏi định lượng trên curated Gold semantic views, với release pinning, AST policy, read-only identity và resource controls nhiều lớp.

### 12.2 Backlog M6

| ID | Công việc và artifact | Owner | Phụ thuộc | Verify / PRD | Size |
|---|---|---|---|---|---|
| IMP-M6-001 | Chốt supported question taxonomy và semantic catalog contract | Product/Analytics/AI | M0-009/017, M3-016 | Metric/name/time ambiguity examples | L |
| IMP-M6-002 | Generate/version semantic catalog từ dbt metadata và approved metrics | Analytics/Backend | M3-016/024 | Bronze/Silver/PII absent; catalog diff review | L |
| IMP-M6-003 | Implement Text-to-SQL prompt template chỉ nhận logical allowlisted objects | AI Eng | M6-001/002, M4 provider adapter | Prompt contract/injection fixtures | M |
| IMP-M6-004 | Chọn/tích hợp SQL AST parser và Snowflake dialect normalizer qua ADR/library wrapper | Backend/Security | M0-018 | Parser contract tests không phụ thuộc regex | L |
| IMP-M6-005 | Implement single `SELECT`/`WITH SELECT` validator; chặn multi-statement, DDL, DML, CALL, COPY, stage | Backend/Security | M6-004 | Malicious corpus; SQL-002 | L |
| IMP-M6-006 | Implement table/column/join/function allowlist và fully-qualified logical resolution | Backend/Analytics | M6-002/004 | INFORMATION_SCHEMA/UDF/external bypass blocked | L |
| IMP-M6-007 | Implement Cartesian/scan-risk policy, mandatory filters và ambiguity detector | Backend/Analytics | M6-001/006 | Runaway/ambiguous questions fail before execution | L |
| IMP-M6-008 | Implement trusted logical→physical release binder; reject model/client physical refs/current alias | Backend/Data | M3-019, M6-006 | Concurrent pointer swap isolation; SQL-012 | L |
| IMP-M6-009 | Configure `TEXT_TO_SQL_ROLE`, dedicated warehouse/session, disabled secondary roles và query tag | Security/Data | M1-007, M6-008 | Exact app identity negative permission tests | L |
| IMP-M6-010 | Enforce timeout, 1.000-row cap, concurrency, resource/credit limit và cancellation | Backend/Platform | M6-009, budget ADR | Timeout/large-scan/burst tests | L |
| IMP-M6-011 | Implement execution service với normalized SQL, typed result, empty/error contract và max one repair | Backend/AI | M6-003…010 | No infinite retry; result schema contract | XL |
| IMP-M6-012 | Implement deterministic table/chart selection và safe result formatting | Backend/App | M6-011 | No code execution/unsafe HTML; chart fixtures | M |
| IMP-M6-013 | Implement clarification/denial UX cho metric, timezone, scope và policy ambiguity | Product/App/AI | M6-001/007/011 | Approved UX examples | M |
| IMP-M6-014 | Implement SQL audit: actor, question hash, prompt/catalog version, candidate, decision, query ID, cost | Backend/Security | M1-013/014, M6-011 | Full trace without raw sensitive telemetry | L |
| IMP-M6-015 | Tạo Text-to-SQL Streamlit tab với SQL display, freshness, table/chart, denial/error states | App Eng | M1-012, M6-011…014 | UI E2E smoke | L |
| IMP-M6-016 | Tạo semantic evaluation set với expected result/equivalence và ambiguous cases | QA/Analytics/Product | M0-017, M6-001 | Versioned supported question set | L |
| IMP-M6-017 | Tạo adversarial SQL corpus: comment/evasion, nested functions, exfiltration, cost và auth attacks | Security/QA | M0-018, M6-004…010 | Zero approved-corpus bypass | L |
| IMP-M6-018 | Implement evaluation runner và release gate cho semantic accuracy/execution/security | AI/QA | M6-016/017 | ≥ approved correctness; 0 critical bypass | L |
| IMP-M6-019 | Implement SQL latency/denial/repair/query-cost metrics và alerts | Platform/Backend | M6-011/014/018 | request→release→query correlation | M |
| IMP-M6-020 | Viết SQL policy/catalog update/query incident/cost runaway runbooks | Backend/Ops/Security | M6-014…019 | Tabletop incident drill | M |

### 12.3 Exit criteria M6

- LLM/client không thể chọn physical schema; server bind đúng pinned release.
- Malicious corpus không thực thi được DDL/DML/multi-statement/object/function ngoài allowlist.
- Execution dùng đúng `TEXT_TO_SQL_ROLE`, warehouse/session limits và audit query ID.
- Supported question set đạt semantic result accuracy; ambiguous/unsupported question không bị đoán.
- UI hiển thị SQL thực thi, freshness, empty/error/denial rõ ràng.

---

## 13. M7 — Dashboard và end-to-end application integration

### 13.1 Mục tiêu

Tạo trải nghiệm thống nhất cho dashboard, Ask Reviews và Ask Data; mọi flow dùng chung auth, filter semantics, release metadata, evidence và error behavior.

### 13.2 Backlog M7

| ID | Công việc và artifact | Owner | Phụ thuộc | Verify / PRD | Size |
|---|---|---|---|---|---|
| IMP-M7-001 | Hoàn thiện app architecture, routing, shared config/client và feature flags | App/Backend | M1-012, M5-016, M6-011 | App startup/route contract tests | M |
| IMP-M7-002 | Hoàn thiện IdP/reverse proxy integration, session expiry/logout/revocation/CSRF | App/Security | M1-008/012, M0-012 | APP-008…010 tests | L |
| IMP-M7-003 | Implement persona/group → feature/data permission mapping và protected operator routes | App/Security | M7-002, M1-007 | Per-persona negative authorization suite | L |
| IMP-M7-004 | Implement shared release context: pin ID, freshness, source coverage, stale/degraded state | App/Backend | M3-018/019 | One navigation/request chain uses expected release | L |
| IMP-M7-005 | Implement global filters/date/city/state/category/business/stars/sentiment/aspect/topic contract | App/Analytics | M3-016, M4/M5 | Cross-page filter consistency tests | L |
| IMP-M7-006 | Xây Executive Overview page | App/Analytics | M3-015/016, M7-004/005 | KPI reference-query reconciliation | L |
| IMP-M7-007 | Xây Business Detail page với trends/aspects/topics/evidence drill-down | App/Analytics | M4/M5, M7-005 | Business UAT fixture | L |
| IMP-M7-008 | Xây City & Category Trends page; xử lý non-additive category và sample thresholds | App/Analytics | M3-015, M7-005 | Ranking/no-double-count fixtures | L |
| IMP-M7-009 | Xây Review & Aspect Insights page với enrichment coverage | App/Analytics | M4 Gold models, M7-005 | AI denominator/coverage reconciliation | L |
| IMP-M7-010 | Xây Data Quality & Pipeline Health page | App/Data/Platform | M2-019, M3 dbt audit, M4/M5 metrics | Latest run/error/quarantine/freshness display | L |
| IMP-M7-011 | Tích hợp RAG tab production UX | App/AI | M5-017/019/021, M7-002…005 | RAG E2E/citation/auth tests | M |
| IMP-M7-012 | Tích hợp Text-to-SQL tab production UX | App/AI | M6-015/018/019, M7-002…005 | SQL E2E/denial/auth tests | M |
| IMP-M7-013 | Implement evidence route với re-authorization và serving-safe excerpt | App/Security | M5-003/015/016, M7-003 | IDOR/copied-link negative tests | M |
| IMP-M7-014 | Implement loading, empty, unavailable, stale, failed và rate-limit states thống nhất | App/Product | M7-001/004/010…012 | UI state matrix tests; BI-005 | M |
| IMP-M7-015 | Implement keyboard navigation, labels, contrast và accessible chart/table alternatives | App/QA | M7-006…014 | Accessibility smoke; BI-006 | M |
| IMP-M7-016 | Implement privacy-safe product telemetry: active users, task completion, latency, useful feedback | App/Product/Security | M0 metrics, M7-002 | Actor pseudonymous; retention/redaction tests | M |
| IMP-M7-017 | Cấu hình Snowsight/approved BI access tới current convenience views và release metadata | Analytics/Security | M3-016/018, OQ-14 | Analyst role read-only + freshness visible | M |
| IMP-M7-018 | Xây `E2E-FIXTURE-001` từ malformed/replay/correction/deletion/AI/security cases | QA/All | M2–M6 | Deterministic end-to-end CI/staging run | XL |
| IMP-M7-019 | Chạy business UAT script theo US-01…US-08 và sửa discrepancy | Product/QA/All | M7-006…018 | Signed UAT evidence; no unexplained KPI mismatch | L |
| IMP-M7-020 | Hoàn thiện user guide, analyst guide và support/error guidance | Product/App/Ops | M7-019 | New pilot user dry run | M |

### 13.3 Exit criteria M7

- Dashboard, RAG và Text-to-SQL dùng chung authenticated identity và pinned release semantics.
- KPI đối soát Gold; AI insights luôn có coverage/evidence; category totals không bị hiểu sai.
- Auth/session/IDOR/rate-limit/error/accessibility tests pass.
- `E2E-FIXTURE-001` pass từ synthetic source đến cả ba consumption flows.
- Product/business UAT được ký, không còn critical discrepancy.

---

## 14. M8 — Production hardening và launch

### 14.1 Mục tiêu

Chứng minh hệ thống chịu tải, quan sát được, rollback/recover/revoke được, nằm trong budget và có owner/runbook vận hành.

### 14.2 Backlog M8

| ID | Công việc và artifact | Owner | Phụ thuộc | Verify / PRD | Size |
|---|---|---|---|---|---|
| IMP-M8-001 | Hoàn thiện DAG `yelp_pipeline` 11 task, trigger rules, pools, timeouts, retries và task ownership | Data/Ops | M2/M3/M4/M5 | DAG structure/import/dependency tests | L |
| IMP-M8-002 | Hoàn thiện `publish_metrics` finalizer: terminal audit luôn chạy; definition/events/CAS pointer chỉ khi gate pass | Data/Backend | M3-018, M5-020, M8-001 | Failure injection ở từng upstream step | XL |
| IMP-M8-003 | Implement end-to-end correlation dashboard cho batch/process/release/request/query/model/index | Platform | OBS-001…007 implementations | Trace sample resolves all refs | L |
| IMP-M8-004 | Tạo operational dashboards: freshness, reconciliation, DQ, quarantine, AI/vector, SQL, latency | Platform/Data/AI | M2–M7 metrics | Owner-reviewed dashboard pack | L |
| IMP-M8-005 | Cấu hình alert severity, threshold, channel, owner, escalation và runbook links | Platform/Ops | M8-004 | Synthetic alert delivery/ack test | L |
| IMP-M8-006 | Cấu hình Snowflake resource monitors/auto-suspend, R2 usage checks, OpenRouter token budget và ChromaDB disk alerts | Platform/Finance | M0-015, usage metrics | 50/80/100% alert + hard/degrade path | M |
| IMP-M8-007 | Chạy full RBAC/auth/session/secret/network/egress negative suite | Security/QA | M1/M5/M6/M7 | SEC-001…005 evidence | L |
| IMP-M8-008 | Chạy secret/key rotation và compromised-credential drill | Security/Platform | M1-008, M8-007 | Rotation without outage + audit | M |
| IMP-M8-009 | Chạy source-to-serving DLP/PII seeded test và telemetry retention validation | Security/QA | M4/M5/M7 | No restricted data outside allowlist | L |
| IMP-M8-010 | Implement/verify release invalidation/revocation, sanitized rebuild và rollback guard | Security/Data | M3-020, M8-002 | Revoked release cannot reactivate; REL-007 | L |
| IMP-M8-011 | Implement legal deletion/correction workflow xuyên live stores, index, cache và backup restore filter | Security/Data/Ops | Retention ADR, M8-010 | Legal deletion dry run; SEC-006/COMP-002 | XL |
| IMP-M8-012 | Chạy release activation concurrency và pointer crash-recovery tests | QA/Data | M8-002/010 | No mixed active release; CAS recovery report | L |
| IMP-M8-013 | Chạy Airflow retry/resume/backfill/late file/provider outage/warehouse outage drills | QA/Ops | M8-001…005 | State/alert/runbook evidence | L |
| IMP-M8-014 | Chạy Gold/AI/vector rollback và index/Silver rebuild drills | QA/Data/AI | M3/M4/M5, M8-002 | Meet rollback window/RTO | L |
| IMP-M8-015 | Configure backup/retention/lifecycle và restore-filter behavior | Platform/Security | M0-005, M8-011 | Restore drill; revoked data not reintroduced | L |
| IMP-M8-016 | Chạy performance/load test theo capacity envelope: full release, concurrent UI/RAG/SQL, cold/warm | QA/Platform | M0-015, M7 | SLO/cost report; NFR-001…004 | XL |
| IMP-M8-017 | Chạy `E2E-SCALE-001` trên named source release và khóa byte/row/token counts | QA/All | Real-data approval, M8-016 | Full staging evidence; AC-SYS-01 | XL |
| IMP-M8-018 | Tối ưu bottleneck đã đo: chunking, warehouse, dbt incremental, cache, concurrency | Relevant owner | M8-016/017 | Before/after benchmark; no semantic regression | L |
| IMP-M8-019 | Hoàn thiện CI/CD promotion dev→staging→prod, migration approval, smoke và automated rollback hook | Platform | M1-015/017, all tests | DEP-001/002 deployment rehearsal | L |
| IMP-M8-020 | Scan/pin dependency và container; generate SBOM/provenance/artifact digest | Platform/Security | M8-019 | Critical scan findings resolved/accepted | M |
| IMP-M8-021 | Hoàn thiện runbooks: ingest, DQ, DLQ, AI quota, vector, SQL, deploy, rollback, DR, revoke, cost | All/Ops | M8-001…020 | Runbook coverage checklist | L |
| IMP-M8-022 | Thiết lập on-call/support ownership, severity matrix và incident communication | Ops/Product | M8-005/021 | Tabletop incident exercise | M |
| IMP-M8-023 | Chạy pilot, thu product metrics/feedback và sửa launch blockers | Product/All | M7 UAT, M8 hardening | Pilot report + blocker closure | L |
| IMP-M8-024 | Review AC-SYS-01…18 theo từng solo responsibility hat; lấy external sign-off nếu public/policy yêu cầu | Solo Developer/External approver | M8-001…023 | Launch evidence checklist | M |

### 14.3 Exit criteria M8

- `E2E-SCALE-001`, security corpus, AI/RAG/SQL eval và SLO tests đều pass hoặc có signed exception không critical.
- Failure ở bất kỳ upstream task nào vẫn có terminal audit/alert và không đổi active release.
- Rollback, rebuild, revoke/legal deletion và restore filtering đáp ứng policy/RTO.
- Cost dashboards/budget alerts/hard cap hoạt động; production capacity nằm trong envelope.
- CI/CD promotion và rollback rehearsal thành công; runbooks/on-call/ownership đầy đủ.
- AC-SYS-01…18 có evidence và solo launch checklist hoàn tất; external Security/Legal/Operations sign-off được đính kèm nếu public/policy yêu cầu.

---

## 15. Suggested sprint sequencing

Đây là sequencing theo sprint 2 tuần cho một developer. Các cột là focus area, không phải stream chạy bởi người khác; chỉ giữ tối đa một hạng mục L/XL `in progress` và dùng phần còn lại cho test/documentation.

| Sprint | Stream Data/Platform | Stream AI/Backend | Stream App/QA | Gate |
|---|---|---|---|---|
| S0–S1 | Source profile, ADR, contracts, R2/Snowflake spike | OpenRouter/ChromaDB/security spikes | Persona, KPI, UX/eval design | M0 |
| S2–S3 | Repo, R2/Snowflake/RBAC, audit skeleton | OpenRouter/ChromaDB interfaces, release/auth spike | App shell, synthetic fixtures, CI | M1 |
| S4–S5 | Validation, R2/Parquet, audit/quarantine | Backend helpers/fakes | Ingestion test harness | M2 slice 1 |
| S6 | Bronze COPY, replay/backfill, Airflow tasks | — | Reconciliation/E2E ingestion | M2 |
| S7–S8 | Versioned Silver + dbt core models | Release binding/backend | Metric fixtures, DQ tests | M3 slice 1 |
| S9 | Gold marts, release registry/pointer | SQL semantic catalog start | Core dashboard spike | M3 |
| S10–S11 | AI task orchestration/support | Enrichment schema/ledger/worker | Labeling/eval harness | M4; M6 parallel |
| S12–S13 | Vector infra/index/reconciliation | RAG service; SQL validator/executor | RAG/SQL UI + eval | M5/M6 |
| S14–S15 | Audit/lineage/DQ integration | Serving integration | Dashboard pages/auth/UAT | M7 |
| S16–S18 | SLO, DR, release finalizer, CI/CD | AI/vector/SQL hardening | E2E/load/security/pilot | M8 |

### 15.1 Parallelization rules

- M6 semantic catalog/policy có thể bắt đầu khi M3 semantic views và metric dictionary ổn định; không phụ thuộc M4.
- M4 evaluation labeling có thể bắt đầu ở M0/M1 sau approval, song song với data engineering.
- M5 UI skeleton có thể mock RAG contract trước khi ChromaDB integration hoàn tất.
- M7 dashboard pages có thể phát triển bằng release-bound fixtures từ M3.
- Không parallelize bằng cách cho hai runs dùng chung mutable Silver/Gold candidate schema.
- Không bật real-data AI/RAG spike trước COMP-001/002 approval.

---

## 16. Release build và activation algorithm

Mọi implementation phải giữ thứ tự logic sau, dù Airflow operator cụ thể có thể khác:

1. Nhận complete source release; tạo/reuse source object identities.
2. Tạo `batch_id`, ingest/audit Bronze và reconcile.
3. Tạo `processing_run_id` và `data_release_id`; append `CANDIDATE_CREATED`.
4. Tạo isolated `SILVER_RUN_<processing_run_id>`; dbt build/test Silver.
5. Chọn in-scope review; enrich, validate và build `AI.REVIEW_RELEASE_MAP` cho candidate ID.
6. Chuẩn bị RAG documents; reuse/create embeddings; build explicit vector index version; reconcile.
7. Tạo isolated `GOLD_RELEASE_<data_release_id>`; dbt build/test Gold và semantic views.
8. Finalizer kiểm tra toàn bộ audit counts, critical tests, AI threshold, vector coverage, artifact checksums/refs và revocation policy.
9. Insert immutable `AUDIT.DATA_RELEASE` artifact definition.
10. Append `BUILD_COMPLETED`; CAS đổi `ACTIVE_RELEASE_POINTER`; append `ACTIVATED`/`SUPERSEDED` trong transaction/audit flow phù hợp.
11. App request đọc pointer đúng một lần và dùng explicit physical refs đến hết request.
12. GC chỉ chạy sau retention/rollback window, không có active request lease và release không còn cần cho legal/audit.

Nếu bất kỳ bước 1–8 fail, append terminal failure event/audit, giữ pointer cũ và không phục vụ candidate artifacts.

---

## 17. Test execution matrix

| Thời điểm | Test bắt buộc | Dữ liệu | Thời lượng mục tiêu |
|---|---|---|---|
| Mỗi commit/local | Unit, type/lint, contract fast tests | Synthetic nhỏ | Vài phút |
| Mỗi pull request | Unit + contract + dbt parse/compile + SQL policy + secret/dependency scan | Synthetic/CI isolated | Dưới khoảng 15–20 phút nếu khả thi |
| Merge/main | Integration R2/Snowflake/ChromaDB test, DAG import/task tests, container build | Synthetic isolated env | Dưới khoảng 30–45 phút |
| Nightly | Replay/backfill, dbt build/test, AI fake/provider smoke, vector/serving smoke | Synthetic medium | Theo budget nightly |
| Model/prompt/index change | Full enrichment/RAG regression + security corpus | Versioned golden sets | Gate trước staging promotion |
| Staging release | `E2E-FIXTURE-001`, auth/RBAC, rollback/revoke, cold/warm serving | Production-like synthetic/approved data | Gate trước approval |
| Pre-production | `E2E-SCALE-001`, load/cost/SLO, DR/legal-delete drill | Named approved release | Gate trước launch |
| Production deploy | Migration check, smoke, pointer/version/freshness, synthetic queries | Safe synthetic probes | Tự động, ngắn |

### 17.1 Minimum test artifacts

- `TC-CON-*`: source/manifest/schema/time/snapshot contracts.
- `TC-ING-*`: ingestion, idempotency, reconciliation, quarantine, backfill.
- `TC-DWH-*`: dbt grain/key/DQ/SCD/restaurant/metric/concurrency.
- `TC-AI-*`: schema, semantic, confidence, ledger, retry, prompt injection, DLP.
- `TC-EMB-*`: compute/upsert keys, index version, filter, reconcile, rollback.
- `TC-RAG-*`: retrieval, citations, groundedness, refusal, authorization.
- `TC-SQL-*`: semantic equivalence, AST/allowlist/RBAC/cost/session bypass.
- `TC-APP-*`: auth/session/IDOR/filter/states/accessibility.
- `TC-REL-*`: candidate isolation, CAS activation, rollback, invalidation/revocation.
- `TC-OPS-*`: alerts, backup/restore, DR, secret rotation, cost and runbook drills.

---

## 18. Environment promotion và change management

### 18.1 Promotion flow

```text
Feature branch
→ PR checks
→ merge main
→ immutable artifact
→ dev deployment + integration smoke
→ staging migration/build + full gates
→ manual approval
→ production candidate deployment
→ smoke
→ release activation
→ monitor / rollback if needed
```

### 18.2 Thay đổi cần migration/evaluation riêng

| Loại thay đổi | Bắt buộc |
|---|---|
| Source contract/schema | Compatibility classification, fixtures, reprocess/backfill plan |
| dbt grain/key/metric | Metric fixtures, incremental-vs-full, downstream semantic impact |
| Restaurant taxonomy | New `restaurant_scope_version`, reprocess/enrich/index/Gold release |
| Prompt/model/taxonomy/output schema | New `enrichment_version`, golden regression, cost review |
| Chunking/embedding model | New compute/index version, retrieval regression, rebuild plan |
| Vector metadata/policy | New vector upsert keys/index reconciliation; embedding may be reused |
| Semantic catalog/SQL policy | SQL semantic + adversarial regression |
| Auth/RBAC/masking | Positive/negative permission and IDOR tests |
| Retention/deletion | Security/Legal approval, revoke/restore-filter drill |
| Release schema/pointer logic | Concurrency/failure/rollback/revocation tests |

---

## 19. Observability implementation checklist

| Domain | Metrics/events | Alert baseline |
|---|---|---|
| Source/ingestion | files, bytes, physical/accepted/quarantine/parse-failed, checksum conflict, duration | Missing/incomplete source, reconciliation mismatch, schema breaking |
| dbt/Silver/Gold | model duration, rows, test severity, freshness, orphan/duplicate, processing ref | Critical test, freshness breach, cross-run mismatch |
| AI enrichment | eligible/reused/success/permanent error, attempts, 429, latency, token, cost, version | Error gate, rate limit, cost anomaly, low confidence spike |
| Embedding/vector | compute reuse, upsert, expected/indexed, stale/missing metadata, index age | Coverage <99.9%, sync lag, rebuild failure |
| RAG | retrieval latency, refusal, citation resolve, grounded eval, provider error, cost | Citation failure, latency/SLO, auth/filter leak signal |
| Text-to-SQL | generation/validation/denial/repair/execution, query cost/time/rows | Security denial spike, timeout, resource threshold, policy bypass |
| App | auth/session failure, request latency, error/stale state, active users | Availability/latency/auth anomaly |
| Release | candidate/build/activate/fail/revoke events, pointer version, artifact refs | Finalizer failure, pointer conflict, revoked active ref |
| Cost | Snowflake credits/trial runway, R2 storage/operations, OpenRouter chat/embedding và ChromaDB disk | 50/80/100% budget and hard/degrade action |

Mọi alert phải có severity, owner, destination, dedup window, actionable context và runbook URL. Alert không có owner/runbook chưa được coi là hoàn tất.

---

## 20. Runbook inventory

| Runbook | Owner | Hoàn tất ở |
|---|---|---|
| Source missing/incomplete/schema conflict | Data Engineering | M2 |
| Replay/resume/backfill/late file | Data Engineering | M2 |
| Quarantine inspection và record replay | Data Engineering | M2 |
| dbt critical failure và isolated schema cleanup | Analytics Engineering | M3 |
| Metric discrepancy/restaurant scope correction | Analytics/Product | M3/M7 |
| LLM quota/429/timeout/DLQ/re-enrichment | AI Engineering | M4 |
| Vector reconcile/rebuild/rollback | AI/Platform | M5 |
| RAG citation/prompt-injection incident | AI/Security | M5 |
| Text-to-SQL denial/policy/query-cost incident | Backend/Security | M6 |
| App auth/session/IDOR incident | App/Security | M7 |
| Release activation/pointer rollback | Data/Platform | M8 |
| Invalidated/revoked/legal deletion/sanitized rebuild | Security/Data | M8 |
| Backup/restore/DR | Platform/Ops | M8 |
| Secret/key rotation | Security/Platform | M8 |
| Cost threshold/hard-cap degradation | Platform/Finance/Product | M8 |

---

## 21. Backlog ticket template

```markdown
# [IMP-ID] Tên outcome

## Context
- PRD requirements:
- Milestone/epic:
- Dependencies:
- ADR/contracts:

## Scope
- In:
- Out:

## Deliverables
- Code/config/schema/docs:

## Acceptance
- Given/When/Then:
- Test IDs/commands:
- Required evidence:

## Operational impact
- Logs/metrics/alerts:
- Cost impact:
- Security/privacy impact:
- Migration/backfill:
- Rollback:

## Definition of Done
- [ ] Review
- [ ] Tests
- [ ] Documentation/runbook
- [ ] Environment verification
```

---

## 22. First 10 working days

Nếu bắt đầu dự án ngay, thứ tự cụ thể nên là:

### Ngày 1–2

- Ghi nhận các solo responsibility hats và mở decision log/timeboxed self-review session.
- Inventory workspace/accounts/source access.
- Tạo sample synthetic fixture nếu chưa được dùng dữ liệu thật.
- Mở các issue `IMP-M0-001`…`IMP-M0-019` và gắn owner.

### Ngày 3–5

- Profile source package hoặc synthetic equivalent.
- Chốt source semantics, required datasets và restaurant scope draft.
- Bắt đầu legal/privacy/threat review.
- Chạy vector/LLM/deployment/auth spikes có timebox bằng synthetic data.

### Ngày 6–8

- Chốt SCD/time/metric dictionary draft.
- Chốt release/version isolation ADR.
- Khóa capacity/SLO/budget assumptions.
- Review AI schema/taxonomy/evaluation plan.

### Ngày 9–10

- Duyệt M0 ADR/OQ hoặc ghi blocker rõ ràng.
- Re-estimate M1–M8 và lập sprint backlog M1.
- Khởi tạo repo/tooling/CI/synthetic fixtures nếu M0 gate cho phép.
- Không provision production hoặc ingest dữ liệu thật trước approval tương ứng.

---

## 23. Milestone sign-off checklist

Mỗi milestone cần một evidence bundle gồm:

- Danh sách work item hoàn tất và requirement IDs được cover.
- Test/evaluation reports và known limitations.
- Data/model/schema/config versions.
- Security/privacy/cost review tương ứng.
- Metrics/alerts/runbooks và owner.
- Demo hoặc UAT evidence.
- Open defect/risk với severity và owner.
- Go/no-go decision cho milestone tiếp theo.

Không chuyển milestone chỉ vì code đã merge; exit criteria và evidence bundle phải được owner chấp thuận.

---

## 24. Implementation completion criteria

Implementation P0 chỉ hoàn tất khi:

1. Tất cả M0–M8 exit criteria đạt.
2. Toàn bộ P0 requirement trong PRD có ticket, test evidence và owner.
3. `E2E-FIXTURE-001` và `E2E-SCALE-001` pass.
4. AC-SYS-01…18 được ký.
5. Không còn critical security/data discrepancy hoặc unexplained reconciliation gap.
6. Active release có explicit Silver/AI/Gold/vector refs, rollback/revoke được và không chứa candidate contamination.
7. Dashboard, RAG và Text-to-SQL đáp ứng approved SLO/quality/cost gates.
8. Operations có thể replay, backfill, recover, rollback, revoke và xử lý incident theo runbook mà không cần người viết code ban đầu.

---

## 25. PRD-to-implementation traceability

| PRD requirement group | Implementation work items chính | Milestone gate |
|---|---|---|
| CON-001…005 | IMP-M0-002/003/005/006/008, IMP-M2-001…012, IMP-M3-001/002 | M0, M2, M3 |
| ING-001…010 | IMP-M2-001…020 | M2 |
| DWH-001…013 | IMP-M2-013…015, IMP-M3-002…024, IMP-M4-019 | M2, M3, M4 |
| AI-001…011 | IMP-M4-001…019 | M4 |
| EMB-001…007 | IMP-M5-001…010/020/022 | M5 |
| RAG-001…007 | IMP-M5-003/010…022, IMP-M7-011/013 | M5, M7 |
| RAG-008…009 (P1) | Backlog sau M5; hook ở IMP-M5-021 và IMP-M7-016 | Sau MVP/M5 |
| SQL-001…012 | IMP-M6-001…020, IMP-M7-012 | M6, M7 |
| BI-001…006 | IMP-M3-015/016/024, IMP-M7-004…010/014/015/017/019 | M3, M7 |
| APP-001…010 | IMP-M1-012, IMP-M5-016/017, IMP-M6-011…015, IMP-M7-001…005/011…016 | M1, M5–M7 |
| ORCH-001…011 | IMP-M1-010, IMP-M2-016…018, IMP-M3-021/023, IMP-M4-017, IMP-M5-020, IMP-M8-001/002/012/013 | M2–M8 |
| OBS-001…008 | IMP-M1-014/018, IMP-M2-015/019, IMP-M4-014, IMP-M5-009/021, IMP-M6-014/019, IMP-M8-003…006 | M1–M8 |
| SEC-001…008 | IMP-M0-004/005/012/018, IMP-M1-005…008/014/015, IMP-M4-003/004, IMP-M5-003/011/016, IMP-M6-004…010/017, IMP-M7-002/003/013, IMP-M8-007…011 | M0–M8 |
| REL-001…007 | IMP-M0-014, IMP-M3-002/017…023, IMP-M5-008/009/020, IMP-M8-002/010/012/014 | M3, M5, M8 |
| NFR-001…004 | IMP-M0-015, IMP-M8-003…006/013…018 | M8 |
| CFG-001…002 | IMP-M1-003/006/009/011/017, versioned config tasks ở M3–M6 | M1–M6 |
| DEP-001…002 | IMP-M1-015…017, IMP-M8-019/020 | M1, M8 |
| COMP-001…002 | IMP-M0-004/005/011, IMP-M4-004, IMP-M8-009…011/015 | M0, M4, M8 |
| AC-SYS-01…18 | IMP-M7-018/019, IMP-M8-007…024 và evidence bundle mục 23 | M7, M8 |

Khi backlog được tạo trong công cụ quản lý công việc, mỗi requirement P0 phải có ít nhất một implementation task và một verification/test artifact; bảng này là baseline, không thay thế link cụ thể trong từng ticket/PR.
