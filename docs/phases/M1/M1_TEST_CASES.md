# M1 Test Cases and Results

## Test matrix

| ID | Loại | Scenario | Expected result | Status | Evidence |
|---|---|---|---|---|---|
| TC-M1-001 | Bootstrap | Lockfile và local Python environment reproducible | `uv sync --locked` thành công | `PASS` | `uv sync --locked --offline --cache-dir .uv-cache`: project built/installed successfully |
| TC-M1-002 | Static | Ruff format/lint | Không lỗi | `PASS` | `ruff format --check src tests`; `ruff check src tests` |
| TC-M1-003 | Static | Mypy strict | Không lỗi | `PASS` | `mypy src tests`: 0 issues |
| TC-M1-004 | Unit | Full pytest suite | Tất cả unit/contract tests pass | `PASS` | Offline suite after Olist migration: 45 passed, 3 live skipped, 87.23% branch-aware coverage |
| TC-M1-005 | Config | Single-local config + `.env` precedence/ignore | `config/config.toml` không có secret/profile selector; process env ghi đè `.env`; `.env` bị ignore | `PASS` | Unit tests pass; `git check-ignore -v .env` → `.gitignore:2` ; old-profile scan 0 match |
| TC-M1-006 | Compliance | Olist source/license configuration | CC BY-NC-SA, NonCommercial, attribution và ShareAlike không thể bị làm yếu | `PASS` | Olist config contract + three weakened-license negative tests pass |
| TC-M1-007 | Security | Secret-safe config summary | Không lộ secret | `PASS` | Secret-field scan 0 match; safe-summary unit test pass |
| TC-M1-008 | Fixture | Deterministic regenerate | File checksums giống nhau | `PASS` | `test_generator_is_deterministic` pass |
| TC-M1-009 | Fixture | Synthetic Olist source contract | 9 required CSVs + manifest, exact headers và valid relational FKs | `PASS` | Determinism/header/FK/source-directory/synthetic-content tests pass |
| TC-M1-010 | Adapter | Provider boundaries với fakes | Không hard-code secret/model | `PENDING` | R2 + Snowflake adapter/fake/error-sanitization subsets pass; OpenRouter/Chroma/audit/clock còn lại |
| TC-M1-011 | Logging | Seeded token/email/phone redaction | Log không chứa seeded values | `PENDING` | Chưa chạy |
| TC-M1-012 | Metrics | Synthetic health metric | Prometheus sample quan sát được | `PENDING` | Chưa chạy |
| TC-M1-013 | R2 contract | Bucket/prefix/private/lifecycle config | Static contract pass | `PASS` | Typed config + `infra/cloudflare_r2/lifecycle.json` + adapter contract tests pass |
| TC-M1-014 | R2 live | Put/head/get/list/delete synthetic object + anonymous deny | Tất cả pass, object được cleanup | `PASS` | Bucket-scoped credential, checksum, list, anonymous/account denial và post-delete absence pass |
| TC-M1-015 | Snowflake contract | DDL, X-SMALL/60s, monitor, stage | Static SQL contract pass | `PASS` | `infra/snowflake/001_foundation.sql` + `tests/test_snowflake.py`: secret-free DDL, config match, SQL parser, S3-compatible stage và error sanitization pass |
| TC-M1-016 | Snowflake live | Account facts + R2 stage `LIST`/`COPY INTO` | Synthetic row load/reconcile pass | `PASS` | Owner account facts documented; live test 1 pass: foundation deploy, exact-key `LIST`, one-row JSON `COPY INTO`/reconcile, R2 delete và warehouse suspend |
| TC-M1-017 | RBAC | Static positive/negative grant matrix | Forbidden grants absent | `PASS` | 7 contract tests: complete hierarchy, isolated SQL warehouse, ingest/transform boundaries, exact-only consumers, no PUBLIC/account/all-privilege/user grants |
| TC-M1-018 | RBAC live | Service-role positive/negative queries | Least privilege pass | `PASS` | 1 live suite pass in 40.25s: 8 primary roles, `USE SECONDARY ROLES NONE`, allowed operations pass, 25 cross-layer/write probes denied, fixture cleanup and two-warehouse suspend |
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
| TC-M1-029 | Data leak | Git-visible files deny Olist CSV/review/vector artifacts | Policy scan pass | `PASS` | `archive/`, `.env` and source/vector artifacts ignored; Git-visible scan contains metadata/docs only |
| TC-M1-030 | Status | Skill status validator | 0 errors/warnings | `PASS` | Validator: 0 errors, 0 warnings |
| TC-M1-031 | Migration | Active source baseline is Olist end to end | Config/license, 9-table fixture, Snowflake CSV format, docs/status/diagram and attribution agree; no active Yelp contract | `PASS` | ADR-008, source manifest, attribution; full offline suite 45 pass/3 expected live skip; active-reference scan reviewed |

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

