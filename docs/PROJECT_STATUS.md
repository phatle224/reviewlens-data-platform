# ReviewLens Project Status

> Dashboard trạng thái ngắn gọn; checklist/test cases của phase là evidence chi tiết.

## Tổng quan

| Thuộc tính | Giá trị |
|---|---|
| Trạng thái tổng thể | `ON_TRACK` |
| Phase hiện tại | `M4` — DLP-approved review enrichment |
| Trạng thái phase hiện tại | `NOT_STARTED` — M3 exit gate closed; M4 artifacts chưa được khởi tạo |
| Phase gần nhất hoàn tất | `M3` — Conformed Silver, Gold and atomic release |
| Cập nhật lần cuối | 2026-08-20 |
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
| M3 | `COMPLETE` | Silver/DQ, conformed facts/dimensions, review allocation, marts, semantic views, Gold candidate target, private full-refresh/deterministic-replay equivalence, immutable releases, guarded activation and live two-release rollback are complete | [Overview](./phases/M3/README.md) · [Checklist](./phases/M3/M3_CHECKLIST.md) · [Tests](./phases/M3/M3_TEST_CASES.md) |
| M4 | `NOT_STARTED` | DLP-approved review enrichment | [Plan](./IMPLEMENTATION_PLAN.md) |
| M5 | `NOT_STARTED` | Embeddings, ChromaDB and grounded RAG | [Plan](./IMPLEMENTATION_PLAN.md) |
| M6 | `NOT_STARTED` | Guarded Text-to-SQL | [Plan](./IMPLEMENTATION_PLAN.md) |
| M7 | `NOT_STARTED` | Streamlit analytics and integrated consumption | [Plan](./IMPLEMENTATION_PLAN.md) |
| M8 | `NOT_STARTED` | Orchestration, hardening and portfolio evidence | [Plan](./IMPLEMENTATION_PLAN.md) |

Milestone completion: **4/9**. Đây là số gate đã đóng, không phải phần trăm effort.

## Kết quả phiên gần nhất

- Owner-approved M3 preflight đã áp dụng additive migrations `004`, `006`, `007`; Snowflake xác nhận processing/release ledgers và hai owner procedures tồn tại. Denied-smoke cho release ID không tồn tại trả `RELEASE_DENIED`, active pointer vẫn uninitialized/version 0, warehouse được suspend.
- Sửa ba lỗi tương thích phát hiện bằng live gate: splitter giữ nguyên `$$` procedure body, Snowflake Scripting dùng parenthesized `IF` + bind `:P_...`, và procedure invocation dùng `USAGE` grant thay vì `EXECUTE`.
- Live Bronze contract pass 138/138. Macro grain hiện quote canonical uppercase Snowflake identifiers; freshness được đổi thành immutable-snapshot 30/90 ngày sau khi aggregate-only preflight xác nhận private snapshot cũ hơn SLA streaming.
- DWH-006/`IMP-M3-020` đã pass live ngày 2026-08-19: executor private dùng đúng 9 Bronze inputs, hai dbt identity/target, 10 object-level Silver→Gold grants và 28 aggregate fingerprints trên mỗi observation. Full refresh và deterministic replay của cùng candidate pair trả `equivalent=true`; pointer vẫn `__UNINITIALIZED__`/v0 và warehouse được suspend. Hai lỗi SQL live (SCD quoted-case, bridge `PRODUCT_KEY` ambiguous) đã được sửa cùng regression tests; một Gold failure lifecycle lịch sử vẫn được audit, không ảnh hưởng candidate pair cuối cùng.
- `IMP-M3-018` registration gate pass live ngày 2026-08-20: migration `008` đã apply; executor xác minh exact 10 Silver + 18 Gold latest `TEST_PASSED` refs và idempotently ghi/re-read một immutable definition, 28 refs và `CREATED` event. Aggregate-only post-check trả một ready definition; active pointer vẫn uninitialized/v0 và transition event count bằng 0. Warehouse được suspend; không activation/rollback.
- Owner-confirmed initial activation pass live ngày 2026-08-20: executor gọi đúng một owner procedure qua `CALL` với CAS v0, đọc lại pointer v1 và aggregate post-check xác nhận đúng một `ACTIVATED` event; warehouse `SUSPENDED`. Hai runtime gaps đã được sửa: Snowflake procedure phải dùng `CALL` (không phải `SELECT`) và migration `008` re-grant exact `USAGE` sau `CREATE OR REPLACE PROCEDURE`. Không có direct `UPDATE`, retry CAS version mới hay public/raw output.
- Owner-approved rollback proof pass live ngày 2026-08-20: revision lineage private tạo một candidate pair thứ hai nhưng giữ nguyên Olist inputs, batch, dbt selectors và semantic contract. Full-refresh/replay trả `equivalent=true`; release 2 activate v1→v2 và guarded rollback về release 1 v2→v3. Aggregate check: 2 definitions, 56 refs, 2 `CREATED`, 2 `ACTIVATED`, 1 `ROLLED_BACK`, 2 ready releases; warehouse `SUSPENDED`. M3 exit gate đóng.
- dbt profile vẫn là một local target nhưng Gold command nay phải override tạm thời sang `GOLD_BUILDER_ROLE`; planner chỉ tạo đúng 10 object-level Silver `SELECT` grants cho Gold, không thêm schema/future privilege. Safe credential-presence check cho transform/Gold key path pass; không đọc hay in secret, không gọi provider.
- Gate local sau rollback-proof pass: Ruff format/lint cho `src`/`tests`, strict mypy, dbt parse `--warn-error`, 492 offline tests (8 opt-in live skips, 85.94% coverage), policy/artifact và status validator đều pass.

