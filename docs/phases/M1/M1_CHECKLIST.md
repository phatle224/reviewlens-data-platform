# M1 Checklist — Foundation, Single-local Configuration and Developer Platform

| Thuộc tính | Giá trị |
|---|---|
| Phase status | `IN_PROGRESS` |
| Completed | 19/20 work items |
| Partial | 1/20 work items |
| Blocked | 0/20 work items |
| Not started | 0/20 work items |
| Last updated | 2026-08-12 |

## Checklist theo implementation plan

| Work item | Status | Outcome cần đạt | Evidence / việc còn lại |
|---|---|---|---|
| IMP-M1-001 | `DONE` | Repo/package/lock/lint/type/test commands | `pyproject.toml`, `.python-version`, `uv.lock`; full `uv sync --locked --offline` và tool entry points pass |
| IMP-M1-002 | `DONE` | README, contribution, CODEOWNERS, PR/issue templates | `README.md`, `CONTRIBUTING.md`, `.github/CODEOWNERS`, PR + issue forms; repository contract tests pass |
| IMP-M1-003 | `DONE` | Một typed local config; `.env`/process-only secrets; không có staging/prod profiles | `config/config.toml`, `.env.example`, `src/reviewlens/config.py`; TC-M1-005…007 pass |
| IMP-M1-004 | `DONE` | Deterministic nine-CSV relational Olist fixture generator/pack | `src/reviewlens/synthetic/generator.py`; exact headers, FK integrity and determinism tests pass |
| IMP-M1-005 | `DONE` | Private R2 config, scoped token/lifecycle/public deny | Bucket-scoped live round trip, account-list denial, anonymous denial và cleanup pass; owner xác nhận lifecycle rule đã apply/enabled ngày 2026-08-05 |
| IMP-M1-006 | `DONE` | Snowflake foundation, monitor và R2 external stage | Secret-free idempotent DDL + in-memory stage DDL using dedicated `R2_STAGE_*` read-only identity; XSMALL/60s/10-credit monitor; live ingest-upload → stage `LIST`/`COPY INTO`/reconcile pass và warehouse cleanup suspend |
| IMP-M1-007 | `DONE` | Least-privilege Snowflake/service roles | 9-role hierarchy dưới `SYSADMIN`, isolated `REVIEWLENS_SQL_WH`, container/exact-object grant boundary; static matrix và live 8-role positive/negative suite pass với secondary roles disabled |
| IMP-M1-008 | `PARTIAL` | Credential boundaries và rotation skeleton | All runtime credentials ready; 8 named keys active, fingerprint/user/role/warehouse/database exact và live JWT auth pass; R2 ingest write/stage read-only live boundary pass. Isolated read-only canary harness, exact owner opt-in, old/new key auth checks và guaranteed cleanup đã pass offline; còn owner-approved live smoke để đóng item |
| IMP-M1-009 | `DONE` | Snowflake-only dbt scaffold | `dbt/` project/profile, nine exact Bronze sources, contracted metadata registry, custom generic test macro and selector; dbt 1.12 parse + no-introspect compile pass with warnings-as-errors and synthetic placeholder credentials; no warehouse connection or DuckDB/multi-env/password path |
| IMP-M1-010 | `DONE` | Airflow 3 DAG scaffold không có parse side effect | Airflow 3 public SDK `olist_pipeline` với 11-task stable graph, manual schedule, fail-closed M1 guards, per-task retry/timeout/one-slot pool và versioned pool manifest; isolated real-DAG import + graph/policy/no-network/no-dotenv contract tests pass trên Windows mà không khởi động service |
| IMP-M1-011 | `DONE` | Provider adapters + fakes | R2/Snowflake/OpenRouter/Chroma/audit/clock typed boundaries và deterministic fakes pass; external AI chỉ nhận typed synthetic/DLP-approved text, Chroma chỉ giữ vector/reference metadata trỏ `AI.RAG_DOCUMENT`, provider errors được sanitize; không có paid/live AI call |
| IMP-M1-012 | `DONE` | Authenticated Streamlit shell + health/error state | `src/reviewlens/app/`: canonical-config launcher pins loopback/headless/CORS/XSRF/error-detail flags; masked token gate uses fixed-length digest comparison, stores no candidate and supports sign-out; boolean-only `ready/degraded/unavailable` states make no provider call; 16 AppTest/unit/security tests and TC-M1-021 pass |
| IMP-M1-013 | `DONE` | Audit schema up/down/compatibility migrations | DDL-only `004_audit_ledgers.sql` creates six versioned ingestion/file/process/release/pointer/AI objects plus constant compatibility view; exact append/read grants deny event mutation and pointer writes; local-only down block requires two session guards before any DROP; 8 offline schema/idempotency/privacy/RBAC/rollback tests pass without warehouse/provider access |
| IMP-M1-014 | `DONE` | Structured logging, correlation và redaction | `src/reviewlens/observability/logging.py`: JSONL stable events, context-local trace/source/batch/run/release IDs, fail-closed exception handling và recursive redaction cho secret/PII/URL/payment/restricted review text kể cả unsafe metadata keys; 11 focused tests và TC-M1-011 pass |
| IMP-M1-015 | `DONE` | CI lint/type/unit/contracts/dbt/security/container gates | Least-privilege GitHub Actions workflow chạy locked sync, Ruff/Airflow rules, mypy, pytest coverage, dbt offline parse/compile, repository policy, dependency audit, status validator và SHA-pinned Trivy image scans; reviewed-container policy thay pre-container rejection |
| IMP-M1-016 | `DONE` | Non-root Docker images/entrypoints | Digest-pinned app/Airflow builds pass; image metadata và live `id -u` xác nhận `10001:10001`/`50000:0`; app `uv pip check` và Airflow `pip check` sạch; CI build/non-root/critical-CVE gates đã version |
| IMP-M1-017 | `DONE` | Local Compose/deploy skeleton + immutable artifact tags + Chroma security quarantine | App/metrics/Airflow Compose build/deploy/health và deterministic artifact tag pass; Airflow không nhận credential env. `deploy/chroma-security-policy.json` cùng repository gate chặn Chroma service/dependency/lock entry trong khi GHSA-f4j7-r4q5-qw2c chưa có bản vá; persistent provisioning được chuyển đúng dependency sang IMP-M5-001 |
| IMP-M1-018 | `DONE` | Metrics sink/health visibility | Provider-free `/healthz` và Prometheus `/metrics` có bounded labels, ready/integration/service-error bootstrap; unit HTTP và Compose end-to-end checks đều pass với `state=ready`, `provider_calls=false` |
| IMP-M1-019 | `DONE` | Foundation operations runbook | `docs/runbooks/M1_FOUNDATION_OPERATIONS.md` bao phủ clean setup, secret-safe readiness, immutable build/image cleanup, start/stop, test tiers, cost-stop, recovery và break-glass; 6 contract/security tests pass. Clean-path solo dry run ngày 2026-08-10 pass toàn bộ checklist với locked offline bootstrap, reproducible two-image build, hardened healthy runtime, offline/dbt/audit gates và cost-stop cleanup |
| IMP-M1-020 | `DONE` | Migrate active source baseline from Yelp to Olist | ADR-008; nine-file manifest; config/license, fixture, Snowflake CSV format, PRD/plan/M0/M1/RAG/diagram updates; TC-M1-031 pass |

## Exit gate

M1 chỉ `COMPLETE` khi offline foundation tests pass và live synthetic R2→Snowflake connectivity cùng RBAC negative tests có evidence. Thiếu credentials hoặc provider access phải ghi `DEFERRED`, không được giả lập `PASS`.
