# ReviewLens Project Status

> Dashboard trạng thái ngắn gọn; checklist/test cases của phase là evidence chi tiết.

## Tổng quan

| Thuộc tính | Giá trị |
|---|---|
| Trạng thái tổng thể | `ON_TRACK` |
| Phase hiện tại | `M3` — Conformed Silver, Gold and atomic release |
| Trạng thái phase hiện tại | `IN_PROGRESS` — 16/20 work items complete; 26/30 phase tests pass |
| Phase gần nhất hoàn tất | `M2` — nine-file private R2/Bronze ingestion and replay gate |
| Cập nhật lần cuối | 2026-08-15 |
| Người thực hiện | Solo Developer |
| Active source | Olist Brazilian E-Commerce dataset — nine relational CSVs, CC BY-NC-SA 4.0 |
| Data policy hiện hành | Raw CSV/review/row-level/embedding artifacts outside Git; private R2/Snowflake after manifest/privacy gate; external AI only after DLP/minimization; public evidence synthetic/aggregate/redacted |
| Cloud topology | Snowflake Standard/AWS Singapore ↔ private R2 Standard/APAC via S3-compatible HTTPS stage |

## Tiến độ theo phase

| Phase | Trạng thái | Tóm tắt | Evidence |
|---|---|---|---|
| M0 | `COMPLETE` | Olist product/data/license/security/architecture baseline | [Checklist](./phases/M0/M0_CHECKLIST.md) · [Tests](./phases/M0/M0_TEST_CASES.md) |
| M1 | `COMPLETE` | Config, identities, provider/dbt/Airflow boundaries, audit/logging, authenticated app shell and fail-closed CI/live rotation gates | [Overview](./phases/M1/README.md) · [Checklist](./phases/M1/M1_CHECKLIST.md) · [Tests](./phases/M1/M1_TEST_CASES.md) |
| M2 | `COMPLETE` | 18 implementation items and owner-approved full nine-file private DAG + immutable replay reconcile with empty alerts and warehouse suspended | [Overview](./phases/M2/README.md) · [Checklist](./phases/M2/M2_CHECKLIST.md) · [Tests](./phases/M2/M2_TEST_CASES.md) |
| M3 | `IN_PROGRESS` | Silver/DQ, conformed facts/dimensions, review allocation, four marts and curated semantic views complete offline (16/20) | [Overview](./phases/M3/README.md) · [Checklist](./phases/M3/M3_CHECKLIST.md) · [Tests](./phases/M3/M3_TEST_CASES.md) |
| M4 | `NOT_STARTED` | DLP-approved review enrichment | [Plan](./IMPLEMENTATION_PLAN.md) |
| M5 | `NOT_STARTED` | Embeddings, ChromaDB and grounded RAG | [Plan](./IMPLEMENTATION_PLAN.md) |
| M6 | `NOT_STARTED` | Guarded Text-to-SQL | [Plan](./IMPLEMENTATION_PLAN.md) |
| M7 | `NOT_STARTED` | Streamlit analytics and integrated consumption | [Plan](./IMPLEMENTATION_PLAN.md) |
| M8 | `NOT_STARTED` | Orchestration, hardening and portfolio evidence | [Plan](./IMPLEMENTATION_PLAN.md) |

Milestone completion: **3/9**. Đây là số gate đã đóng, không phải phần trăm effort.

## Kết quả phiên gần nhất

- Hoàn tất offline `IMP-M3-016`: semantic catalog v1 và bốn curated dbt views cho delivery, product-review, seller và customer.
- Dashboard/Text-to-SQL chỉ dùng logical names và approved fields; physical identifiers, natural IDs, review text, unsafe roles và early serving grants bị chặn. Product/seller order counts được gắn nhãn nonadditive; AI enrichment vẫn hiển thị partial cho tới M4.
- ADR-013 giữ active-release resolution cho `IMP-M3-018/019`; candidate semantic views chưa tự publish hoặc grant quyền serving.
- Ruff, strict mypy, dbt parse warnings-as-errors, 82 focused M3 tests và full offline regression pass. Không build Docker image và không gọi Snowflake, R2, OpenRouter hoặc Chroma.

## Kiểm thử

| Phạm vi | Kết quả | Chi tiết |
|---|---|---|
| M0 | 18 `PASS`, 3 `DEFERRED`, 0 `FAIL` | [M0 test cases](./phases/M0/M0_TEST_CASES.md) |
| M1 | 41 `PASS`, 0 `PENDING`, 0 `FAIL`, 0 `DEFERRED` | [M1 test cases](./phases/M1/M1_TEST_CASES.md); offline 193 pass/6 live skip plus owner-approved live rotation 1 pass; Chroma quarantine + clean-path/container/Compose/artifact/metrics + CI policy/dependency/AppTest/logging/audit/Airflow/dbt/provider/R2/stage/RBAC/JWT evidence |
| M2 | 25 `PASS`, 0 `PENDING`, 0 `FAIL`, 0 `DEFERRED` | [M2 test cases](./phases/M2/M2_TEST_CASES.md); offline, synthetic live and full private nine-file DAG/replay evidence pass |
| M3 | 26 `PASS`, 4 `PENDING`, 0 `FAIL`, 0 `DEFERRED` | [M3 test cases](./phases/M3/M3_TEST_CASES.md); first sixteen work items pass offline contracts; live candidate build and release work are not claimed |
| Quality | `PASS` | 428 offline tests pass + 8 expected opt-in live skips, 86.41% coverage; Ruff, strict mypy, dbt parse, policy/artifact/dependency locks pass |
| Status validator | `PASS` — 0 errors, 0 warnings | M0–M2 complete; M3 synchronized at 16/20 done and 26/30 pass |