## Kiểm thử

| Phạm vi | Kết quả | Chi tiết |
|---|---|---|
| M0 | 18 `PASS`, 3 `DEFERRED`, 0 `FAIL` | [M0 test cases](./phases/M0/M0_TEST_CASES.md) |
| M1 | 41 `PASS`, 0 `PENDING`, 0 `FAIL`, 0 `DEFERRED` | [M1 test cases](./phases/M1/M1_TEST_CASES.md); offline 193 pass/6 live skip plus owner-approved live rotation 1 pass; Chroma quarantine + clean-path/container/Compose/artifact/metrics + CI policy/dependency/AppTest/logging/audit/Airflow/dbt/provider/R2/stage/RBAC/JWT evidence |
| M2 | 25 `PASS`, 0 `PENDING`, 0 `FAIL`, 0 `DEFERRED` | [M2 test cases](./phases/M2/M2_TEST_CASES.md); offline, synthetic live and full private nine-file DAG/replay evidence pass |
| M3 | 31 `PASS`, 0 `PENDING`, 0 `FAIL`, 0 `DEFERRED` | [M3 test cases](./phases/M3/M3_TEST_CASES.md); private same-candidate-pair full/replay, guarded activation and real two-release rollback pass live |
| Quality | `PARTIAL` | Ruff, strict mypy, dbt parse, 492 offline tests (8 opt-in live skips, 85.94% coverage), artifact lock and repository policy pass. Dependency audit flags 12 known CVEs in Airflow 3.3.0/sqlparse 0.5.5; remediation is tracked before M8/container release. |
| Status validator | `PASS` — 0 errors, 0 warnings | M0–M3 complete; M3 synchronized at 20/20 done and 31/31 pass |

## Blocker và rủi ro

