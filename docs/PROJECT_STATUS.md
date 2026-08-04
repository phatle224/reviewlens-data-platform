# ReviewLens Project Status

> Dashboard trạng thái ngắn gọn; checklist/test cases của phase là evidence chi tiết.

## Tổng quan

| Thuộc tính | Giá trị |
|---|---|
| Trạng thái tổng thể | `ON_TRACK` |
| Phase hiện tại | `M1` — Foundation and developer platform |
| Trạng thái phase hiện tại | `IN_PROGRESS` — 8 done, 1 partial, 11 not started |
| Phase gần nhất hoàn tất | `M0` — 19/19 work items, re-baselined for Olist |
| Cập nhật lần cuối | 2026-08-05 |
| Người thực hiện | Solo Developer |
| Active source | Olist Brazilian E-Commerce dataset — nine relational CSVs, CC BY-NC-SA 4.0 |
| Data policy hiện hành | Raw CSV/review/row-level/embedding artifacts outside Git; private R2/Snowflake after manifest/privacy gate; external AI only after DLP/minimization; public evidence synthetic/aggregate/redacted |
| Cloud topology | Snowflake Standard/AWS Singapore ↔ private R2 Standard/APAC via S3-compatible HTTPS stage |

## Tiến độ theo phase

| Phase | Trạng thái | Tóm tắt | Evidence |
|---|---|---|---|
| M0 | `COMPLETE` | Olist product/data/license/security/architecture baseline | [Checklist](./phases/M0/M0_CHECKLIST.md) · [Tests](./phases/M0/M0_TEST_CASES.md) |
| M1 | `IN_PROGRESS` | Config, Olist fixtures, R2/Snowflake foundation, RBAC and migration | [Overview](./phases/M1/README.md) · [Checklist](./phases/M1/M1_CHECKLIST.md) · [Tests](./phases/M1/M1_TEST_CASES.md) |
| M2 | `NOT_STARTED` | Nine-file Olist ingestion, R2 and Bronze | [Plan](./IMPLEMENTATION_PLAN.md) |
| M3 | `NOT_STARTED` | Conformed Silver, Gold and atomic release | [Plan](./IMPLEMENTATION_PLAN.md) |
| M4 | `NOT_STARTED` | DLP-approved review enrichment | [Plan](./IMPLEMENTATION_PLAN.md) |
| M5 | `NOT_STARTED` | Embeddings, ChromaDB and grounded RAG | [Plan](./IMPLEMENTATION_PLAN.md) |
| M6 | `NOT_STARTED` | Guarded Text-to-SQL | [Plan](./IMPLEMENTATION_PLAN.md) |
| M7 | `NOT_STARTED` | Streamlit analytics and integrated consumption | [Plan](./IMPLEMENTATION_PLAN.md) |
| M8 | `NOT_STARTED` | Orchestration, hardening and portfolio evidence | [Plan](./IMPLEMENTATION_PLAN.md) |

Milestone completion: **1/9**. Đây là số gate đã đóng, không phải phần trăm effort.

## Kết quả phiên gần nhất

- Đóng `IMP-M1-020`: migrate active source baseline từ Yelp sang Olist trong config, fixture generator, tests, Snowflake contract, PRD/plan, M0/M1 docs, RAG advisory, skill và sơ đồ.
- Ghi metadata-only manifest cho 9 CSV (filename/header/rows/bytes/SHA-256); raw files trong ignored `archive/`, không bị xóa hay commit.
- Thay license-window gate bằng CC BY-NC-SA 4.0 obligations: attribution, NonCommercial, ShareAlike và change indication; thêm negative config tests.
- Synthetic generator giờ tạo đúng 9 CSV, exact source headers, deterministic checksums và valid relational foreign keys.
- Snowflake có `OLIST_CSV_FORMAT` và `INGEST_ROLE` usage; real upload vẫn thuộc M2 sau executable manifest/privacy gate.
- Architecture `plan.png` đã chuyển sang e-commerce/Olist; bản Yelp cũ được archive riêng.
- Full offline gate pass: 45 tests, 3 expected live skips, 87.23% coverage, Ruff, mypy, lock check và locked offline sync.

