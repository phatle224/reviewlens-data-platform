# ReviewLens Project Status

> Dashboard trạng thái ngắn gọn; checklist/test cases của phase là evidence chi tiết.

## Tổng quan

| Thuộc tính | Giá trị |
|---|---|
| Trạng thái tổng thể | `ON_TRACK` |
| Phase hiện tại | `M1` — Foundation and developer platform |
| Trạng thái phase hiện tại | `IN_PROGRESS` — 12 done, 1 partial, 7 not started |
| Phase gần nhất hoàn tất | `M0` — 19/19 work items, re-baselined for Olist |
| Cập nhật lần cuối | 2026-08-06 |
| Người thực hiện | Solo Developer |
| Active source | Olist Brazilian E-Commerce dataset — nine relational CSVs, CC BY-NC-SA 4.0 |
| Data policy hiện hành | Raw CSV/review/row-level/embedding artifacts outside Git; private R2/Snowflake after manifest/privacy gate; external AI only after DLP/minimization; public evidence synthetic/aggregate/redacted |
| Cloud topology | Snowflake Standard/AWS Singapore ↔ private R2 Standard/APAC via S3-compatible HTTPS stage |

## Tiến độ theo phase

| Phase | Trạng thái | Tóm tắt | Evidence |
|---|---|---|---|
| M0 | `COMPLETE` | Olist product/data/license/security/architecture baseline | [Checklist](./phases/M0/M0_CHECKLIST.md) · [Tests](./phases/M0/M0_TEST_CASES.md) |
| M1 | `IN_PROGRESS` | Config, identities, provider/dbt/Airflow boundaries and versioned Snowflake audit ledgers | [Overview](./phases/M1/README.md) · [Checklist](./phases/M1/M1_CHECKLIST.md) · [Tests](./phases/M1/M1_TEST_CASES.md) |
| M2 | `NOT_STARTED` | Nine-file Olist ingestion, R2 and Bronze | [Plan](./IMPLEMENTATION_PLAN.md) |
| M3 | `NOT_STARTED` | Conformed Silver, Gold and atomic release | [Plan](./IMPLEMENTATION_PLAN.md) |
| M4 | `NOT_STARTED` | DLP-approved review enrichment | [Plan](./IMPLEMENTATION_PLAN.md) |
| M5 | `NOT_STARTED` | Embeddings, ChromaDB and grounded RAG | [Plan](./IMPLEMENTATION_PLAN.md) |
| M6 | `NOT_STARTED` | Guarded Text-to-SQL | [Plan](./IMPLEMENTATION_PLAN.md) |
| M7 | `NOT_STARTED` | Streamlit analytics and integrated consumption | [Plan](./IMPLEMENTATION_PLAN.md) |
| M8 | `NOT_STARTED` | Orchestration, hardening and portfolio evidence | [Plan](./IMPLEMENTATION_PLAN.md) |

Milestone completion: **1/9**. Đây là số gate đã đóng, không phải phần trăm effort.

## Kết quả phiên gần nhất

- Hoàn tất `IMP-M1-013`: DDL-only Snowflake migration tạo versioned ingestion/file/process/release/AI ledgers, guarded active pointer và constant compatibility view.
- Exact grants cho phép producer chỉ `SELECT, INSERT`; không event update/delete/truncate, không future-table grant và chưa có pointer writer trước guarded release procedure ở M3.
- AI ledger chỉ lưu hashes/version/token/cost/latency/sanitized error code; không raw payload, review/prompt/response text hoặc credential field.
- Local-only down migration cần đúng hai session guards và raise trước mọi DROP; deterministic up plan replay hai lần qua adapter pass.
- Không apply live vì acceptance hiện là static migration compatibility và up migration không cần compute; provider/RBAC/Airflow/dbt evidence trước vẫn xanh.
- Full offline gate: 107 pass, 5 expected live skips, 90.09% coverage; Ruff + Airflow 3 rules, mypy, dbt warnings-as-errors, lock check và locked offline Airflow+dbt sync pass.

## Kiểm thử

