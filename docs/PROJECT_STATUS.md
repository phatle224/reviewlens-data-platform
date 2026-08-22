# ReviewLens Project Status

> Dashboard trạng thái ngắn gọn; checklist/test cases của phase là evidence chi tiết.

## Tổng quan

| Thuộc tính | Giá trị |
|---|---|
| Trạng thái tổng thể | `ON_TRACK` |
| Phase hiện tại | `M4` — DLP-approved review enrichment |
| Trạng thái phase hiện tại | `IN_PROGRESS` — 12/15 M4 items complete, 3 partial; structured provider smoke remains opt-in |
| Phase gần nhất hoàn tất | `M3` — Conformed Silver, Gold and atomic release |
| Cập nhật lần cuối | 2026-08-23 |
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
| M4 | `IN_PROGRESS` | DLP through retry/quarantine, durable cost guard, validated commit/coverage, evaluator, quality-gate, aggregate observability and recovery-runbook contracts complete; provider, real golden and release wiring remain gated | [Overview](./phases/M4/README.md) · [Checklist](./phases/M4/M4_CHECKLIST.md) · [Tests](./phases/M4/M4_TEST_CASES.md) |
| M5 | `NOT_STARTED` | Embeddings, ChromaDB and grounded RAG | [Plan](./IMPLEMENTATION_PLAN.md) |
| M6 | `NOT_STARTED` | Guarded Text-to-SQL | [Plan](./IMPLEMENTATION_PLAN.md) |
| M7 | `NOT_STARTED` | Streamlit analytics and integrated consumption | [Plan](./IMPLEMENTATION_PLAN.md) |
| M8 | `NOT_STARTED` | Orchestration, hardening and portfolio evidence | [Plan](./IMPLEMENTATION_PLAN.md) |

Milestone completion: **4/9**. Đây là số gate đã đóng, không phải phần trăm effort.

## Kết quả phiên gần nhất

- M4 `IMP-M4-012` progressed offline on 2026-08-23: the completed 200-label
  private set was revalidated as a 40-item blind holdout. A new local evaluator
  accepts only exact holdout predictions, schema-validates them and writes an
  immutable aggregate-only report; it rejects train/missing/duplicate IDs and
  made no provider or managed-service request. Real metrics remain pending the
  separately authorized bounded pilot.
- M4 `IMP-M4-012` documentation progressed offline on 2026-08-22: the private
  golden-set annotation runbook was rewritten as a beginner-friendly Windows
  procedure with exact files, permitted fields, taxonomy, examples, progress
  check, validation command and error recovery. It makes no data/provider call
  and does not change the still-open human-review gate.
- M4 `IMP-M4-012` progressed offline on 2026-08-22: the owner-authorized local
  heuristic generated 200 `machine_assisted` suggestions from score/delivery
  metadata only. It made no provider call and is explicitly rejected by the
  human-golden loader; every suggestion still needs private human review before
  `approved` status. It therefore does not close the golden gate.
- M4 `IMP-M4-012` progressed offline on 2026-08-22: a private-only CLI now
  generated a deterministic 200-row Olist annotation queue/template under
  ignored `private_evaluation/m4_enrichment_v1/`. It exposes no natural IDs in
  its label shape and prints only aggregate generation output. The pack is still
  `pending_human_review`, so it does not close the golden evaluation or permit a
  provider call; no managed-service request occurred.
- M4 `IMP-M4-015` completed offline on 2026-08-22: solo-operator recovery
  runbook and a synthetic tabletop contract now cover pause/triage, bounded
  retryable resume, versioned model/prompt/schema/taxonomy change and a
  fail-closed purge request. It explicitly preserves base facts, immutable raw,
  active/rollback releases and audit lineage, and provides no direct-delete
  command. This is not evidence of a live provider, golden evaluation or release
  transition; no managed-service request occurred.
- M4 `IMP-M4-014` completed offline on 2026-08-22: terminal invocation telemetry
  now emits only aggregate tokens, exact USD cost, total/p95 latency, sanitized
  error-code counts and base/eligible/valid/missing AI coverage. It rejects a
  mismatched enrichment version, duplicate opaque invocation ID, coverage drift
  and budget-ledger drift before a dashboard snapshot exists. The reproducible
  snapshot keeps opaque references internal and exposes no review, prompt,
  provider payload, natural identifier or row-level result. No managed-service
  request occurred.
