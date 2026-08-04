# M1 Test Cases and Results

## Test matrix

| ID | Loại | Scenario | Expected result | Status | Evidence |
|---|---|---|---|---|---|
| TC-M1-001 | Bootstrap | Lockfile và local Python environment reproducible | `uv sync --locked` thành công | `PASS` | `uv sync --locked --offline --cache-dir .uv-cache`: project built/installed successfully |
| TC-M1-002 | Static | Ruff format/lint | Không lỗi | `PASS` | `ruff format --check src tests`; `ruff check src tests` |
| TC-M1-003 | Static | Mypy strict | Không lỗi | `PASS` | `mypy src tests`: 0 issues |
| TC-M1-004 | Unit | Full pytest suite | Tất cả unit/contract tests pass | `PASS` | Offline suite: 15 passed, 1 live skipped, 83.33% coverage |
| TC-M1-005 | Config | Single-local config + `.env` precedence/ignore | `config/config.toml` không có secret/profile selector; process env ghi đè `.env`; `.env` bị ignore | `PASS` | Unit tests pass; `git check-ignore -v .env` → `.gitignore:2` ; old-profile scan 0 match |
| TC-M1-006 | Compliance | Real Yelp + managed provider | Config fail closed | `PASS` | `test_real_yelp_cannot_enable_managed_providers` pass |
| TC-M1-007 | Security | Secret-safe config summary | Không lộ secret | `PASS` | Secret-field scan 0 match; safe-summary unit test pass |
| TC-M1-008 | Fixture | Deterministic regenerate | File checksums giống nhau | `PASS` | `test_generator_is_deterministic` pass |
| TC-M1-009 | Fixture | Synthetic source contract | 5 required JSONL + manifest, không Yelp payload | `PASS` | 3 fixture safety/contract tests pass |
| TC-M1-010 | Adapter | Provider boundaries với fakes | Không hard-code secret/model | `PENDING` | R2 adapter/fake subset pass; các provider adapter khác chưa implement |
| TC-M1-011 | Logging | Seeded token/email/phone redaction | Log không chứa seeded values | `PENDING` | Chưa chạy |
| TC-M1-012 | Metrics | Synthetic health metric | Prometheus sample quan sát được | `PENDING` | Chưa chạy |
| TC-M1-013 | R2 contract | Bucket/prefix/private/lifecycle config | Static contract pass | `PASS` | Typed config + `infra/cloudflare_r2/lifecycle.json` + adapter contract tests pass |
| TC-M1-014 | R2 live | Put/head/get/list/delete synthetic object + anonymous deny | Tất cả pass, object được cleanup | `PASS` | Bucket-scoped credential, checksum, list, anonymous/account denial và post-delete absence pass |
| TC-M1-015 | Snowflake contract | DDL, X-SMALL/60s, monitor, stage | Static SQL contract pass | `PENDING` | Chưa chạy |
| TC-M1-016 | Snowflake live | Account facts + R2 stage `LIST`/`COPY INTO` | Synthetic row load/reconcile pass | `DEFERRED` | Cần local Snowflake/R2 credentials |
| TC-M1-017 | RBAC | Static positive/negative grant matrix | Forbidden grants absent | `PENDING` | Chưa chạy |
| TC-M1-018 | RBAC live | Service-role positive/negative queries | Least privilege pass | `DEFERRED` | Cần provisioned Snowflake roles |
| TC-M1-019 | dbt | `dbt parse` Snowflake-only | Parse pass; không DuckDB profile | `PENDING` | Chưa chạy |
| TC-M1-020 | Airflow | DAG import/task graph | Import không side effect; expected task IDs | `PENDING` | Chưa chạy |
| TC-M1-021 | App | Anonymous/authenticated shell behavior | Anonymous denied; valid token allowed | `PENDING` | Chưa chạy |
| TC-M1-022 | Audit | Migration up/down/static compatibility | Required schemas/tables, dev-only down guard | `PENDING` | Chưa chạy |
| TC-M1-023 | CI | Workflow required gates | Static workflow contract pass | `PENDING` | Chưa chạy |
| TC-M1-024 | Container | App image build/non-root | Build pass; runtime user non-root | `PENDING` | Chưa chạy |
| TC-M1-025 | Container | Airflow/Chroma single-local Compose config | `docker compose config` pass và chỉ dùng `config/config.toml` + `.env` | `PENDING` | Chưa chạy |
| TC-M1-026 | Deploy | Immutable artifact tag/rollback metadata | Deterministic digest + local-scope guard | `PENDING` | Chưa chạy |
| TC-M1-027 | Runbook | Required operations documented | Bootstrap/credentials/test/cost-stop/break-glass present | `PENDING` | Chưa chạy |
| TC-M1-028 | Secret scan | Repository tracked/untracked source scan | Không secret-like value | `PENDING` | Chưa chạy |
| TC-M1-029 | Data leak | Git-visible files deny Yelp/review/vector artifacts | Policy scan pass | `PASS` | `git status --untracked-files=all` scan: 0 prohibited data/artifact paths; `.env` untracked |
| TC-M1-030 | Status | Skill status validator | 0 errors/warnings | `PASS` | Validator: 0 errors, 0 warnings |

## Execution log — 2026-08-04

- Dependency resolution: `uv lock --check --cache-dir .uv-cache` pass, 237 packages.
- Dependency install for testing: `uv sync --locked --no-install-project --cache-dir .uv-cache` pass.
- Full `uv sync --locked` correctly remains `FAIL` because project metadata references the not-yet-created `README.md`; this is tracked under IMP-M1-001/002 and is not hidden by the partial install command.
- Static/unit evidence: Ruff pass, mypy pass, pytest 10/10 pass with 83.33% branch-aware coverage.
- Config policy evidence: `.env` ignored; no old profile path/selector references; no credential key assignments in `config/config.toml`.
- Workflow status validator: pass với 0 errors và 0 warnings.

### M1 bootstrap and R2 slice

- Credential readiness was checked as booleans only; `.env` is ignored/untracked and all required provider/app variables are present.
- Snowflake key-pair file exists and is ignored/untracked, but is currently inside the workspace; `*.p8` was added to `.gitignore` and moving the key outside the repo remains an owner action before Snowflake live work.
- `uv sync --locked --offline --cache-dir .uv-cache` built and installed the local package; config and fixture console entry points pass.
- Offline quality suite: Ruff pass, mypy strict pass, pytest 15 pass + 1 live skip, 83.33% coverage.
- First anonymous R2 probe returned unsigned-request HTTP 400, which still denied payload; the contract was corrected to accept R2 denial codes `400/401/403/404` and require response payload mismatch.
- Final live R2 test: 1 pass. The synthetic object was uploaded under `manifests/_smoke/`, checksum/retrieval/list verified, account-level bucket listing denied, anonymous payload denied, and object deleted/confirmed absent.
- Lifecycle configuration is versioned but not applied with the application token because Cloudflare lifecycle administration requires broader bucket-level authority; owner application/verification remains pending.