| Phạm vi | Kết quả | Chi tiết |
|---|---|---|
| M0 | 18 `PASS`, 3 `DEFERRED`, 0 `FAIL` | [M0 test cases](./phases/M0/M0_TEST_CASES.md) |
| M1 | 31 `PASS`, 10 `PENDING`, 0 `FAIL`, 0 `DEFERRED` | [M1 test cases](./phases/M1/M1_TEST_CASES.md); offline 107 pass/5 live skip; audit migration + Airflow DAG + dbt parse/compile plus provider, R2/stage/RBAC and JWT live evidence |
| Quality | `PASS` | Ruff format/lint + Airflow 3 rules, mypy strict, dbt warnings-as-errors, 90.09% branch-aware coverage, uv lock check và locked offline Airflow+dbt sync |
| Status validator | `PASS` — 0 errors, 0 warnings | M0: 19 done/21 tests; M1: 20 work items/41 tests synchronized |

## Blocker và rủi ro

- Không có external blocker cho phần M1 còn lại.
- Dedicated service users đã enable, exact role-scoped named keys/JWT auth pass. Runtime không có đường fallback sang admin/`REVIEWLENS_OWNER`; controlled rotation/revocation smoke chưa chạy.
- R2 stage dùng direct scoped credentials theo Snowflake S3-compatible contract; rotation/revocation thuộc `IMP-M1-008`.
- Olist license cho phép non-commercial portfolio use theo CC BY-NC-SA, nhưng review free text vẫn cần DLP/privacy gate trước OpenRouter/Chroma và không được public raw.
- Snowflake trial hết hạn `2026-09-03`; ưu tiên hoàn tất M1 và M2/M3 vertical slice, giữ X-Small/60s/resource monitor.
- Product/seller insights từ review có multi-item ambiguity; M3 phải implement allocation/label policy, không nhân review rồi sum.

## Chi phí và tài nguyên

| Dịch vụ | Budget/gate hiện tại | Usage đã xác minh |
|---|---|---|
| OpenRouter | 5 USD/project; warning 0.50 USD/day | Không gọi trong phiên migration; 0 USD phát sinh từ code path project |
| Snowflake | ≤10 credits/month; X-Small, auto-suspend 60s | Audit migration tests offline; up artifact is DDL-only/no warehouse; dbt placeholder compile and prior JWT evidence remain pass |
| Cloudflare R2 | Standard; target ≤15 GB; private/lifecycle | Dedicated ingest/stage synthetic live pass; smoke object cleaned up; không upload Olist |
| ChromaDB | ≤5 GB local | Typed/in-memory adapter tests only; chưa provision/index và 0 byte project data được ghi |

## Input cần từ chủ project

Không cần thêm credential hoặc gửi secret cho Codex. Tất cả runtime readiness hiện
`true`; 8 Snowflake key files tồn tại ngoài repository và live authentication pass.
Để đóng `IMP-M1-008`, cần owner xác nhận một maintenance window cho controlled
rotation/revocation smoke vì bước này chủ động thay đổi live authentication state.

## Việc tiếp theo

1. `IMP-M1-014`: structured logging, trace/correlation IDs và seeded secret/PII/review-text redaction tests.
2. `IMP-M1-012`: authenticated loopback-only Streamlit shell and health/error states.
3. `IMP-M1-015`: CI quality/security/data-leak gates sau khi logging/app shell có contract ổn định.
4. Khi owner xác nhận maintenance window: chạy controlled key rotation/revocation smoke để đóng `IMP-M1-008`.
5. Chỉ bắt đầu real Olist upload ở M2 sau machine-readable contract/manifest/privacy preflight.

## Tài liệu nguồn

- [PRD v2](./PRD.md)
- [Implementation plan v2](./IMPLEMENTATION_PLAN.md)
- [Dataset attribution](./DATA_ATTRIBUTION.md)
- [Olist source manifest](./data/OLIST_SOURCE_MANIFEST.md)
- [ADR-008 — Olist primary dataset](./ADR/ADR-008-olist-primary-dataset.md)
- [M0 decision register](./phases/M0/M0_DECISION_REGISTER.md)
- [RAG recommendation](./reviewlens_rag_recommendation.md)
- [Credential rotation runbook](./runbooks/M1_CREDENTIAL_ROTATION.md)
- [Architecture diagram](./images/plan.png)