- M4 `IMP-M4-013` progressed offline on 2026-08-22: a candidate can publish
  only if its exact enrichment version has an aggregate report that clears the
  initial M0 sentiment/aspect/topic/schema thresholds. Low, missing or
  mismatched reports block before the publish callback, with no Snowflake
  pointer operation. It remains partial pending a real private report and
  deliberate integration with the guarded release runtime.
- M4 `IMP-M4-012` progressed offline on 2026-08-22: deterministic splitting
  stratifies private structured labels and reserves a blind ≥20% holdout; the
  evaluator reports only aggregate F1/schema metrics and rejects train or
  incomplete holdout predictions. A private 200-row annotation pack has now
  been generated from the local archive under ignored `private_evaluation/`,
  but every row remains `pending_human_review`; it is therefore still partial.
  No managed-service call occurred.
- M4 `IMP-M4-012` golden set annotation complete on 2026-08-22: 200/200 private Olist review items human-annotated and approved in `private_evaluation/m4_enrichment_v1/labels.jsonl`. Validation passed with split seed `m4-eval-holdout-v1` (40 blind holdout items, status `ready_for_private_predictions`). Focused pytest suite passes 9/9 tests offline. No live model or network call occurred.
- M4 `IMP-M4-011` complete offline on 2026-08-22: only a hash-matched,
  semantically validated result linked to a successful result-map can enter the
  private current-result contract. Exact replay is idempotent, changed approved
  input replaces atomically, and aggregate coverage preserves all base-review
  counts when AI is missing or ineligible. Static migration `010` is fake-tested
  only and remains unapplied; no provider or managed-service request occurred.
- M4 `IMP-M4-010` complete offline on 2026-08-22: catalog-pinned token-price
  estimates now reserve aggregate-only cost before every synthetic live-smoke
  provider dispatch, warn at 0.50 USD/day and stop before the 5 USD project cap.
  The ignored local ledger persists only USD/date/opaque reservation metadata;
  it contains no review, prompt, response or provider payload. Focused tests
  pass and the smoke remains explicitly opt-in; no paid call was made.
- M4 `IMP-M4-007…009` complete/partial on 2026-08-21: structured-enrichment
  requests use strict JSON Schema, pinned model and data-collection deny/no
  fallback; synthetic semantic validation, one repair, rate limit, transient
  resume/max-attempt and permanent-error quarantine tests pass. A single
  synthetic-only live smoke (`max_tokens=200`) exists but is not executed without
  owner opt-in due to token cost. No Olist review, API request, R2, Snowflake or
  Chroma operation occurred in this bundle.
- M4 `IMP-M4-004…006` complete on 2026-08-21: one public metadata-only catalog
  request confirms the pinned `google/gemini-2.5-flash-lite` slug, 1,048,576
  context, structured-output support and prompt/completion price 0.0000001 /
  0.0000004 USD per token. Private selector dispatches only new/changed approved
  hashes and reuses exact prior results; Portuguese controls isolate synthetic
  injection evidence in explicit delimiters. Focused tests have 26 passes. No
  API key, completion, review, R2, Snowflake or Chroma operation occurred.
- M4 `IMP-M4-001…003` complete offline on 2026-08-21: ADR-016 freezes the v1
  structured enrichment schema/taxonomy/version key; `009` adds three
  secret-free, append-only AI enrichment ledger contracts with exact
  `AI_ENRICH_ROLE` grants; a private DLP projection redacts email/URL/phone/CPF
  patterns and quarantines empty, oversized, direct-ID or secret-like text.
  Focused synthetic suite has 19 passing tests. No provider, warehouse, R2 or
  Chroma call was made; migration `009` has not been applied live.
