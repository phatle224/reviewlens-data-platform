# ReviewLens Project Status

> Dashboard trạng thái ngắn gọn; checklist/test cases của phase là evidence chi tiết.

## Tổng quan

| Thuộc tính | Giá trị |
|---|---|
| Trạng thái tổng thể | `ON_TRACK` |
| Phase hiện tại | `M2` — Olist ingestion, R2 and immutable Bronze |
| Trạng thái phase hiện tại | `IN_PROGRESS` — 8/18 work items, 17/25 phase tests pass |
| Phase gần nhất hoàn tất | `M1` — foundation, service identities and live rotation gate |
| Cập nhật lần cuối | 2026-08-13 |
| Người thực hiện | Solo Developer |
| Active source | Olist Brazilian E-Commerce dataset — nine relational CSVs, CC BY-NC-SA 4.0 |
| Data policy hiện hành | Raw CSV/review/row-level/embedding artifacts outside Git; private R2/Snowflake after manifest/privacy gate; external AI only after DLP/minimization; public evidence synthetic/aggregate/redacted |
| Cloud topology | Snowflake Standard/AWS Singapore ↔ private R2 Standard/APAC via S3-compatible HTTPS stage |

## Tiến độ theo phase

| Phase | Trạng thái | Tóm tắt | Evidence |
|---|---|---|---|
| M0 | `COMPLETE` | Olist product/data/license/security/architecture baseline | [Checklist](./phases/M0/M0_CHECKLIST.md) · [Tests](./phases/M0/M0_TEST_CASES.md) |
| M1 | `COMPLETE` | Config, identities, provider/dbt/Airflow boundaries, audit/logging, authenticated app shell and fail-closed CI/live rotation gates | [Overview](./phases/M1/README.md) · [Checklist](./phases/M1/M1_CHECKLIST.md) · [Tests](./phases/M1/M1_TEST_CASES.md) |
| M2 | `IN_PROGRESS` | Source discovery, IDs/parser, typed validation, record replay hash and fail-closed upload preflight complete | [Overview](./phases/M2/README.md) · [Checklist](./phases/M2/M2_CHECKLIST.md) · [Tests](./phases/M2/M2_TEST_CASES.md) |
| M3 | `NOT_STARTED` | Conformed Silver, Gold and atomic release | [Plan](./IMPLEMENTATION_PLAN.md) |
| M4 | `NOT_STARTED` | DLP-approved review enrichment | [Plan](./IMPLEMENTATION_PLAN.md) |
| M5 | `NOT_STARTED` | Embeddings, ChromaDB and grounded RAG | [Plan](./IMPLEMENTATION_PLAN.md) |
| M6 | `NOT_STARTED` | Guarded Text-to-SQL | [Plan](./IMPLEMENTATION_PLAN.md) |
| M7 | `NOT_STARTED` | Streamlit analytics and integrated consumption | [Plan](./IMPLEMENTATION_PLAN.md) |
| M8 | `NOT_STARTED` | Orchestration, hardening and portfolio evidence | [Plan](./IMPLEMENTATION_PLAN.md) |

Milestone completion: **2/9**. Đây là số gate đã đóng, không phải phần trăm effort.

## Kết quả phiên gần nhất

- Hoàn tất `IMP-M2-006…008`: versioned typed validation/file reconciliation, canonical typed record hash với explicit replay/duplicate classification và fail-closed real-upload preflight.
- Chín synthetic files pass; required/type/range/enum/format/timestamp, declared count và unique/occurrence identity semantics có stable row-safe errors.
- Preflight chỉ cấp deterministic authorization khi Olist mode, private R2, exact approved snapshot, CC BY-NC-SA attribution/notices và privacy/DLP evidence cùng pass; năm failure variants đều deny.
- Focused ingestion suite 83 pass. Full offline gate 269 pass + 6 expected live skips, 90.13% branch-aware coverage; Ruff, mypy, lock, policy, artifact và status gates pass.
- Chỉ dùng synthetic fixtures; không đọc/upload Olist, không gọi R2/Snowflake/OpenRouter/Chroma và không phát sinh paid AI cost.

