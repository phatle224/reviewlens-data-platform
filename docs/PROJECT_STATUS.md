# ReviewLens Project Status

> Dashboard trạng thái ngắn gọn; checklist/test cases của phase là evidence chi tiết.

## Tổng quan

| Thuộc tính | Giá trị |
|---|---|
| Trạng thái tổng thể | `ON_TRACK` |
| Phase hiện tại | `M1` — Foundation and developer platform |
| Trạng thái phase hiện tại | `IN_PROGRESS` — 9 done, 1 partial, 10 not started |
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
| M1 | `IN_PROGRESS` | Config, Olist fixtures, R2/Snowflake foundation, RBAC, dedicated identity skeleton and migration | [Overview](./phases/M1/README.md) · [Checklist](./phases/M1/M1_CHECKLIST.md) · [Tests](./phases/M1/M1_TEST_CASES.md) |
| M2 | `NOT_STARTED` | Nine-file Olist ingestion, R2 and Bronze | [Plan](./IMPLEMENTATION_PLAN.md) |
| M3 | `NOT_STARTED` | Conformed Silver, Gold and atomic release | [Plan](./IMPLEMENTATION_PLAN.md) |
| M4 | `NOT_STARTED` | DLP-approved review enrichment | [Plan](./IMPLEMENTATION_PLAN.md) |
| M5 | `NOT_STARTED` | Embeddings, ChromaDB and grounded RAG | [Plan](./IMPLEMENTATION_PLAN.md) |
| M6 | `NOT_STARTED` | Guarded Text-to-SQL | [Plan](./IMPLEMENTATION_PLAN.md) |
| M7 | `NOT_STARTED` | Streamlit analytics and integrated consumption | [Plan](./IMPLEMENTATION_PLAN.md) |
| M8 | `NOT_STARTED` | Orchestration, hardening and portfolio evidence | [Plan](./IMPLEMENTATION_PLAN.md) |

Milestone completion: **1/9**. Đây là số gate đã đóng, không phải phần trăm effort.

## Kết quả phiên gần nhất

- Hoàn tất `IMP-M1-011`: sáu typed provider/runtime boundaries R2, Snowflake, OpenRouter, Chroma, audit và clock đều có deterministic fake/negative tests.
- OpenRouter adapter pin model từ config, chỉ nhận internal-control/synthetic/hash-verified DLP-approved text, bật provider `data_collection=deny` và sanitize mọi lỗi. Không có request thật hoặc chi phí AI.
- Chroma adapter chỉ kết nối loopback bằng token, tạo collection theo `index_version`, không lưu document text và fail closed nếu source/release/index metadata không khớp authoritative Snowflake `AI.RAG_DOCUMENT`. Không tạo index thật.
- Audit/clock boundary cung cấp immutable events, secret-key denial, in-memory sink và frozen UTC clock; Snowflake audit schema vẫn thuộc dependency kế tiếp `IMP-M1-013`.
- Credential readiness hiện đầy đủ. Approved metadata-only check xác nhận đủ 8 private + 8 public key files sau Windows ACL; không đọc nội dung key.
- Live Snowflake JWT pass cho cả 8 service identities: named key active/role-scoped, current user/role/warehouse/database đúng và secondary roles trống; warehouses đã suspend.
- Sửa hardening sau khi live test phát hiện role-restricted session không được chạy `USE SECONDARY ROLES NONE`: adapter chuyển sang verify `CURRENT_SECONDARY_ROLES()` và fail closed nếu khác rỗng.
- Implement dedicated R2 runtime adapters và chuyển external stage sang `R2_STAGE_*`: ingestion write/read/delete; stage read/list/COPY pass, direct write bị Cloudflare deny; account-list denied; synthetic cleanup thành công.
- Full offline gate: 91 pass, 5 expected live skips, 90.09% coverage; Ruff, mypy, lock check và locked offline sync pass. Không gọi OpenRouter, không ghi Chroma và không truy cập Olist source data.

## Kiểm thử

| Phạm vi | Kết quả | Chi tiết |
|---|---|---|
| M0 | 18 `PASS`, 3 `DEFERRED`, 0 `FAIL` | [M0 test cases](./phases/M0/M0_TEST_CASES.md) |
| M1 | 28 `PASS`, 13 `PENDING`, 0 `FAIL`, 0 `DEFERRED` | [M1 test cases](./phases/M1/M1_TEST_CASES.md); offline 91 pass/5 live skip; six provider/runtime boundary suites plus synthetic R2, dedicated stage/RBAC, 8-key JWT auth and R2 identity live evidence |
| Quality | `PASS` | Ruff format/lint, mypy strict, 90.09% branch-aware coverage, uv lock check và locked offline sync |
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
| Snowflake | ≤10 credits/month; X-Small, auto-suspend 60s | 8 JWT metadata/auth sessions pass; không query business data; both warehouses suspended |
| Cloudflare R2 | Standard; target ≤15 GB; private/lifecycle | Dedicated ingest/stage synthetic live pass; smoke object cleaned up; không upload Olist |
| ChromaDB | ≤5 GB local | Typed/in-memory adapter tests only; chưa provision/index và 0 byte project data được ghi |

## Input cần từ chủ project

Không cần thêm credential hoặc gửi secret cho Codex. Tất cả runtime readiness hiện
`true`; 8 Snowflake key files tồn tại ngoài repository và live authentication pass.
Để đóng `IMP-M1-008`, cần owner xác nhận một maintenance window cho controlled
rotation/revocation smoke vì bước này chủ động thay đổi live authentication state.

## Việc tiếp theo

1. `IMP-M1-009`: Snowflake-only dbt scaffold using the Olist relational model names.
2. `IMP-M1-010`: Airflow 3 `olist_pipeline` scaffold without import side effects.
3. Khi owner xác nhận maintenance window: chạy controlled key rotation/revocation smoke để đóng `IMP-M1-008`.
4. Tiếp tục `IMP-M1-013` audit schema rồi `IMP-M1-014` logging/redaction theo dependency graph.
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
