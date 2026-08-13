# ReviewLens Project Status

> Dashboard trạng thái ngắn gọn; checklist/test cases của phase là evidence chi tiết.

## Tổng quan

| Thuộc tính | Giá trị |
|---|---|
| Trạng thái tổng thể | `ON_TRACK` |
| Phase hiện tại | `M2` — Olist ingestion, R2 and immutable Bronze |
| Trạng thái phase hiện tại | `IN_PROGRESS` — 18/18 work items, 25/25 phase tests pass; full private DAG exit run pending |
| Phase gần nhất hoàn tất | `M1` — foundation, service identities and live rotation gate |
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
| M2 | `IN_PROGRESS` | All 18 implementation items pass offline/container gates; owner-approved full nine-file private DAG run remains the exit evidence | [Overview](./phases/M2/README.md) · [Checklist](./phases/M2/M2_CHECKLIST.md) · [Tests](./phases/M2/M2_TEST_CASES.md) |
| M3 | `NOT_STARTED` | Conformed Silver, Gold and atomic release | [Plan](./IMPLEMENTATION_PLAN.md) |
| M4 | `NOT_STARTED` | DLP-approved review enrichment | [Plan](./IMPLEMENTATION_PLAN.md) |
| M5 | `NOT_STARTED` | Embeddings, ChromaDB and grounded RAG | [Plan](./IMPLEMENTATION_PLAN.md) |
| M6 | `NOT_STARTED` | Guarded Text-to-SQL | [Plan](./IMPLEMENTATION_PLAN.md) |
| M7 | `NOT_STARTED` | Streamlit analytics and integrated consumption | [Plan](./IMPLEMENTATION_PLAN.md) |
| M8 | `NOT_STARTED` | Orchestration, hardening and portfolio evidence | [Plan](./IMPLEMENTATION_PLAN.md) |

Milestone completion: **2/9**. Đây là số gate đã đóng, không phải phần trăm effort.

## Kết quả phiên gần nhất

- Hoàn tất `IMP-M2-016…018`: ba Airflow task runtime, typed metadata-only handoff, retry/replay safety, late/change/backfill/concurrent same-key scenarios và failure injection.
- Bổ sung bounded Prometheus ingestion metrics, atomic stable-code alert artifact và runbook cho private run, replay, quarantine, recovery, suspend/shutdown.
- Locked Airflow image build và container import smoke pass với đủ 11 DAG tasks; base-image `chardet` conflict đã được loại bỏ nên Snowflake dependency warning không còn.
- Full offline suite đạt 335 pass + 8 expected live skips, 86.33% branch-aware coverage và policy scan 0 findings. Không đọc/materialize Olist row từ `archive/`, không gọi R2/Snowflake/OpenRouter/Chroma.

## Kiểm thử

| Phạm vi | Kết quả | Chi tiết |
|---|---|---|
| M0 | 18 `PASS`, 3 `DEFERRED`, 0 `FAIL` | [M0 test cases](./phases/M0/M0_TEST_CASES.md) |
| M1 | 41 `PASS`, 0 `PENDING`, 0 `FAIL`, 0 `DEFERRED` | [M1 test cases](./phases/M1/M1_TEST_CASES.md); offline 193 pass/6 live skip plus owner-approved live rotation 1 pass; Chroma quarantine + clean-path/container/Compose/artifact/metrics + CI policy/dependency/AppTest/logging/audit/Airflow/dbt/provider/R2/stage/RBAC/JWT evidence |
| M2 | 25 `PASS`, 0 `PENDING`, 0 `FAIL`, 0 `DEFERRED` | [M2 test cases](./phases/M2/M2_TEST_CASES.md); implementation tests plus synthetic/live representative R2/Bronze/RBAC evidence pass; full real-data DAG exit run remains a phase-level gate |
| Quality | `PASS` | Ruff on project source + Airflow 3 rules, mypy strict, 86.33% branch-aware coverage, uv lock/artifact checks, repository scan and Airflow container smoke |
| Status validator | `PASS` — 0 errors, 0 warnings | M0 complete; M1 complete; M2 synchronized at 18 done/25 pass and intentionally remains in progress for its live exit gate |

