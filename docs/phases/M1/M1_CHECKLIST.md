# M1 Checklist — Foundation, Single-local Configuration and Developer Platform

| Thuộc tính | Giá trị |
|---|---|
| Phase status | `IN_PROGRESS` |
| Completed | 8/20 work items |
| Partial | 1/20 work items |
| Blocked | 0/20 work items |
| Not started | 11/20 work items |
| Last updated | 2026-08-05 |

## Checklist theo implementation plan

| Work item | Status | Outcome cần đạt | Evidence / việc còn lại |
|---|---|---|---|
| IMP-M1-001 | `DONE` | Repo/package/lock/lint/type/test commands | `pyproject.toml`, `.python-version`, `uv.lock`; full `uv sync --locked --offline` và tool entry points pass |
| IMP-M1-002 | `DONE` | README, contribution, CODEOWNERS, PR/issue templates | `README.md`, `CONTRIBUTING.md`, `.github/CODEOWNERS`, PR + issue forms; repository contract tests pass |
| IMP-M1-003 | `DONE` | Một typed local config; `.env`/process-only secrets; không có staging/prod profiles | `config/config.toml`, `.env.example`, `src/reviewlens/config.py`; TC-M1-005…007 pass |
| IMP-M1-004 | `DONE` | Deterministic nine-CSV relational Olist fixture generator/pack | `src/reviewlens/synthetic/generator.py`; exact headers, FK integrity and determinism tests pass |
| IMP-M1-005 | `DONE` | Private R2 config, scoped token/lifecycle/public deny | Bucket-scoped live round trip, account-list denial, anonymous denial và cleanup pass; owner xác nhận lifecycle rule đã apply/enabled ngày 2026-08-05 |
| IMP-M1-006 | `DONE` | Snowflake foundation, monitor và R2 external stage | Secret-free idempotent DDL + in-memory stage DDL; XSMALL/60s/10-credit monitor; live R2 `LIST`/`COPY INTO`/reconcile pass và warehouse cleanup suspend |
| IMP-M1-007 | `DONE` | Least-privilege Snowflake/service roles | 9-role hierarchy dưới `SYSADMIN`, isolated `REVIEWLENS_SQL_WH`, container/exact-object grant boundary; static matrix và live 8-role positive/negative suite pass với secondary roles disabled |
| IMP-M1-008 | `NOT_STARTED` | Credential boundaries và rotation skeleton | Chờ implementation |
| IMP-M1-009 | `NOT_STARTED` | Snowflake-only dbt scaffold | Chờ implementation |
| IMP-M1-010 | `NOT_STARTED` | Airflow 3 DAG scaffold không có parse side effect | Chờ implementation |
| IMP-M1-011 | `PARTIAL` | Provider adapters + fakes | R2 và Snowflake adapters + fake/error-sanitization tests pass; OpenRouter/Chroma/audit/clock adapters còn lại |
| IMP-M1-012 | `NOT_STARTED` | Authenticated Streamlit shell + health/error state | Chờ implementation |
| IMP-M1-013 | `NOT_STARTED` | Audit schema up/down/compatibility migrations | Chờ implementation |
| IMP-M1-014 | `NOT_STARTED` | Structured logging, correlation và redaction | Chờ implementation |
| IMP-M1-015 | `NOT_STARTED` | CI lint/type/unit/contracts/dbt/security/container gates | Chờ implementation |
| IMP-M1-016 | `NOT_STARTED` | Non-root Docker images/entrypoints | Chờ implementation |
| IMP-M1-017 | `NOT_STARTED` | Local Compose/deploy skeleton + immutable artifact tags | Chờ implementation |
| IMP-M1-018 | `NOT_STARTED` | Metrics sink/health visibility | Chờ implementation |
| IMP-M1-019 | `NOT_STARTED` | Foundation operations runbook | Chờ implementation |
| IMP-M1-020 | `DONE` | Migrate active source baseline from Yelp to Olist | ADR-008; nine-file manifest; config/license, fixture, Snowflake CSV format, PRD/plan/M0/M1/RAG/diagram updates; TC-M1-031 pass |

## Exit gate

M1 chỉ `COMPLETE` khi offline foundation tests pass và live synthetic R2→Snowflake connectivity cùng RBAC negative tests có evidence. Thiếu credentials hoặc provider access phải ghi `DEFERRED`, không được giả lập `PASS`.
