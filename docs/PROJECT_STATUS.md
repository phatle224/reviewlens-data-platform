# ReviewLens Project Status

> Dashboard trạng thái ngắn gọn; checklist/test cases của phase là evidence chi tiết.

## Tổng quan

| Thuộc tính | Giá trị |
|---|---|
| Trạng thái tổng thể | `ON_TRACK` |
| Phase hiện tại | `M1` — Foundation and developer platform |
| Trạng thái phase hiện tại | `IN_PROGRESS` — 15 done, 1 partial, 4 not started |
| Phase gần nhất hoàn tất | `M0` — 19/19 work items, re-baselined for Olist |
| Cập nhật lần cuối | 2026-08-09 |
| Người thực hiện | Solo Developer |
| Active source | Olist Brazilian E-Commerce dataset — nine relational CSVs, CC BY-NC-SA 4.0 |
| Data policy hiện hành | Raw CSV/review/row-level/embedding artifacts outside Git; private R2/Snowflake after manifest/privacy gate; external AI only after DLP/minimization; public evidence synthetic/aggregate/redacted |
| Cloud topology | Snowflake Standard/AWS Singapore ↔ private R2 Standard/APAC via S3-compatible HTTPS stage |

## Tiến độ theo phase

| Phase | Trạng thái | Tóm tắt | Evidence |
|---|---|---|---|
| M0 | `COMPLETE` | Olist product/data/license/security/architecture baseline | [Checklist](./phases/M0/M0_CHECKLIST.md) · [Tests](./phases/M0/M0_TEST_CASES.md) |
| M1 | `IN_PROGRESS` | Config, identities, provider/dbt/Airflow boundaries, audit/logging, authenticated app shell and fail-closed CI gates | [Overview](./phases/M1/README.md) · [Checklist](./phases/M1/M1_CHECKLIST.md) · [Tests](./phases/M1/M1_TEST_CASES.md) |
| M2 | `NOT_STARTED` | Nine-file Olist ingestion, R2 and Bronze | [Plan](./IMPLEMENTATION_PLAN.md) |
| M3 | `NOT_STARTED` | Conformed Silver, Gold and atomic release | [Plan](./IMPLEMENTATION_PLAN.md) |
| M4 | `NOT_STARTED` | DLP-approved review enrichment | [Plan](./IMPLEMENTATION_PLAN.md) |
| M5 | `NOT_STARTED` | Embeddings, ChromaDB and grounded RAG | [Plan](./IMPLEMENTATION_PLAN.md) |
| M6 | `NOT_STARTED` | Guarded Text-to-SQL | [Plan](./IMPLEMENTATION_PLAN.md) |
| M7 | `NOT_STARTED` | Streamlit analytics and integrated consumption | [Plan](./IMPLEMENTATION_PLAN.md) |
| M8 | `NOT_STARTED` | Orchestration, hardening and portfolio evidence | [Plan](./IMPLEMENTATION_PLAN.md) |

Milestone completion: **1/9**. Đây là số gate đã đóng, không phải phần trăm effort.

## Kết quả phiên gần nhất

- Hoàn tất `IMP-M1-015`: least-privilege GitHub Actions workflow với locked sync, Ruff/Airflow rules, mypy, pytest coverage, dbt offline compile, repository policy, dependency audit và status validation.
- `reviewlens-policy` fail closed cho secret/env/key, Olist/row-level artifact, unsafe path và Docker/Compose artifact trước `IMP-M1-016`; output chỉ chứa path/rule và không echo nội dung.
- 18/18 focused CI/policy tests pass, gồm deliberate failing fixtures. Workflow không dùng repo secret/live flag, không silence failure và checkout không persist credential.
- Dependency audit phát hiện 17 advisory trong runtime/dev graph và thêm 1 advisory chưa có bản vá ở optional Chroma package. Các package có bản vá đã được nâng; inactive Chroma extra được gỡ khỏi M1 lock và chỉ được re-enable ở M5 khi có bản an toàn. Audit cuối không còn known vulnerability.
- Full offline regression: 151 pass, 5 expected live skips, 90.87% coverage; Ruff + Airflow 3 rules, mypy, dbt 1.12 warnings-as-errors, lock check và repository scan đều pass.
- Không gọi Snowflake/R2/OpenRouter/Chroma, không đọc/upload Olist row, không resume warehouse và không phát sinh project service cost.