## Blocker và rủi ro

- Full nine-file Olist materialization/load chưa được trigger trong bundle này. Code, scenario tests và container runtime đã pass, nhưng M2 chỉ đóng sau một owner-approved private DAG run chứng minh nine-dataset reconciliation/replay và warehouse suspend.
- Raw Olist hiện nằm trong private R2 dưới immutable release prefix. Không public object, không cleanup/overwrite thủ công; retention 90 ngày vẫn áp dụng theo baseline.
- Olist license cho phép non-commercial portfolio use theo CC BY-NC-SA, nhưng review free text vẫn cần DLP/privacy gate trước OpenRouter/Chroma và không được public raw.
- Snowflake trial hết hạn `2026-09-03`; ưu tiên hoàn tất M1 và M2/M3 vertical slice, giữ X-Small/60s/resource monitor.
- Product/seller insights từ review có multi-item ambiguity; M3 phải implement allocation/label policy, không nhân review rồi sum.
- Chroma adapter M1 vẫn là lazy/fake-tested boundary. Machine-readable quarantine chặn package/server 1.5.9 và mọi addition chưa được review; `IMP-M5-001` phải thay policy có chủ đích chỉ sau khi một patched release qua dependency/image audit và negative access smoke.

## Chi phí và tài nguyên

| Dịch vụ | Budget/gate hiện tại | Usage đã xác minh |
|---|---|---|
| OpenRouter | 5 USD/project; warning 0.50 USD/day | Không gọi trong phiên CI; 0 USD phát sinh từ code path project |
| Snowflake | ≤10 credits/month; X-Small, auto-suspend 60s | Synthetic migration/COPY/replay/RBAC smoke pass; test rows cleaned and warehouse suspended; chưa load Olist |
| Cloudflare R2 | Standard; target ≤15 GB; private/lifecycle | 9 approved CSV (~126.19 MB) + manifest retained; temporary synthetic Parquet object cleaned after live smoke |
| ChromaDB | ≤5 GB local | Typed/in-memory adapter tests only; chưa provision/index và 0 byte project data được ghi |

## Input cần từ chủ project

Không cần thêm credential hoặc secret. Để đóng M2, cần chủ project xác nhận cho
chạy full nine-file private DAG; thao tác này sẽ đọc `archive/`, dùng private R2 và
Snowflake X-Small. Nếu chưa muốn phát sinh cloud usage, có thể giữ M2 `IN_PROGRESS`.

## Việc tiếp theo

1. Owner-approved full nine-file private `olist_pipeline` run, capture metadata-only reconciliation evidence, replay once and verify warehouse suspend to close M2.
2. Initialize M3 phase artifacts and begin `IMP-M3-001…003` only after M2 exit evidence is recorded.
3. Keep `REVIEWLENS_ENABLE_OLIST_PIPELINE=0` outside the intentional run.
4. Re-audit Chroma tại `IMP-M5-001`; không bypass blocked policy để provision sớm.

## Tài liệu nguồn

- [PRD v2](./PRD.md)
- [Implementation plan v2](./IMPLEMENTATION_PLAN.md)
- [Dataset attribution](./DATA_ATTRIBUTION.md)
- [Olist source manifest](./data/OLIST_SOURCE_MANIFEST.md)
- [ADR-008 — Olist primary dataset](./ADR/ADR-008-olist-primary-dataset.md)
- [M0 decision register](./phases/M0/M0_DECISION_REGISTER.md)
- [M2 overview](./phases/M2/README.md)
- [M2 checklist](./phases/M2/M2_CHECKLIST.md)
- [M2 test cases](./phases/M2/M2_TEST_CASES.md)
- [RAG recommendation](./reviewlens_rag_recommendation.md)
- [Credential rotation runbook](./runbooks/M1_CREDENTIAL_ROTATION.md)
- [Foundation operations runbook](./runbooks/M1_FOUNDATION_OPERATIONS.md)
- [M2 ingestion operations runbook](./runbooks/M2_INGESTION_OPERATIONS.md)
- [Architecture diagram](./images/plan.png)