## Blocker và rủi ro

- Raw Olist hiện nằm trong private R2 dưới immutable release prefix. Không public object, không cleanup/overwrite thủ công; retention 90 ngày vẫn áp dụng theo baseline.
- Olist license cho phép non-commercial portfolio use theo CC BY-NC-SA, nhưng review free text vẫn cần DLP/privacy gate trước OpenRouter/Chroma và không được public raw.
- Snowflake trial hết hạn `2026-09-03`; ưu tiên M3 vertical slice, giữ X-Small/60s/resource monitor.
- Product/seller review insights remain allocations, not item-level evidence; semantic views expose the policy label and mark order counts as nonadditive.
- Chroma adapter M1 vẫn là lazy/fake-tested boundary. Machine-readable quarantine chặn package/server 1.5.9 và mọi addition chưa được review; `IMP-M5-001` phải thay policy có chủ đích chỉ sau khi một patched release qua dependency/image audit và negative access smoke.

## Chi phí và tài nguyên

| Dịch vụ | Budget/gate hiện tại | Usage đã xác minh |
|---|---|---|
| OpenRouter | 5 USD/project; warning 0.50 USD/day | Không gọi trong phiên CI; 0 USD phát sinh từ code path project |
| Snowflake | ≤10 credits/month; X-Small, auto-suspend 60s | Nine Bronze tables contain 1,289,091 reconciled accepted rows; replay has zero duplicate committed effect and warehouse suspended |
| Cloudflare R2 | Standard; target ≤15 GB; private/lifecycle | 9 approved CSV (~126.19 MB), source manifest and immutable raw/quarantine artifacts retained privately; replay verified create-only objects |
| ChromaDB | ≤5 GB local | Typed/in-memory adapter tests only; chưa provision/index và 0 byte project data được ghi |

## Input cần từ chủ project

Không cần thêm credential hoặc secret cho `IMP-M3-017`. Candidate build/test
target có thể được scaffold và kiểm thử offline; execution trên Snowflake chỉ
chạy sau khi workflow nêu rõ chi phí và nhận xác nhận của owner.

## Việc tiếp theo

1. Implement `IMP-M3-017`: fail-closed candidate Gold build/test target covering marts and semantic views.
2. Keep review text private and `ai_eligible=false`; only M4 may create a DLP-approved external projection.
3. Avoid Docker builds for dbt/docs-only bundles and keep every model under the candidate namespace.
4. Defer migration `006` and live dbt build/source freshness until an explicit owner-approved Snowflake gate.
5. Re-audit Chroma tại `IMP-M5-001`; không bypass blocked policy để provision sớm.

## Tài liệu nguồn

- [PRD v2](./PRD.md)
- [Implementation plan v2](./IMPLEMENTATION_PLAN.md)
- [Dataset attribution](./DATA_ATTRIBUTION.md)
- [Olist source manifest](./data/OLIST_SOURCE_MANIFEST.md)
- [ADR-008 — Olist primary dataset](./ADR/ADR-008-olist-primary-dataset.md)
- [ADR-009 — Bronze decimal projection](./ADR/ADR-009-bronze-decimal-projection.md)
- [ADR-010 — duplicate observability semantics](./ADR/ADR-010-duplicate-observability-semantics.md)
- [ADR-011 — review-to-item attribution policy](./ADR/ADR-011-review-item-attribution-policy.md)
- [ADR-012 — Gold mart grains and metric semantics](./ADR/ADR-012-gold-mart-metric-semantics.md)
- [ADR-013 — semantic serving boundary](./ADR/ADR-013-semantic-serving-boundary.md)
- [M0 decision register](./phases/M0/M0_DECISION_REGISTER.md)
- [M2 overview](./phases/M2/README.md)
- [M2 checklist](./phases/M2/M2_CHECKLIST.md)
- [M2 test cases](./phases/M2/M2_TEST_CASES.md)
- [M3 overview](./phases/M3/README.md)
- [M3 checklist](./phases/M3/M3_CHECKLIST.md)
- [M3 test cases](./phases/M3/M3_TEST_CASES.md)
- [RAG recommendation](./reviewlens_rag_recommendation.md)
- [Credential rotation runbook](./runbooks/M1_CREDENTIAL_ROTATION.md)
- [Foundation operations runbook](./runbooks/M1_FOUNDATION_OPERATIONS.md)
- [M2 ingestion operations runbook](./runbooks/M2_INGESTION_OPERATIONS.md)
- [Architecture diagram](./images/plan.png)
