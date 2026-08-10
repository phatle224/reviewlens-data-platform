# ReviewLens Project Status

> Dashboard trạng thái ngắn gọn; checklist/test cases của phase là evidence chi tiết.

## Tổng quan

| Thuộc tính | Giá trị |
|---|---|
| Trạng thái tổng thể | `ON_TRACK` |
| Phase hiện tại | `M1` — Foundation and developer platform |
| Trạng thái phase hiện tại | `IN_PROGRESS` — 19 done, 1 partial, 0 not started |
| Phase gần nhất hoàn tất | `M0` — 19/19 work items, re-baselined for Olist |
| Cập nhật lần cuối | 2026-08-11 |
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

- `IMP-M1-017`/TC-M1-025 đã đóng `DONE/PASS` bằng machine-readable Chroma quarantine: re-audit ngày 2026-08-11 xác nhận latest Python release 1.5.9 vẫn thuộc critical GHSA-f4j7-r4q5-qw2c/CVE-2026-45829 và chưa có patched version.
- `reviewlens-policy` fail closed nếu Chroma service, direct dependency hoặc lock entry xuất hiện; policy thiếu hoặc bị nới lỏng cũng bị chặn. Persistent Chroma giữ nguyên kiến trúc local nhưng chuyển đúng sequencing sang `IMP-M5-001` sau patched dependency/image audit.
- Compose M1 tiếp tục chỉ có hardened app/metrics/Airflow; artifact tag `local-sha256-4cac8b541993b042` build/runtime smoke pass, và hai tag cũ đã được xóa an toàn.
- Full offline gate có 178 pass + 5 expected live skips và 88.62% branch-aware coverage; dbt no-introspect, repository/artifact/status policy và dependency audit đều pass.
- Không gọi Snowflake/R2/OpenRouter/Chroma, không đọc/upload Olist và không phát sinh project service cost.

## Kiểm thử

| Phạm vi | Kết quả | Chi tiết |
|---|---|---|
| M0 | 18 `PASS`, 3 `DEFERRED`, 0 `FAIL` | [M0 test cases](./phases/M0/M0_TEST_CASES.md) |
| M1 | 40 `PASS`, 1 `PENDING`, 0 `FAIL`, 0 `DEFERRED` | [M1 test cases](./phases/M1/M1_TEST_CASES.md); offline 178 pass/5 live skip; Chroma quarantine + clean-path/container/Compose/artifact/metrics + CI policy/dependency/AppTest/logging/audit/Airflow/dbt/provider/R2/stage/RBAC/JWT evidence |
| Quality | `PASS` | Ruff format/lint + Airflow 3 rules, mypy strict, dbt warnings-as-errors, 88.62% branch-aware coverage, uv lock/artifact checks, repository scan và dependency audit with no known vulnerabilities |
| Status validator | `PASS` — 0 errors, 0 warnings | M0: 19 done/21 tests; M1: 20 work items/41 tests synchronized |

## Blocker và rủi ro

- Dedicated service users đã enable, exact role-scoped named keys/JWT auth pass. Runtime không có đường fallback sang admin/`REVIEWLENS_OWNER`; controlled rotation/revocation smoke chưa chạy.
- R2 stage dùng direct scoped credentials theo Snowflake S3-compatible contract; rotation/revocation thuộc `IMP-M1-008`.
- Olist license cho phép non-commercial portfolio use theo CC BY-NC-SA, nhưng review free text vẫn cần DLP/privacy gate trước OpenRouter/Chroma và không được public raw.
- Snowflake trial hết hạn `2026-09-03`; ưu tiên hoàn tất M1 và M2/M3 vertical slice, giữ X-Small/60s/resource monitor.
- Product/seller insights từ review có multi-item ambiguity; M3 phải implement allocation/label policy, không nhân review rồi sum.
- Chroma adapter M1 vẫn là lazy/fake-tested boundary. Machine-readable quarantine chặn package/server 1.5.9 và mọi addition chưa được review; `IMP-M5-001` phải thay policy có chủ đích chỉ sau khi một patched release qua dependency/image audit và negative access smoke.

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
Không cần tải Olist data hoặc gọi cloud provider cho phần M1 local còn lại.
Để đóng `IMP-M1-008`, cần owner xác nhận một maintenance window cho controlled
rotation/revocation smoke vì bước này chủ động thay đổi live authentication state.

## Việc tiếp theo

1. Khi owner xác nhận maintenance window: chạy controlled key rotation/revocation smoke để đóng `IMP-M1-008` và M1.
2. Sau M1 exit, bắt đầu M2 bằng machine-readable nine-file contracts và synthetic compatibility fixtures; chưa cần Olist upload.
3. Chỉ bắt đầu real Olist upload ở M2 sau contract/manifest/privacy preflight.
4. Re-audit Chroma tại `IMP-M5-001`; không bypass blocked policy để provision sớm.

## Tài liệu nguồn

- [PRD v2](./PRD.md)
- [Implementation plan v2](./IMPLEMENTATION_PLAN.md)
- [Dataset attribution](./DATA_ATTRIBUTION.md)
- [Olist source manifest](./data/OLIST_SOURCE_MANIFEST.md)
- [ADR-008 — Olist primary dataset](./ADR/ADR-008-olist-primary-dataset.md)
- [M0 decision register](./phases/M0/M0_DECISION_REGISTER.md)
- [RAG recommendation](./reviewlens_rag_recommendation.md)
- [Credential rotation runbook](./runbooks/M1_CREDENTIAL_ROTATION.md)
- [Foundation operations runbook](./runbooks/M1_FOUNDATION_OPERATIONS.md)
- [Architecture diagram](./images/plan.png)