- Owner-approved M3 preflight đã áp dụng additive migrations `004`, `006`, `007`; Snowflake xác nhận processing/release ledgers và hai owner procedures tồn tại. Denied-smoke cho release ID không tồn tại trả `RELEASE_DENIED`, active pointer vẫn uninitialized/version 0, warehouse được suspend.
- Sửa ba lỗi tương thích phát hiện bằng live gate: splitter giữ nguyên `$$` procedure body, Snowflake Scripting dùng parenthesized `IF` + bind `:P_...`, và procedure invocation dùng `USAGE` grant thay vì `EXECUTE`.
- Live Bronze contract pass 138/138. Macro grain hiện quote canonical uppercase Snowflake identifiers; freshness được đổi thành immutable-snapshot 30/90 ngày sau khi aggregate-only preflight xác nhận private snapshot cũ hơn SLA streaming.
- DWH-006/`IMP-M3-020` đã pass live ngày 2026-08-19: executor private dùng đúng 9 Bronze inputs, hai dbt identity/target, 10 object-level Silver→Gold grants và 28 aggregate fingerprints trên mỗi observation. Full refresh và deterministic replay của cùng candidate pair trả `equivalent=true`; pointer vẫn `__UNINITIALIZED__`/v0 và warehouse được suspend. Hai lỗi SQL live (SCD quoted-case, bridge `PRODUCT_KEY` ambiguous) đã được sửa cùng regression tests; một Gold failure lifecycle lịch sử vẫn được audit, không ảnh hưởng candidate pair cuối cùng.
- `IMP-M3-018` registration gate pass live ngày 2026-08-20: migration `008` đã apply; executor xác minh exact 10 Silver + 18 Gold latest `TEST_PASSED` refs và idempotently ghi/re-read một immutable definition, 28 refs và `CREATED` event. Aggregate-only post-check trả một ready definition; active pointer vẫn uninitialized/v0 và transition event count bằng 0. Warehouse được suspend; không activation/rollback.
- Owner-confirmed initial activation pass live ngày 2026-08-20: executor gọi đúng một owner procedure qua `CALL` với CAS v0, đọc lại pointer v1 và aggregate post-check xác nhận đúng một `ACTIVATED` event; warehouse `SUSPENDED`. Hai runtime gaps đã được sửa: Snowflake procedure phải dùng `CALL` (không phải `SELECT`) và migration `008` re-grant exact `USAGE` sau `CREATE OR REPLACE PROCEDURE`. Không có direct `UPDATE`, retry CAS version mới hay public/raw output.
- Owner-approved rollback proof pass live ngày 2026-08-20: revision lineage private tạo một candidate pair thứ hai nhưng giữ nguyên Olist inputs, batch, dbt selectors và semantic contract. Full-refresh/replay trả `equivalent=true`; release 2 activate v1→v2 và guarded rollback về release 1 v2→v3. Aggregate check: 2 definitions, 56 refs, 2 `CREATED`, 2 `ACTIVATED`, 1 `ROLLED_BACK`, 2 ready releases; warehouse `SUSPENDED`. M3 exit gate đóng.
- dbt profile vẫn là một local target nhưng Gold command nay phải override tạm thời sang `GOLD_BUILDER_ROLE`; planner chỉ tạo đúng 10 object-level Silver `SELECT` grants cho Gold, không thêm schema/future privilege. Safe credential-presence check cho transform/Gold key path pass; không đọc hay in secret, không gọi provider.
- Gate local sau M4-012 machine-assisted suggestion tooling: Ruff format/lint cho `src`/`tests`, strict mypy, dbt parse `--warn-error`, 554 offline tests (9 opt-in live skips, 85.52% coverage), artifact lock, repository policy và status validator pass. Full suite dùng workspace-local pytest temp do Windows user-temp bị access-denied.

## Kiểm thử

| Phạm vi | Kết quả | Chi tiết |
|---|---|---|
| M0 | 18 `PASS`, 3 `DEFERRED`, 0 `FAIL` | [M0 test cases](./phases/M0/M0_TEST_CASES.md) |
| M1 | 41 `PASS`, 0 `PENDING`, 0 `FAIL`, 0 `DEFERRED` | [M1 test cases](./phases/M1/M1_TEST_CASES.md); offline 193 pass/6 live skip plus owner-approved live rotation 1 pass; Chroma quarantine + clean-path/container/Compose/artifact/metrics + CI policy/dependency/AppTest/logging/audit/Airflow/dbt/provider/R2/stage/RBAC/JWT evidence |
| M2 | 25 `PASS`, 0 `PENDING`, 0 `FAIL`, 0 `DEFERRED` | [M2 test cases](./phases/M2/M2_TEST_CASES.md); offline, synthetic live and full private nine-file DAG/replay evidence pass |
| M3 | 31 `PASS`, 0 `PENDING`, 0 `FAIL`, 0 `DEFERRED` | [M3 test cases](./phases/M3/M3_TEST_CASES.md); private same-candidate-pair full/replay, guarded activation and real two-release rollback pass live |
| M4 | 18 `PASS`, 2 `PENDING`, 0 `FAIL`, 0 `DEFERRED` | [M4 test cases](./phases/M4/M4_TEST_CASES.md); provider smoke and real private golden evaluation remain pending |
| Quality | `PARTIAL` | Ruff, strict mypy, dbt parse, 554 offline tests (9 opt-in live skips, 85.52% coverage), artifact lock, repository policy and status validator pass. Dependency audit flags 12 known CVEs in Airflow 3.3.0/sqlparse 0.5.5; remediation is tracked before M8/container release. |
| Status validator | `PASS` — 0 errors, 0 warnings | M0–M3 complete; M3 synchronized at 20/20 done and 31/31 pass |

