# ReviewLens Project Status

> Đây là dashboard trạng thái ngắn gọn và là file đầu tiên cần đọc sau mỗi phiên phát triển. Chi tiết và bằng chứng nằm trong checklist/test cases của phase.

## Tổng quan

| Thuộc tính | Giá trị |
|---|---|
| Trạng thái tổng thể | `ON_TRACK` |
| Phase hiện tại | `M1` — Foundation, single-local configuration và developer platform |
| Trạng thái phase hiện tại | `IN_PROGRESS` — 6 work items done, 1 partial; R2 và Snowflake foundation live slice hoạt động |
| Phase gần nhất hoàn tất | `M0` — 19/19 work items |
| Cập nhật lần cuối | 2026-08-05 |
| Người thực hiện | Solo Developer |
| Data policy hiện hành | Yelp data thật giữ local; cloud/AI/public demo dùng synthetic data cho tới khi compliance gate được mở |
| Cloud topology | Snowflake Standard/AWS Singapore ↔ private R2 Standard/APAC qua S3-compatible HTTPS stage |

## Tiến độ theo phase

| Phase | Trạng thái | Tóm tắt | Evidence |
|---|---|---|---|
| M0 | `COMPLETE` | Product, data, architecture, security và budget baselines | [Checklist](./phases/M0/M0_CHECKLIST.md) · [Tests](./phases/M0/M0_TEST_CASES.md) |
| M1 | `IN_PROGRESS` | Foundation, single-local configuration và developer platform | [M1 overview](./phases/M1/README.md) · [Checklist](./phases/M1/M1_CHECKLIST.md) · [Tests](./phases/M1/M1_TEST_CASES.md) |
| M2 | `NOT_STARTED` | R2 ingestion và Snowflake Bronze | [Implementation plan](./IMPLEMENTATION_PLAN.md#8-m2--ingestion-cloudflare-r2-và-snowflake-bronze) |
| M3 | `NOT_STARTED` | Versioned Silver, Gold và release framework | [Implementation plan](./IMPLEMENTATION_PLAN.md#9-m3--versioned-silver-core-gold-và-release-framework) |
| M4 | `NOT_STARTED` | LLM review enrichment | [Implementation plan](./IMPLEMENTATION_PLAN.md#10-m4--llm-review-enrichment) |
| M5 | `NOT_STARTED` | Embedding, ChromaDB và RAG | [Implementation plan](./IMPLEMENTATION_PLAN.md#11-m5--embedding-vector-index-và-rag) |
| M6 | `NOT_STARTED` | Safe Text-to-SQL | [Implementation plan](./IMPLEMENTATION_PLAN.md#12-m6--safe-text-to-sql) |
| M7 | `NOT_STARTED` | Dashboard và end-to-end app | [Implementation plan](./IMPLEMENTATION_PLAN.md#13-m7--dashboard-và-end-to-end-application-integration) |
| M8 | `NOT_STARTED` | Portfolio hardening và launch evidence | [Implementation plan](./IMPLEMENTATION_PLAN.md#14-m8--portfolio-hardening-và-launch-evidence) |

Milestone completion: **1/9**. Chỉ số này thể hiện gate đã đóng, không phải phần trăm effort vì độ lớn các phase khác nhau.

## Kết quả phiên gần nhất

- Đóng `IMP-M1-005`: owner xác nhận lifecycle đã enabled; Snowflake private key đã nằm ngoài repo; R2 private/scoped live checks vẫn pass.
- Đóng `IMP-M1-006`: thêm secret-free Snowflake foundation DDL, XSMALL/60s, 10-credit resource monitor, JSONL format và private R2 S3-compatible external stage dựng trong bộ nhớ.
- Snowflake live pass: foundation deploy, R2 exact-key `LIST`, một-row synthetic `COPY INTO`/reconcile, R2 cleanup và warehouse suspend.
- Thêm Snowflake provider adapter/fakes, key-pair bootstrap, safe identifier/path checks và sanitized errors; `IMP-M1-011` vẫn `PARTIAL` do còn OpenRouter/Chroma/audit/clock.
- Full offline gate pass: 30 test, 86.47% coverage, Ruff, mypy, lock check và locked offline sync đều sạch.

## Kiểm thử

| Phạm vi | Kết quả | Chi tiết |
|---|---|---|
| M0 | 18 `PASS`, 3 `DEFERRED`, 0 `FAIL` | [M0 test cases](./phases/M0/M0_TEST_CASES.md) |
| M1 | 15 `PASS`, 0 `FAIL`, 1 `DEFERRED`, 14 `PENDING` | [M1 test cases](./phases/M1/M1_TEST_CASES.md); offline suite 30 pass/2 live skip; R2 và Snowflake live tests pass riêng |
| Status validator | `PASS` — 0 errors, 0 warnings | `.agents/skills/reviewlens-dev-workflow/scripts/validate_project_status.py` |

## Blocker và rủi ro

- Không có external blocker đối với M1 scaffolding và live connectivity test bằng synthetic fixtures.
- R2 stage hiện dùng direct scoped credentials theo giới hạn của Snowflake S3-compatible stage; rotation/revocation và service-role boundaries sẽ được khóa ở `IMP-M1-007/008`.
- RBAC positive/negative live tests chưa chạy vì service roles thuộc work item tiếp theo; bootstrap hiện vẫn là owner-operated account role.
- Project không thuộc chương trình academic chính thức và không có Yelp written approval. Educational intent/attribution không tự mở quyền đưa Yelp data thật lên managed cloud, external AI hoặc public artifacts; mặc định fail closed.
- Snowflake trial hết hạn `2026-09-03`, còn 30 ngày tại ngày cập nhật; ưu tiên M1 foundation và M2 synthetic vertical slice sớm, không trì hoãn live connectivity smoke.

## Chi phí và tài nguyên

| Dịch vụ | Budget/gate hiện tại | Usage đã xác minh |
|---|---|---|
| OpenRouter | 5 USD/project, cảnh báo 0.50 USD/ngày | Chưa đo |
| Snowflake | Tối đa 10 credits/tháng; X-SMALL, auto-suspend 60s | Trial balance input `US$400`; hết hạn `2026-09-03`; live one-row COPY pass và warehouse được suspend, exact credit delta chưa đo |
| Cloudflare R2 | Mục tiêu không quá 15 GB, Standard storage | Lifecycle enabled; live Snowflake attempts trong phiên đều cleanup synthetic object; bucket private và scoped-token denial đã xác minh |
| ChromaDB | Không quá 5 GB local cho portfolio | Chưa đo |

## Input cần từ chủ project

Không còn input từ owner chặn `IMP-M1-007/008`. Credential hiện tại chỉ được đọc từ ignored `.env`; không gửi lifecycle/admin token, password, private key, R2 secret access key hoặc OpenRouter API key vào chat/tài liệu.

## Việc tiếp theo

1. Thực hiện `IMP-M1-007`: least-privilege Snowflake service roles cùng static/live positive-negative grant tests.
2. Thực hiện `IMP-M1-008`: credential rotation/revocation skeleton cho Snowflake/R2/OpenRouter/Chroma và app auth.
3. Hoàn tất `IMP-M1-011` với OpenRouter/Chroma/audit/clock adapters và fakes.
4. Scaffold Snowflake-only dbt, Airflow và local Docker Compose sau khi foundation/RBAC pass.

## Tài liệu nguồn

- [PRD](./PRD.md)
- [Implementation plan](./IMPLEMENTATION_PLAN.md)
- [Phase delivery convention](./phases/README.md)
- [M0 overview](./phases/M0/README.md)
- [M0 decision register](./phases/M0/M0_DECISION_REGISTER.md)
- [RAG recommendation](./reviewlens_rag_recommendation.md)
- [Architecture diagram](./images/plan.png)