## Kiểm thử

| Phạm vi | Kết quả | Chi tiết |
|---|---|---|
| M0 | 18 `PASS`, 3 `DEFERRED`, 0 `FAIL` | [M0 test cases](./phases/M0/M0_TEST_CASES.md) |
| M1 | 18 `PASS`, 13 `PENDING`, 0 `FAIL`, 0 `DEFERRED` | [M1 test cases](./phases/M1/M1_TEST_CASES.md); offline 45 pass/3 live skip; prior synthetic R2, Snowflake stage and RBAC live suites pass |
| Quality | `PASS` | Ruff format/lint, mypy strict, 87.23% branch-aware coverage, uv lock/sync |
| Status validator | `PASS` — 0 errors, 0 warnings | M0: 19 done/21 tests; M1: 20 work items/31 tests synchronized |

## Blocker và rủi ro

- Không có external blocker cho phần M1 còn lại.
- Roles đã provision nhưng chưa gán dedicated service users; bootstrap/live tests vẫn owner-operated. Không dùng admin/`REVIEWLENS_OWNER` làm runtime identity.
- R2 stage dùng direct scoped credentials theo Snowflake S3-compatible contract; rotation/revocation thuộc `IMP-M1-008`.
- Olist license cho phép non-commercial portfolio use theo CC BY-NC-SA, nhưng review free text vẫn cần DLP/privacy gate trước OpenRouter/Chroma và không được public raw.
- Snowflake trial hết hạn `2026-09-03`; ưu tiên hoàn tất M1 và M2/M3 vertical slice, giữ X-Small/60s/resource monitor.
- Product/seller insights từ review có multi-item ambiguity; M3 phải implement allocation/label policy, không nhân review rồi sum.

## Chi phí và tài nguyên

| Dịch vụ | Budget/gate hiện tại | Usage đã xác minh |
|---|---|---|
| OpenRouter | 5 USD/project; warning 0.50 USD/day | Không gọi trong phiên migration; 0 USD phát sinh từ code path project |
| Snowflake | ≤10 credits/month; X-Small, auto-suspend 60s | Không gọi trong phiên migration; prior stage/RBAC live pass và warehouses suspended |
| Cloudflare R2 | Standard; target ≤15 GB; private/lifecycle | Không upload Olist trong phiên; prior synthetic live objects cleaned up |
| ChromaDB | ≤5 GB local | Chưa provision/index |

## Input cần từ chủ project

Không cần input để tiếp tục M1. Khi đến `IMP-M1-008`, owner có thể cần tạo/
đăng ký public key cho dedicated Snowflake service users. Không gửi private key,
password, R2 secret hoặc OpenRouter key vào chat/tài liệu.

## Việc tiếp theo

1. `IMP-M1-008`: dedicated service identities and rotation/revocation skeleton.
2. Hoàn tất `IMP-M1-011`: OpenRouter, Chroma, audit and clock adapters/fakes.
3. `IMP-M1-009`: Snowflake-only dbt scaffold using the Olist relational model names.
4. `IMP-M1-010`: Airflow 3 `olist_pipeline` scaffold without import side effects.
5. Chỉ bắt đầu real Olist upload ở M2 sau machine-readable contract/manifest/privacy preflight.

## Tài liệu nguồn

- [PRD v2](./PRD.md)
- [Implementation plan v2](./IMPLEMENTATION_PLAN.md)
- [Dataset attribution](./DATA_ATTRIBUTION.md)
- [Olist source manifest](./data/OLIST_SOURCE_MANIFEST.md)
- [ADR-008 — Olist primary dataset](./ADR/ADR-008-olist-primary-dataset.md)
- [M0 decision register](./phases/M0/M0_DECISION_REGISTER.md)
- [RAG recommendation](./reviewlens_rag_recommendation.md)
- [Architecture diagram](./images/plan.png)