## Kiểm thử

| Phạm vi | Kết quả | Chi tiết |
|---|---|---|
| M0 | 18 `PASS`, 3 `DEFERRED`, 0 `FAIL` | [M0 test cases](./phases/M0/M0_TEST_CASES.md) |
| M1 | 35 `PASS`, 6 `PENDING`, 0 `FAIL`, 0 `DEFERRED` | [M1 test cases](./phases/M1/M1_TEST_CASES.md); offline 151 pass/5 live skip; CI policy/dependency + authenticated AppTest/logging/audit/Airflow/dbt/provider/R2/stage/RBAC/JWT evidence |
| Quality | `PASS` | Ruff format/lint + Airflow 3 rules, mypy strict, dbt warnings-as-errors, 90.87% branch-aware coverage, uv lock check, repository scan và dependency audit with no known vulnerabilities |
| Status validator | `PASS` — 0 errors, 0 warnings | M0: 19 done/21 tests; M1: 20 work items/41 tests synchronized |

## Blocker và rủi ro

- Không có external blocker cho phần M1 còn lại.
- Dedicated service users đã enable, exact role-scoped named keys/JWT auth pass. Runtime không có đường fallback sang admin/`REVIEWLENS_OWNER`; controlled rotation/revocation smoke chưa chạy.
- R2 stage dùng direct scoped credentials theo Snowflake S3-compatible contract; rotation/revocation thuộc `IMP-M1-008`.
- Olist license cho phép non-commercial portfolio use theo CC BY-NC-SA, nhưng review free text vẫn cần DLP/privacy gate trước OpenRouter/Chroma và không được public raw.
- Snowflake trial hết hạn `2026-09-03`; ưu tiên hoàn tất M1 và M2/M3 vertical slice, giữ X-Small/60s/resource monitor.
- Product/seller insights từ review có multi-item ambiguity; M3 phải implement allocation/label policy, không nhân review rồi sum.
- Chroma adapter M1 vẫn là lazy/fake-tested boundary nhưng package runtime chưa được cài vì advisory chưa có bản vá; M5 phải chọn và audit một phiên bản/backend an toàn trước khi provision index.

## Chi phí và tài nguyên

| Dịch vụ | Budget/gate hiện tại | Usage đã xác minh |
|---|---|---|
| OpenRouter | 5 USD/project; warning 0.50 USD/day | Không gọi trong phiên CI; 0 USD phát sinh từ code path project |
| Snowflake | ≤10 credits/month; X-Small, auto-suspend 60s | CI/regression offline; dbt placeholder compile không kết nối provider; prior JWT evidence remain pass |
| Cloudflare R2 | Standard; target ≤15 GB; private/lifecycle | Dedicated ingest/stage synthetic live pass; smoke object cleaned up; không upload Olist |
| ChromaDB | ≤5 GB local | Typed/in-memory adapter tests only; chưa provision/index và 0 byte project data được ghi |

## Input cần từ chủ project

Không cần thêm credential hoặc gửi secret cho Codex. Tất cả runtime readiness hiện
`true`; 8 Snowflake key files tồn tại ngoài repository và live authentication pass.
Để đóng `IMP-M1-008`, cần owner xác nhận một maintenance window cho controlled
rotation/revocation smoke vì bước này chủ động thay đổi live authentication state.

## Việc tiếp theo

1. `IMP-M1-016`: tạo non-root app/Airflow container images và thay pre-container rejection bằng build/non-root CI gates.
2. `IMP-M1-017`: single-local Compose và immutable artifact metadata sau container gate.
3. `IMP-M1-018`: metrics sink và health visibility sau local runtime skeleton.
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
