# ReviewLens Project Status

> Đây là dashboard trạng thái ngắn gọn và là file đầu tiên cần đọc sau mỗi phiên phát triển. Chi tiết và bằng chứng nằm trong checklist/test cases của phase.

## Tổng quan

| Thuộc tính | Giá trị |
|---|---|
| Trạng thái tổng thể | `ON_TRACK` |
| Phase hiện tại | `M1` — Foundation, environments và developer platform |
| Trạng thái phase hiện tại | `NOT_STARTED` — entry account facts đã xác nhận; sẵn sàng scaffold bằng synthetic fixtures |
| Phase gần nhất hoàn tất | `M0` — 19/19 work items |
| Cập nhật lần cuối | 2026-08-04 |
| Người thực hiện | Solo Developer |
| Data policy hiện hành | Yelp data thật giữ local; cloud/AI/public demo dùng synthetic data cho tới khi compliance gate được mở |
| Cloud topology | Snowflake Standard/AWS Singapore ↔ private R2 Standard/APAC qua S3-compatible HTTPS stage |

## Tiến độ theo phase

| Phase | Trạng thái | Tóm tắt | Evidence |
|---|---|---|---|
| M0 | `COMPLETE` | Product, data, architecture, security và budget baselines | [Checklist](./phases/M0/M0_CHECKLIST.md) · [Tests](./phases/M0/M0_TEST_CASES.md) |
| M1 | `NOT_STARTED` | Foundation, environments và developer platform | [Entry inputs](./phases/M0/M0_USER_INPUTS.md); chưa tạo phase artifacts |
| M2 | `NOT_STARTED` | R2 ingestion và Snowflake Bronze | [Implementation plan](./IMPLEMENTATION_PLAN.md#8-m2--ingestion-cloudflare-r2-và-snowflake-bronze) |
| M3 | `NOT_STARTED` | Versioned Silver, Gold và release framework | [Implementation plan](./IMPLEMENTATION_PLAN.md#9-m3--versioned-silver-core-gold-và-release-framework) |
| M4 | `NOT_STARTED` | LLM review enrichment | [Implementation plan](./IMPLEMENTATION_PLAN.md#10-m4--llm-review-enrichment) |
| M5 | `NOT_STARTED` | Embedding, ChromaDB và RAG | [Implementation plan](./IMPLEMENTATION_PLAN.md#11-m5--embedding-vector-index-và-rag) |
| M6 | `NOT_STARTED` | Safe Text-to-SQL | [Implementation plan](./IMPLEMENTATION_PLAN.md#12-m6--safe-text-to-sql) |
| M7 | `NOT_STARTED` | Dashboard và end-to-end app | [Implementation plan](./IMPLEMENTATION_PLAN.md#13-m7--dashboard-và-end-to-end-application-integration) |
| M8 | `NOT_STARTED` | Production hardening và portfolio launch | [Implementation plan](./IMPLEMENTATION_PLAN.md#14-m8--production-hardening-và-launch) |

Milestone completion: **1/9**. Chỉ số này thể hiện gate đã đóng, không phải phần trăm effort vì độ lớn các phase khác nhau.

## Kết quả phiên gần nhất

- Hoàn tất M0 với 19/19 work items và toàn bộ artifact quyết định/baseline cần thiết.
- Ghi nhận 18 test `PASS`; 3 live integration smoke tests được chuyển sang M1 vì cần credentials.
- Tạo và xác minh project-local skill `$reviewlens-dev-workflow`; Codex đã tự nhận diện skill từ `.agents/skills` và validator pass 0 lỗi/0 cảnh báo.
- Ghi nhận Snowflake AWS Singapore/Standard trial và private R2 APAC bucket; topology tương thích qua S3-compatible external stage.
- Review RAG recommendation: nhận P0 safety/citation/chunking baseline; giữ BM25/RRF/FlashRank ở evaluation-gated/P1.

## Kiểm thử

| Phạm vi | Kết quả | Chi tiết |
|---|---|---|
| M0 | 18 `PASS`, 3 `DEFERRED`, 0 `FAIL` | [M0 test cases](./phases/M0/M0_TEST_CASES.md) |
| M1 | Chưa chạy | Test cases sẽ được tạo trước/đồng thời với M1 implementation |
| Status validator | `PASS` — 0 errors, 0 warnings | `.agents/skills/reviewlens-dev-workflow/scripts/validate_project_status.py` |

## Blocker và rủi ro

- Không có blocker đối với M1 scaffolding và live connectivity test bằng synthetic fixtures.
- Live R2/Snowflake/OpenRouter smoke tests cần account configuration và secrets đặt trong local environment; không paste secrets vào chat hoặc tài liệu.
- Project không thuộc chương trình academic chính thức và không có Yelp written approval. Educational intent/attribution không tự mở quyền đưa Yelp data thật lên managed cloud, external AI hoặc public artifacts; mặc định fail closed.
- Snowflake trial hết hạn `2026-09-03`, còn 30 ngày tại ngày cập nhật; ưu tiên M1 foundation và M2 synthetic vertical slice sớm, không trì hoãn live connectivity smoke.

## Chi phí và tài nguyên

| Dịch vụ | Budget/gate hiện tại | Usage đã xác minh |
|---|---|---|
| OpenRouter | 5 USD/project, cảnh báo 0.50 USD/ngày | Chưa đo |
| Snowflake | Tối đa 10 credits/tháng; X-SMALL, auto-suspend 60s | Trial balance hiển thị `US$400`; hết hạn `2026-09-03`; usage chưa đo |
| Cloudflare R2 | Mục tiêu không quá 15 GB, Standard storage | Bucket `reviewlens-data-dev`, APAC, private; usage chưa đo |
| ChromaDB | Không quá 5 GB local cho portfolio | Chưa đo |

## Input cần từ chủ project

Các input sau không chặn M1 scaffolding hoặc synthetic R2/Snowflake smoke:

1. Portfolio cần public live URL hay local demo + video/screenshots.
2. Có chấp nhận budget/model defaults trong M0 hay muốn điều chỉnh.
3. Ngày tải/truy cập Yelp dataset để tính `license_expires_at` trước mọi real-data local processing tiếp theo.

Không gửi password, Snowflake private key, R2 secret access key hoặc OpenRouter API key vào chat/tài liệu.

## Việc tiếp theo

1. Tạo `M1_CHECKLIST.md`, `M1_TEST_CASES.md` và phase README từ 19 work items của implementation plan.
2. Thực hiện `IMP-M1-001`: repo structure, Python package metadata, dependency lock và lint/type/test commands.
3. Thực hiện `IMP-M1-003` và `IMP-M1-004`: typed configuration cùng deterministic synthetic fixture generator.
4. Scaffold provider adapters bằng fakes, rồi chạy R2/Snowflake `LIST`/`COPY INTO` smoke chỉ với synthetic object khi local credentials sẵn sàng.
5. Ưu tiên M1/M2 vertical slice trước trial expiry; giữ RAG implementation cho M5 nhưng dùng recommendation disposition khi thiết kế interface từ M1.

## Tài liệu nguồn

- [PRD](./PRD.md)
- [Implementation plan](./IMPLEMENTATION_PLAN.md)
- [Phase delivery convention](./phases/README.md)
- [M0 overview](./phases/M0/README.md)
- [M0 decision register](./phases/M0/M0_DECISION_REGISTER.md)
- [RAG recommendation](./reviewlens_rag_recommendation.md)
- [Architecture diagram](./images/plan.png)