- Raw Olist hiện nằm trong private R2 dưới immutable release prefix. Không public object, không cleanup/overwrite thủ công; retention 90 ngày vẫn áp dụng theo baseline.
- Olist license cho phép non-commercial portfolio use theo CC BY-NC-SA, nhưng review free text vẫn cần DLP/privacy gate trước OpenRouter/Chroma và không được public raw.
- Snowflake trial hết hạn `2026-09-03`; ưu tiên M3 vertical slice, giữ X-Small/60s/resource monitor.
- Local dependency audit ngày 2026-08-20 báo 12 known CVEs: Airflow 3.3.0 có fix 3.3.1 và sqlparse 0.5.5 có fix 0.6.0. Chưa update trong M3 để tránh một Docker/runtime migration ngoài scope; phải re-audit/upgrade có kiểm soát trước M8 portfolio release.
- Product/seller review insights remain allocations, not item-level evidence; semantic views expose the policy label and mark order counts as nonadditive.
- Gold candidate build must read a tested Silver candidate and write a different candidate namespace. Owner-approved preflight/migrations are complete, but a candidate build must first persist its processing lineage and pass DQ/reconciliation before any release definition or pointer action.
- M3 release definition/CAS, request pinning and guarded two-release rollback have complete live evidence. `008` is applied/re-applied idempotently; active pointer is v3 on the restored first release. M4 DLP/minimization gate is the next data/privacy boundary.
- Chroma adapter M1 vẫn là lazy/fake-tested boundary. Machine-readable quarantine chặn package/server 1.5.9 và mọi addition chưa được review; `IMP-M5-001` phải thay policy có chủ đích chỉ sau khi một patched release qua dependency/image audit và negative access smoke.

## Chi phí và tài nguyên

| Dịch vụ | Budget/gate hiện tại | Usage đã xác minh |
|---|---|---|
| OpenRouter | 5 USD/project; warning 0.50 USD/day | Không gọi trong phiên CI; 0 USD phát sinh từ code path project |
| Snowflake | ≤10 credits/month; X-Small, auto-suspend 60s | Nine Bronze tables contain 1,289,091 reconciled accepted rows; M3 full/replay, two private registrations, guarded activation and rollback passed; pointer is v3 and warehouse is suspended |
| Cloudflare R2 | Standard; target ≤15 GB; private/lifecycle | 9 approved CSV (~126.19 MB), source manifest and immutable raw/quarantine artifacts retained privately; replay verified create-only objects |
| ChromaDB | ≤5 GB local | Typed/in-memory adapter tests only; chưa provision/index và 0 byte project data được ghi |

## Input cần từ chủ project

Không cần thêm credential hoặc secret cho M4 offline baseline. M3 rollback proof
đã pass. Trước bất kỳ OpenRouter call nào trong M4, cần thực hiện DLP/minimization
projection theo M0 và chỉ dùng review text private, không public.

## Việc tiếp theo

1. Khởi tạo M4 artifacts và implement `IMP-M4-001…003`: enrichment schema, ledgers và DLP/minimization projection offline.
2. Keep review text private and `ai_eligible=false`; chỉ M4 mới có thể tạo external projection sau DLP approval.
3. Re-audit Chroma tại `IMP-M5-001`; không bypass blocked policy để provision sớm; trước M8, xử lý dependency audit Airflow/sqlparse rồi rebuild một image mới có kiểm soát.

## Dự báo hoàn thành (solo portfolio)

| Mục tiêu | Ước tính từ 2026-08-20 | Điều kiện |
|---|---:|---|
| Lean local demo có video/screenshots | 6–8 tuần (đầu–giữa 10/2026) | Đóng M3 bằng lựa chọn initial-release hợp lý; M4–M7 chỉ dùng slice tối thiểu, review text vẫn private và AI call trong budget |
| Portfolio đầy đủ theo M0–M8 | 10–14 tuần tập trung, tương đương khoảng 3–4 tháng lịch | Duy trì ~12–15 giờ/tuần, không phát sinh chờ provider/trial, hoàn tất evaluation, dashboard và hardening M8 |

Đây là forecast, không phải cam kết thời hạn. Hiện đã đóng 3/9 milestone;
M3 gần xong nhưng M4–M8 chứa phần lớn công việc AI, RAG, Text-to-SQL, ứng dụng và
portfolio evidence. Việc cần quyết định ở M3 có thể thay đổi forecast khoảng một
đến hai buổi làm việc, không làm thay đổi kiến trúc nền tảng.

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
- [ADR-014 — atomic release CAS](./ADR/ADR-014-atomic-release-cas.md)
- [ADR-015 — M3 rollback-proof release revision](./ADR/ADR-015-m3-rollback-proof-release.md)
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
- [M3 release operations runbook](./runbooks/M3_RELEASE_OPERATIONS.md)
- [Architecture diagram](./images/plan.png)