## Blocker và rủi ro

- Raw Olist hiện nằm trong private R2 dưới immutable release prefix. Không public object, không cleanup/overwrite thủ công; retention 90 ngày vẫn áp dụng theo baseline.
- Olist license cho phép non-commercial portfolio use theo CC BY-NC-SA, nhưng review free text vẫn cần DLP/privacy gate trước OpenRouter/Chroma và không được public raw.
- Snowflake trial hết hạn `2026-09-03`; ưu tiên M3 vertical slice, giữ X-Small/60s/resource monitor.
- Local dependency audit ngày 2026-08-20 báo 12 known CVEs: Airflow 3.3.0 có fix 3.3.1 và sqlparse 0.5.5 có fix 0.6.0. Chưa update trong M3 để tránh một Docker/runtime migration ngoài scope; phải re-audit/upgrade có kiểm soát trước M8 portfolio release.
- Product/seller review insights remain allocations, not item-level evidence; semantic views expose the policy label and mark order counts as nonadditive.
- Gold candidate build must read a tested Silver candidate and write a different candidate namespace. Owner-approved preflight/migrations are complete, but a candidate build must first persist its processing lineage and pass DQ/reconciliation before any release definition or pointer action.
- M3 release definition/CAS, request pinning and guarded two-release rollback have complete live evidence. `008` is applied/re-applied idempotently; active pointer is v3 on the restored first release. M4 now has DLP, catalog, selector, prompt, validation, retry, budget, private commit/coverage, evaluator and quality-gate controls, but no real review can be sent externally until a bounded pilot is explicitly authorized and a private human-reviewed golden set is available. The quality gate is not wired to the live release runtime yet.
- Chroma adapter M1 vẫn là lazy/fake-tested boundary. Machine-readable quarantine chặn package/server 1.5.9 và mọi addition chưa được review; `IMP-M5-001` phải thay policy có chủ đích chỉ sau khi một patched release qua dependency/image audit và negative access smoke.

## Chi phí và tài nguyên

| Dịch vụ | Budget/gate hiện tại | Usage đã xác minh |
|---|---|---|
| OpenRouter | 5 USD/project; warning 0.50 USD/day | Không gọi trong phiên CI; 0 USD phát sinh từ code path project |
| Snowflake | ≤10 credits/month; X-Small, auto-suspend 60s | Nine Bronze tables contain 1,289,091 reconciled accepted rows; M3 full/replay, two private registrations, guarded activation and rollback passed; pointer is v3 and warehouse is suspended |
| Cloudflare R2 | Standard; target ≤15 GB; private/lifecycle | 9 approved CSV (~126.19 MB), source manifest and immutable raw/quarantine artifacts retained privately; replay verified create-only objects |
| ChromaDB | ≤5 GB local | Typed/in-memory adapter tests only; chưa provision/index và 0 byte project data được ghi |

## Input cần từ chủ project

Không cần thêm credential hoặc secret. Human review đã hoàn tất 200/200 labels
và local validation đã tạo 40-item blind holdout. Để tiếp tục M4, cần owner
chấp thuận riêng một bounded OpenRouter pilot sau DLP/minimization projection;
pilot sẽ dùng review text private, không public, và chịu 5 USD project cap.

## Việc tiếp theo

1. Decide whether to authorize a bounded DLP-approved OpenRouter pilot for the 40 blind-holdout reviews; use the cost guard and keep outputs private.
2. Run the new local evaluator to create the aggregate-only golden report; do not include train IDs or public artifacts.
3. After a real private golden report exists, deliberately wire the M4 quality gate to the guarded release runtime; do not bypass the current no-pointer contract.
4. Re-audit Chroma at `IMP-M5-001`; do not bypass blocked policy to provision early; before M8, remediate Airflow/sqlparse dependency audit and rebuild one controlled image.

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
- [M4 AI enrichment operations runbook](./runbooks/M4_AI_ENRICHMENT_OPERATIONS.md)
- [M4 golden-set annotation runbook](./runbooks/M4_GOLDEN_SET_ANNOTATION.md)
- [Architecture diagram](./images/plan.png)
