# ReviewLens Project Status

> Dashboard trạng thái ngắn gọn; checklist/test cases của phase là evidence chi tiết.

## Tổng quan

| Thuộc tính | Giá trị |
|---|---|
| Trạng thái tổng thể | `ON_TRACK` |
| Phase hiện tại | `M2` — Olist ingestion, R2 and immutable Bronze |
| Trạng thái phase hiện tại | `COMPLETE` — 18/18 work items, 25/25 phase tests and full private DAG/replay exit gate pass |
| Phase gần nhất hoàn tất | `M2` — nine-file private R2/Bronze ingestion and replay gate |
| Cập nhật lần cuối | 2026-08-14 |
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
| M3 | `NOT_STARTED` | Conformed Silver, Gold and atomic release | [Plan](./IMPLEMENTATION_PLAN.md) |
| M4 | `NOT_STARTED` | DLP-approved review enrichment | [Plan](./IMPLEMENTATION_PLAN.md) |
| M5 | `NOT_STARTED` | Embeddings, ChromaDB and grounded RAG | [Plan](./IMPLEMENTATION_PLAN.md) |
| M6 | `NOT_STARTED` | Guarded Text-to-SQL | [Plan](./IMPLEMENTATION_PLAN.md) |
| M7 | `NOT_STARTED` | Streamlit analytics and integrated consumption | [Plan](./IMPLEMENTATION_PLAN.md) |
| M8 | `NOT_STARTED` | Orchestration, hardening and portfolio evidence | [Plan](./IMPLEMENTATION_PLAN.md) |

Milestone completion: **3/9**. Đây là số gate đã đóng, không phải phần trăm effort.

## Kết quả phiên gần nhất

- Owner-approved full private DAG run và hai replay runs đều kết thúc `success`; clean replay dùng locked runtime image và final image preserves the same tested code with synchronized metadata.
- Chín dataset giải thích đủ 1,550,922 source rows thành 1,289,091 accepted/Bronze, 261,831 exact duplicates, 0 invalid quarantine và 0 parse failures.
- ADR-009 sửa projection DECIMAL scale 18 trong Bronze/Parquet mà vẫn giữ exact source value trong private raw payload; ADR-010 tách duplicate khỏi invalid quarantine để loại false-positive alert.
- Clean replay ghi 19 object/load replays, 0 task errors, reconciled=1, warehouse-suspended=1 và alert list rỗng. M3+ tasks skip đúng fail-closed guard; OpenRouter/Chroma không được gọi.

## Kiểm thử

| Phạm vi | Kết quả | Chi tiết |
|---|---|---|
| M0 | 18 `PASS`, 3 `DEFERRED`, 0 `FAIL` | [M0 test cases](./phases/M0/M0_TEST_CASES.md) |
| M1 | 41 `PASS`, 0 `PENDING`, 0 `FAIL`, 0 `DEFERRED` | [M1 test cases](./phases/M1/M1_TEST_CASES.md); offline 193 pass/6 live skip plus owner-approved live rotation 1 pass; Chroma quarantine + clean-path/container/Compose/artifact/metrics + CI policy/dependency/AppTest/logging/audit/Airflow/dbt/provider/R2/stage/RBAC/JWT evidence |
| M2 | 25 `PASS`, 0 `PENDING`, 0 `FAIL`, 0 `DEFERRED` | [M2 test cases](./phases/M2/M2_TEST_CASES.md); offline, synthetic live and full private nine-file DAG/replay evidence pass |
| Quality | `PASS` | 337 offline tests pass + 8 expected opt-in live skips; Ruff, strict mypy, policy/locks pass; final Airflow image pip/DagBag smoke pass |
| Status validator | `PASS` — 0 errors, 0 warnings | M0, M1 and M2 complete; M2 synchronized at 18 done/25 pass with live exit evidence |

## Blocker và rủi ro

- Raw Olist hiện nằm trong private R2 dưới immutable release prefix. Không public object, không cleanup/overwrite thủ công; retention 90 ngày vẫn áp dụng theo baseline.
- Olist license cho phép non-commercial portfolio use theo CC BY-NC-SA, nhưng review free text vẫn cần DLP/privacy gate trước OpenRouter/Chroma và không được public raw.
- Snowflake trial hết hạn `2026-09-03`; ưu tiên M3 vertical slice, giữ X-Small/60s/resource monitor.
- Product/seller insights từ review có multi-item ambiguity; M3 phải implement allocation/label policy, không nhân review rồi sum.
- Chroma adapter M1 vẫn là lazy/fake-tested boundary. Machine-readable quarantine chặn package/server 1.5.9 và mọi addition chưa được review; `IMP-M5-001` phải thay policy có chủ đích chỉ sau khi một patched release qua dependency/image audit và negative access smoke.

## Chi phí và tài nguyên

| Dịch vụ | Budget/gate hiện tại | Usage đã xác minh |
|---|---|---|
| OpenRouter | 5 USD/project; warning 0.50 USD/day | Không gọi trong phiên CI; 0 USD phát sinh từ code path project |
| Snowflake | ≤10 credits/month; X-Small, auto-suspend 60s | Nine Bronze tables contain 1,289,091 reconciled accepted rows; replay has zero duplicate committed effect and warehouse suspended |
| Cloudflare R2 | Standard; target ≤15 GB; private/lifecycle | 9 approved CSV (~126.19 MB), source manifest and immutable raw/quarantine artifacts retained privately; replay verified create-only objects |
| ChromaDB | ≤5 GB local | Typed/in-memory adapter tests only; chưa provision/index và 0 byte project data được ghi |

## Input cần từ chủ project

Không cần thêm credential hoặc secret cho việc đóng M2. Trước M3 live transformation,
chỉ cần owner xác nhận khi workflow nêu rõ một provider gate có thể phát sinh thêm
Snowflake usage; công việc contract/dbt offline có thể bắt đầu ngay.

## Việc tiếp theo

1. Initialize M3 phase artifacts and begin `IMP-M3-001…003` for processing ledger, grain contracts and dbt Bronze sources.
2. Keep `REVIEWLENS_ENABLE_OLIST_PIPELINE=0` outside an intentional private replay.
3. Build and test Silver/Gold candidates before any atomic release activation.
4. Re-audit Chroma tại `IMP-M5-001`; không bypass blocked policy để provision sớm.

## Tài liệu nguồn

- [PRD v2](./PRD.md)
- [Implementation plan v2](./IMPLEMENTATION_PLAN.md)
- [Dataset attribution](./DATA_ATTRIBUTION.md)
- [Olist source manifest](./data/OLIST_SOURCE_MANIFEST.md)
- [ADR-008 — Olist primary dataset](./ADR/ADR-008-olist-primary-dataset.md)
- [ADR-009 — Bronze decimal projection](./ADR/ADR-009-bronze-decimal-projection.md)
- [ADR-010 — duplicate observability semantics](./ADR/ADR-010-duplicate-observability-semantics.md)
- [M0 decision register](./phases/M0/M0_DECISION_REGISTER.md)
- [M2 overview](./phases/M2/README.md)
- [M2 checklist](./phases/M2/M2_CHECKLIST.md)
- [M2 test cases](./phases/M2/M2_TEST_CASES.md)
- [RAG recommendation](./reviewlens_rag_recommendation.md)
- [Credential rotation runbook](./runbooks/M1_CREDENTIAL_ROTATION.md)
- [Foundation operations runbook](./runbooks/M1_FOUNDATION_OPERATIONS.md)
- [M2 ingestion operations runbook](./runbooks/M2_INGESTION_OPERATIONS.md)
- [Architecture diagram](./images/plan.png)
