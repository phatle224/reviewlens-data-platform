# ReviewLens Project Status

> Đây là dashboard trạng thái ngắn gọn và là file đầu tiên cần đọc sau mỗi phiên phát triển. Chi tiết và bằng chứng nằm trong checklist/test cases của phase.

## Tổng quan

| Thuộc tính | Giá trị |
|---|---|
| Trạng thái tổng thể | `ON_TRACK` |
| Phase hiện tại | `M1` — Foundation, single-local configuration và developer platform |
| Trạng thái phase hiện tại | `IN_PROGRESS` — 4 work items done, 2 partial; bootstrap và R2 live slice hoạt động |
| Phase gần nhất hoàn tất | `M0` — 19/19 work items |
| Cập nhật lần cuối | 2026-08-04 |
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

- Đóng `IMP-M1-001/002`: full locked bootstrap pass; thêm README, contribution guide, CODEOWNERS, PR và issue templates.
- Credential readiness đầy đủ và được kiểm tra chỉ bằng boolean; `.env` ignored/untracked. Snowflake đang dùng key-pair.
- Tạo reusable bucket-scoped R2 adapter với fakes, lifecycle contract và live synthetic smoke test.
- R2 live pass: put/head/get/list/checksum, account-level bucket-list denial, anonymous payload denial và cleanup/absence confirmation.
- `IMP-M1-005/011` ở trạng thái `PARTIAL`: chờ owner apply lifecycle; các provider adapters khác chưa implement.

## Kiểm thử

| Phạm vi | Kết quả | Chi tiết |
|---|---|---|
| M0 | 18 `PASS`, 3 `DEFERRED`, 0 `FAIL` | [M0 test cases](./phases/M0/M0_TEST_CASES.md) |
| M1 | 13 `PASS`, 0 `FAIL`, 2 `DEFERRED`, 15 `PENDING` | [M1 test cases](./phases/M1/M1_TEST_CASES.md); offline suite 15 pass/1 live skip và R2 live test pass |
| Status validator | `PASS` — 0 errors, 0 warnings | `.agents/skills/reviewlens-dev-workflow/scripts/validate_project_status.py` |

## Blocker và rủi ro

- Không có external blocker đối với M1 scaffolding và live connectivity test bằng synthetic fixtures.
- R2 lifecycle artifact chưa được apply/verified trên bucket; application token cố ý không có bucket-admin authority. Owner cần apply bằng Dashboard hoặc owner-operated Wrangler.
- Snowflake private key hiện nằm trong workspace nhưng đã ignored/untracked; cần chuyển ra ngoài repository và cập nhật local `.env` trước Snowflake live work.
- Snowflake live stage và RBAC tests vẫn cần provision foundation/service roles; không paste secrets vào chat hoặc tài liệu.
- Project không thuộc chương trình academic chính thức và không có Yelp written approval. Educational intent/attribution không tự mở quyền đưa Yelp data thật lên managed cloud, external AI hoặc public artifacts; mặc định fail closed.
- Snowflake trial hết hạn `2026-09-03`, còn 30 ngày tại ngày cập nhật; ưu tiên M1 foundation và M2 synthetic vertical slice sớm, không trì hoãn live connectivity smoke.

## Chi phí và tài nguyên

| Dịch vụ | Budget/gate hiện tại | Usage đã xác minh |
|---|---|---|
| OpenRouter | 5 USD/project, cảnh báo 0.50 USD/ngày | Chưa đo |
| Snowflake | Tối đa 10 credits/tháng; X-SMALL, auto-suspend 60s | Trial balance hiển thị `US$400`; hết hạn `2026-09-03`; usage chưa đo |
| Cloudflare R2 | Mục tiêu không quá 15 GB, Standard storage | Live smoke tạo/xóa 2 synthetic test objects trong phiên; bucket private và scoped-token denial đã xác minh |
| ChromaDB | Không quá 5 GB local cho portfolio | Chưa đo |

## Input cần từ chủ project

Không còn product/architecture/config input chặn M1. Trước M1 Snowflake live slice, owner cần:

1. Apply lifecycle rule `expire-reviewlens-smoke-objects` từ `infra/cloudflare_r2/lifecycle.json` vào bucket và xác nhận rule đang enabled.
2. Chuyển Snowflake private key ra ngoài repository, rồi chỉ cập nhật `SNOWFLAKE_PRIVATE_KEY_PATH` trong local `.env`.

Không gửi lifecycle/admin token, password, private key, R2 secret access key hoặc OpenRouter API key vào chat/tài liệu.

Không gửi password, Snowflake private key, R2 secret access key hoặc OpenRouter API key vào chat/tài liệu.

## Việc tiếp theo

1. Owner apply/verify R2 smoke lifecycle và chuyển Snowflake private key ra ngoài repo; đóng `IMP-M1-005`.
2. Thực hiện `IMP-M1-006`: idempotent Snowflake foundation, X-SMALL/60s/resource monitor và R2 external stage.
3. Thực hiện `IMP-M1-007/008`: least-privilege service roles, key rotation/revocation skeleton và negative tests.
4. Hoàn tất `IMP-M1-011` với Snowflake/OpenRouter/Chroma/audit/clock adapters và fakes.
5. Scaffold Snowflake-only dbt, Airflow và local Docker Compose sau khi foundation/RBAC pass.

## Tài liệu nguồn

- [PRD](./PRD.md)
- [Implementation plan](./IMPLEMENTATION_PLAN.md)
- [Phase delivery convention](./phases/README.md)
- [M0 overview](./phases/M0/README.md)
- [M0 decision register](./phases/M0/M0_DECISION_REGISTER.md)
- [RAG recommendation](./reviewlens_rag_recommendation.md)
- [Architecture diagram](./images/plan.png)