## Kiểm thử

| Phạm vi | Kết quả | Chi tiết |
|---|---|---|
| M0 | 18 `PASS`, 3 `DEFERRED`, 0 `FAIL` | [M0 test cases](./phases/M0/M0_TEST_CASES.md) |
| M1 | 41 `PASS`, 0 `PENDING`, 0 `FAIL`, 0 `DEFERRED` | [M1 test cases](./phases/M1/M1_TEST_CASES.md); offline 193 pass/6 live skip plus owner-approved live rotation 1 pass; Chroma quarantine + clean-path/container/Compose/artifact/metrics + CI policy/dependency/AppTest/logging/audit/Airflow/dbt/provider/R2/stage/RBAC/JWT evidence |
| M2 | 17 `PASS`, 8 `PENDING`, 0 `FAIL`, 0 `DEFERRED` | [M2 test cases](./phases/M2/M2_TEST_CASES.md); focused ingestion suite 83 pass |
| Quality | `PASS` | Ruff format/lint + Airflow 3 rules, mypy strict, dbt warnings-as-errors, 90.13% branch-aware coverage, uv lock/artifact checks, repository scan và dependency audit with no known vulnerabilities |
| Status validator | `PASS` — 0 errors, 0 warnings | M0 complete; M1 complete; M2 synchronized at 8 done/17 pass |

## Blocker và rủi ro

- Synthetic file counts đã được đối chiếu bằng streaming validation; physical source→R2→Bronze reconciliation thật vẫn thuộc `IMP-M2-015`.
- Real Olist CSV vẫn chưa được đọc hoặc upload. Manifest/privacy preflight `IMP-M2-008` phải pass trước mọi real-data provider action.
- Olist license cho phép non-commercial portfolio use theo CC BY-NC-SA, nhưng review free text vẫn cần DLP/privacy gate trước OpenRouter/Chroma và không được public raw.
- Snowflake trial hết hạn `2026-09-03`; ưu tiên hoàn tất M1 và M2/M3 vertical slice, giữ X-Small/60s/resource monitor.
- Product/seller insights từ review có multi-item ambiguity; M3 phải implement allocation/label policy, không nhân review rồi sum.
- Chroma adapter M1 vẫn là lazy/fake-tested boundary. Machine-readable quarantine chặn package/server 1.5.9 và mọi addition chưa được review; `IMP-M5-001` phải thay policy có chủ đích chỉ sau khi một patched release qua dependency/image audit và negative access smoke.

## Chi phí và tài nguyên

| Dịch vụ | Budget/gate hiện tại | Usage đã xác minh |
|---|---|---|
| OpenRouter | 5 USD/project; warning 0.50 USD/day | Không gọi trong phiên CI; 0 USD phát sinh từ code path project |
| Snowflake | ≤10 credits/month; X-Small, auto-suspend 60s | Không gọi trong bundle M2 hiện tại; không load/query Olist |
| Cloudflare R2 | Standard; target ≤15 GB; private/lifecycle | Không gọi trong bundle M2 hiện tại; không upload Olist |
| ChromaDB | ≤5 GB local | Typed/in-memory adapter tests only; chưa provision/index và 0 byte project data được ghi |

## Input cần từ chủ project

Không cần gửi credential/secret hoặc raw data để implement offline contract của
`IMP-M2-009`. Trước khi chạy upload Olist thật, chủ project cần xác nhận local
snapshot folder đã match metadata và chủ động cho phép live gate; chỉ cung cấp
đường dẫn local, không gửi CSV hoặc nội dung review qua chat.

## Việc tiếp theo

1. Implement immutable R2 source upload/replay/conflict/download-checksum contract (`IMP-M2-009`) bằng fake và synthetic live gate opt-in.
2. Chỉ upload Olist thật sau preflight thực tế và owner chủ động xác nhận local snapshot/live action.
3. Tiếp theo tạo typed raw/quarantine Parquet và audit state machine (`IMP-M2-010…012`).
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
- [Architecture diagram](./images/plan.png)