## Execution log — 2026-08-05

### R2 owner gate and Snowflake foundation slice

- Owner confirmed the R2 lifecycle rule is applied/enabled and moved the Snowflake private key outside the repository. Safe checks found zero private-key files in the workspace; `.env` remains ignored/untracked.
- Added secret-free idempotent Snowflake foundation DDL for `REVIEWLENS`, six schemas, `REVIEWLENS_WH` at XSMALL/60-second auto-suspend, a 10-credit monthly monitor with 50/80/100% actions, and the JSONL file format.
- Added a Snowflake adapter with key-pair bootstrap, safe identifier/path validation, sanitized errors, an SQL splitter that preserves semicolons in quoted literals, and R2 stage DDL rendered only in memory from `.env` credentials.
- The first live attempt exposed the quoted-semicolon parser bug after the resource monitor step; cleanup ran, the parser was corrected and covered by a regression test. The retry passed in 16.63 seconds.
- Final Snowflake live evidence: foundation deploy succeeded; R2 exact-key `LIST` returned the synthetic object; `COPY INTO` loaded one row and reconciled `data_class`/`object_id`; cleanup deleted the R2 object and suspended the warehouse.
- Final offline gate: Ruff format/lint pass, mypy strict pass, pytest 30 pass + 2 explicitly skipped live tests, 86.47% branch-aware coverage; `uv lock --check` and locked offline sync pass.
- OpenRouter was not called and no real source payload, review text or embedding was used.

### Olist source-baseline migration

- Recorded the nine local CSV filenames, headers, row counts, byte sizes and SHA-256 values without printing row content.
- Added ADR-008 and CC BY-NC-SA attribution/non-commercial/ShareAlike release obligations.
- Migrated typed config from expiring Yelp terms to the Olist license contract while keeping `synthetic` as the M1 default data mode.
- Replaced the fixture contract with deterministic, relational nine-CSV Olist-shaped data and exact foreign-key tests.
- Added `OLIST_CSV_FORMAT` to Snowflake and scoped it to `INGEST_ROLE`; real source upload remains an M2 operator action.
- Added `archive/` and `olist_dataset/` to `.gitignore`; no local source CSV was deleted or committed.
- Full migration gate: Ruff format/lint pass, mypy strict pass, pytest 45 pass + 3 explicitly skipped live tests, 87.23% branch-aware coverage; lock check and locked offline sync pass.

### Snowflake least-privilege RBAC slice

- Added idempotent `infra/snowflake/002_roles.sql`: top custom `REVIEWLENS_OWNER` under `SYSADMIN` with eight service roles beneath it; no system role is granted downward and no role is granted directly to a user in this artifact.
- Added isolated `REVIEWLENS_SQL_WH` for Text-to-SQL at XSMALL/60-second auto-suspend on the existing 10-credit resource monitor.
- `INGEST_ROLE` is insert-only for Bronze/Quarantine plus external-stage/file-format usage. `TRANSFORMER_ROLE` is broad only for Bronze-read/Silver-build. AI, vector, Gold consumption, analyst, Text-to-SQL and RAG object access remains exact-grant-only.
- Static RBAC suite passed 7/7 tests, including forbidden PUBLIC/account/all-privilege/user grants and absence of schema-wide object grants on sensitive consumers.
- Live suite provisioned the role hierarchy twice to verify idempotency, disabled secondary roles for each probe and exercised all eight service roles. Positive reads/writes passed; 25 forbidden cross-layer reads/writes were denied.
- All RBAC fixture payloads were synthetic. Probe views/tables were dropped and both `REVIEWLENS_WH` and `REVIEWLENS_SQL_WH` were suspended during cleanup. No OpenRouter call was made.
- Final offline gate: Ruff format/lint pass, mypy strict pass, pytest 37 pass + 3 explicitly skipped live tests, 86.53% branch-aware coverage; locked dependency checks and secret/private-key/restricted-data scans pass.
