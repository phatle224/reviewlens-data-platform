# M1 Test Cases and Results

## Test matrix

| ID | Loại | Scenario | Expected result | Status | Evidence |
|---|---|---|---|---|---|
| TC-M1-001 | Bootstrap | Lockfile và local Python environment reproducible | `uv sync --locked` thành công | `PASS` | `uv sync --locked --offline --cache-dir .uv-cache`: project built/installed successfully |
| TC-M1-002 | Static | Ruff format/lint | Không lỗi | `PASS` | `ruff format --check src tests`; `ruff check src tests` |
| TC-M1-003 | Static | Mypy strict | Không lỗi | `PASS` | `mypy src tests`: 0 issues |
| TC-M1-004 | Unit | Full pytest suite | Tất cả unit/contract tests pass | `PASS` | 193 passed, 6 expected live skips, 88.78% branch-aware coverage |
| TC-M1-005 | Config | Single-local config + `.env` precedence/ignore | `config/config.toml` không có secret/profile selector; process env ghi đè `.env`; `.env` bị ignore | `PASS` | Unit tests pass; `git check-ignore -v .env` → `.gitignore:2` ; old-profile scan 0 match |
| TC-M1-006 | Compliance | Olist source/license configuration | CC BY-NC-SA, NonCommercial, attribution và ShareAlike không thể bị làm yếu | `PASS` | Olist config contract + three weakened-license negative tests pass |
| TC-M1-007 | Security | Secret-safe config summary | Không lộ secret | `PASS` | Secret-field scan 0 match; safe-summary unit test pass |
| TC-M1-008 | Fixture | Deterministic regenerate | File checksums giống nhau | `PASS` | `test_generator_is_deterministic` pass |
| TC-M1-009 | Fixture | Synthetic Olist source contract | 9 required CSVs + manifest, exact headers và valid relational FKs | `PASS` | Determinism/header/FK/source-directory/synthetic-content tests pass |
| TC-M1-010 | Adapter | Provider boundaries với fakes | Không hard-code secret/model; deterministic offline failures fail closed | `PASS` | R2/Snowflake/OpenRouter/Chroma/audit/clock adapter suites pass; configured models/secrets remain outside code and provider errors are sanitized |
| TC-M1-011 | Logging | Seeded secret/PII/review-text redaction | JSONL không chứa token, email, phone, URL, payment-like value, restricted text hoặc unsafe key đã seed | `PASS` | `tests/test_logging.py`: 11/11 pass; covers nested values/keys, exceptions, invalid events, context isolation/spoofing, bounds and level filtering |
| TC-M1-012 | Metrics | Synthetic health metric | Prometheus sample quan sát được | `PASS` | Provider-free loopback HTTP integration test quan sát `/healthz`, `reviewlens_foundation_ready`, bounded integration labels và service-error bootstrap; unknown route trả 404 |
| TC-M1-013 | R2 contract | Bucket/prefix/private/lifecycle config | Static contract pass | `PASS` | Typed config + `infra/cloudflare_r2/lifecycle.json` + adapter contract tests pass |
| TC-M1-014 | R2 live | Put/head/get/list/delete synthetic object + anonymous deny | Tất cả pass, object được cleanup | `PASS` | Bucket-scoped credential, checksum, list, anonymous/account denial và post-delete absence pass |
| TC-M1-015 | Snowflake contract | DDL, X-SMALL/60s, monitor, stage | Static SQL contract pass | `PASS` | `infra/snowflake/001_foundation.sql` + `tests/test_snowflake.py`: secret-free DDL, config match, SQL parser, S3-compatible stage và error sanitization pass |
| TC-M1-016 | Snowflake live | Account facts + dedicated R2 stage `LIST`/`COPY INTO` | Synthetic row load/reconcile pass using ingest write + stage read-only identities | `PASS` | Live test 1 pass in 15.96s: ingest upload, runtime stage recreate, exact-key `LIST`, one-row JSON `COPY INTO`/reconcile, R2 delete và warehouse suspend |
| TC-M1-017 | RBAC | Static positive/negative grant matrix | Forbidden grants absent | `PASS` | 7 contract tests: complete hierarchy, isolated SQL warehouse, ingest/transform boundaries, exact-only consumers, no PUBLIC/account/all-privilege/user grants |
| TC-M1-018 | RBAC live | Service-role positive/negative queries | Least privilege pass | `PASS` | 1 live suite pass in 40.25s: 8 primary roles, `USE SECONDARY ROLES NONE`, allowed operations pass, 25 cross-layer/write probes denied, fixture cleanup and two-warehouse suspend |
| TC-M1-019 | dbt | Snowflake-only `dbt parse/compile` | Nine Olist sources, model contract and tests parse; compile pass without introspection; no DuckDB/multi-env/password fallback | `PASS` | dbt-core 1.12.0 + dbt-snowflake 1.12.0: parse and selected compile pass with `--warn-error`, synthetic placeholder credentials and no provider connection; manifest contract pytest 3/3 pass |
| TC-M1-020 | Airflow | DAG import/task graph | Import không side effect; expected task IDs | `PASS` | 5 contract tests: real `airflow.sdk` DAG import in isolated subprocess, exact 11-task/10-edge graph, manual/single-run policy, per-task retry/timeout/pool, pool manifest and static provider/credential-access denial; no service or provider call |
| TC-M1-021 | App | Anonymous/authenticated shell behavior | Anonymous/invalid/missing token and remote bind denied; valid local token allowed; ready/degraded/unavailable/config-error states explicit | `PASS` | `tests/test_app.py`: 16/16 pass with Streamlit 1.60 `AppTest`; token never appears in rendered evidence, sign-out returns to gate, launcher uses fixed container root only for exact Compose marker and readiness performs no provider call |
| TC-M1-022 | Audit | Migration up/down/static compatibility | Required schemas/tables, dev-only down guard | `PASS` | 8 tests: exact six-table/versioned-column contract, DDL-only deterministic replay through adapter, AI privacy/cost fields, append-only exact grants, read-only release pointer, stable compatibility view and two-factor local rollback guard |
| TC-M1-023 | CI | Workflow required gates | Static workflow contract pass | `PASS` | `.github/workflows/ci.yml` least-privilege/pinned-action contract, Docker build/non-root checks và two SHA-pinned Trivy critical-CVE gates; không dùng secret/live flag hoặc silence failure |
| TC-M1-024 | Container | App image build/non-root | Build pass; runtime user non-root | `PASS` | App/Airflow digest-pinned builds pass; image config + live `id -u` return `10001`/`50000`; app `uv pip check` và Airflow `pip check` report no broken requirements |
| TC-M1-025 | Container security | Single-local Compose + Chroma quarantine | Compose app/metrics/Airflow pass; unpatched Chroma service/dependency/lock entry bị policy chặn và persistent server chỉ được provision ở M5 sau patched audit | `PASS` | Machine-readable GHSA-f4j7-r4q5-qw2c/CVE-2026-45829 policy review ngày 2026-08-11; positive repository policy và negative service/dependency/lock/missing/weakened-policy fixtures pass; Compose final-tag runtime evidence giữ nguyên |
| TC-M1-026 | Deploy | Immutable artifact tag/rollback metadata | Deterministic digest + local-scope guard | `PASS` | `reviewlens-artifacts --check` pass; manifest có full source SHA-256, deterministic local tag, image refs, no timestamp/host path và stale-source negative test |
| TC-M1-027 | Runbook | Required operations documented | Bootstrap/credentials/test/cost-stop/break-glass present | `PASS` | Runbook artifact + 6/6 contract/security tests pass. Clean-path solo dry run ngày 2026-08-10: locked offline bootstrap, secret-free degraded readiness, artifact/Compose/build, non-root/dependency/health/Airflow checks, full offline/dbt/audit gates và cost-stop cleanup đều pass |
| TC-M1-028 | Secret scan | Repository tracked/untracked source scan | Không secret-like value | `PASS` | `reviewlens-policy --root .`: 0 findings; negative fixtures chặn env/key/token/private-key/credential assignment và không echo canary value |
| TC-M1-029 | Data leak | Git-visible files deny Olist CSV/review/vector artifacts | Policy scan pass | `PASS` | `archive/`, `.env` and source/vector artifacts ignored; Git-visible scan contains metadata/docs only |
| TC-M1-030 | Status | Skill status validator | 0 errors/warnings | `PASS` | Validator: 0 errors, 0 warnings |
| TC-M1-031 | Migration | Active source baseline is Olist end to end | Config/license, 9-table fixture, Snowflake CSV format, docs/status/diagram and attribution agree; no active Yelp contract | `PASS` | ADR-008, source manifest, attribution; full offline suite 45 pass/3 expected live skip; active-reference scan reviewed |
| TC-M1-032 | Identity contract | Eight runtime services map one-to-one to dedicated Snowflake users and least-privilege roles | Exact inventory; no admin/owner role, duplicate user or shared key env | `PASS` | Typed config and negative validation tests pass |
| TC-M1-033 | Credential safety | Readiness exposes booleans only and fails closed when runtime secrets are absent | No credential value appears in output; missing env remains not-ready | `PASS` | Seeded-secret and isolated-empty-env unit tests pass |
| TC-M1-034 | Service connection | Snowflake runtime connector pins user/role/warehouse and key-pair auth | No password fallback; secondary roles verified empty/fail closed; provider errors sanitized | `PASS` | Connector fake, active-secondary-role negative, missing-key, provider and cleanup-error tests pass |
| TC-M1-035 | Rotation runbook | Snowflake/R2/OpenRouter/Chroma/app initial setup, rotation and emergency revocation are actionable | Windows prerequisites, exact UI/PowerShell/SQL/`.env` mapping, verification, troubleshooting, cutover/revoke and owner gates documented | `PASS` | Guided runbook contract pass; 13 PowerShell code blocks parse without syntax errors |
| TC-M1-036 | Identity live | Service-user provisioning and named-key authentication are exact | Two DDL applies; 8 users enabled with active role-scoped keys; JWT sessions match user/role/warehouse/database and have no secondary roles | `PASS` | Live Snowflake suite: 1 pass in 70.33s; all eight runtime identities authenticated; warehouses suspended |
| TC-M1-037 | Rotation live | Controlled named-key rotation/revocation smoke without admin fallback | New key succeeds with exact role; old key is denied after configured grace/revoke | `PASS` | Owner-approved isolated `ANALYST_ROLE` canary: live retry 1 pass in 7.80s; old key denied, new key exact session pass, active canary removed, original runtime key re-authenticated and warehouse suspended |
| TC-M1-038 | R2 runtime identities live | Ingestion is write-scoped and Snowflake stage is read-only | Ingest put/read/delete passes; stage read/list passes and direct write is denied; account listing denied; cleanup succeeds | `PASS` | Dedicated R2 live suite: 1 pass in 5.22s using synthetic smoke object only |
| TC-M1-039 | OpenRouter boundary | Only internal-control, synthetic or hash-verified DLP-approved text can cross the adapter; model/privacy route comes from policy/config | Restricted/hash-mismatched text is denied before HTTP; Bearer/model/payload shape and `data_collection=deny` are exact; errors leak no token/prompt/body | `PASS` | Deterministic `httpx.MockTransport` chat/embedding tests pass; no provider request left the process and no spend occurred |
| TC-M1-040 | Chroma boundary | Every collection is index-versioned and every result remains pinned to Snowflake `AI.RAG_DOCUMENT` authority | Upsert contains embeddings/reference metadata but no document text; mismatched source/release/index and restricted records fail closed | `PASS` | In-memory Chroma backend tests cover versioning, token header, loopback-only connection, dimension/version validation and sanitized errors |
| TC-M1-041 | Audit/clock boundary | Audit events are immutable, deterministic and secret-safe; clocks are aware UTC | Stable IDs/timestamps with fakes; sensitive metadata keys and unsafe names rejected | `PASS` | `InMemoryAuditSink`, `FrozenClock` and `SystemClock` unit tests pass |

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

### Dedicated service identity and rotation slice

- Added a typed one-to-one inventory for eight runtime services, each with an exact Snowflake service user, role, warehouse and private-key environment reference. Admin/owner roles, duplicate users and shared key references fail configuration validation.
- Added distinct environment references for R2 ingestion/stage credentials plus OpenRouter, Chroma and app tokens. Readiness output is boolean-only and remains fail-closed when values are absent.
- Added key-pair-only Snowflake service connections that pin the declared user/role/warehouse, set a query tag and disable secondary roles; password fallback is not available and provider failures are sanitized.
- Added secret-free idempotent `003_service_identities.sql`. The live suite applied it twice and verified all eight `TYPE=SERVICE` users have exact defaults and only the intended runtime role; users remain disabled until their public keys are registered.
- Added `M1_CREDENTIAL_ROTATION.md` covering normal and emergency rotation/revocation for Snowflake named keys, the two scoped R2 credentials, OpenRouter, Chroma and app auth.
- Final gate: Ruff format/lint pass, mypy strict pass, pytest 57 pass + 4 expected live skips, 88.83% branch-aware coverage; live identity suite 1 pass in 13.99s; lock check and locked offline sync pass. No warehouse data processing, R2 object operation or OpenRouter call occurred in this slice.

### Credential guide usability revision

- Replaced the terse rotation notes with a Vietnamese guided setup for Windows/PowerShell: current readiness, prerequisites, 8-key generation, Snowflake registration/fingerprint verification, exact `.env` mapping, two Cloudflare R2 token flows, Chroma token generation, readiness checks and troubleshooting.
- Verified against current official Snowflake named-key, Cloudflare R2 token and OpenRouter rotation documentation. The focused runbook contract passed 12/12 and all 12 PowerShell code blocks parsed without syntax errors.
- No credential was printed, changed or sent to a provider during this documentation-only revision.

### Runtime credential activation and R2 boundary slice

- Boolean readiness reports every runtime credential configured. The eight `.p8` paths initially appeared absent only inside the workspace sandbox; an approved filename/size-only check confirmed all 8 private and 8 public key files exist behind the intended Windows ACL.
- Extended the Snowflake live identity suite from provisioning metadata to real JWT authentication for all eight service users. Named keys are active and role-scoped; current user/role/warehouse/database match typed config and `CURRENT_SECONDARY_ROLES()` reports no active/requested roles.
- The first runtime attempt exposed Snowflake error `3107/42501`: role-restricted service sessions cannot execute the post-connect `USE SECONDARY ROLES NONE`. The adapter now verifies `CURRENT_SECONDARY_ROLES()` and fails closed if either role list/value is non-empty; direct JWT auth and the final 8-user live suite pass.
- Added R2 runtime-purpose construction that reads the dedicated ingestion/stage environment references rather than bootstrap secrets. The stage adapter rejects mutating methods locally before a provider call.
- Live R2 evidence proves the bucket-scoped ingestion credential can write/read/delete, the stage credential can read/list but Cloudflare denies a direct write, and both credentials are denied account bucket listing. The one synthetic object was removed.
- Final R2→Snowflake integration re-created the external stage with dedicated `R2_STAGE_*` credentials and passed `LIST`/`COPY INTO`/reconciliation in 15.96s; ingestion cleanup and warehouse suspension passed.
- Final offline gate: Ruff format/lint pass, mypy strict pass, pytest 61 pass + 5 expected live skips, 89.68% branch-aware coverage; lock check and locked offline sync pass. OpenRouter was not called and no Olist source data was accessed.

### Remaining provider, audit and clock boundary slice

- Added a typed OpenRouter adapter for configured enrichment/RAG/Text-to-SQL and embedding models. Every text carries an internal-control, synthetic or hash-verified DLP-approved transfer decision; restricted and hash-mismatched text is rejected before HTTP.
- OpenRouter requests use Bearer authentication, the documented `/chat/completions` and `/embeddings` endpoints, non-streaming deterministic payloads and `provider.data_collection=deny`. Tests use `httpx.MockTransport`; no request reached OpenRouter and no cost was incurred. Contract references: [chat completion](https://openrouter.ai/docs/api/api-reference/chat/send-chat-completion-request), [embeddings](https://openrouter.ai/docs/api/api-reference/embeddings/create-embeddings).
- Added a lazy-loaded local Chroma `HttpClient` boundary with loopback-only host and `x-chroma-token`. Collections use `reviewlens_rag_<index_version>`; upsert sends embeddings plus release/hash/policy metadata and intentionally omits document text because Snowflake `AI.RAG_DOCUMENT` is authoritative. Contract references: [Python client](https://docs.trychroma.com/reference/python/client), [collection upsert/query](https://docs.trychroma.com/reference/python/collection).
- Chroma query validates source table, data release and index version before returning only `chunk_id + distance`; wrong authority metadata fails closed. All Chroma tests use an in-memory backend, so no local collection was created.
- Added an audit sink protocol, immutable event contract, secret-key metadata denial, in-memory fake, UTC system clock and frozen test clock. The Snowflake audit ledger remains correctly scoped to dependent `IMP-M1-013`.
- Focused suite: 30/30 pass. Full gate: Ruff format/lint pass, mypy strict pass, pytest 91 pass + 5 expected live skips, 90.09% branch-aware coverage; `uv lock --check` và locked offline sync pass. No OpenRouter call, Chroma write, managed-resource mutation or Olist source access occurred.

### Snowflake-only dbt foundation slice

- Added a single-local dbt Core project under `dbt/` with one `local` Snowflake target. The profile pins `REVIEWLENS_TRANSFORM_SVC`, `TRANSFORMER_ROLE`, `REVIEWLENS_WH`, `REVIEWLENS.SILVER` and key-pair environment references; it has no password, admin role, DuckDB adapter, staging or production target.
- Declared all nine exact immutable Bronze source identifiers and privacy/license metadata. Review source metadata explicitly records restricted UGC and DLP-before-external-AI policy.
- Added a metadata-only `DBT_SOURCE_CONTRACT_REGISTRY` view contract for the nine filenames, relations and grains, plus a reusable compound-uniqueness generic test and M1 selector. It contains no Olist rows or review text; M2 still owns Bronze creation/load and M3 owns conformed models.
- `dbt parse` is the offline project/YAML/Jinja gate per [dbt command documentation](https://docs.getdbt.com/reference/commands/parse). Selected `dbt compile --no-introspect --no-populate-cache` follows the documented introspection controls and compiled successfully with placeholder account/key values, proving that this slice did not connect to Snowflake ([compile documentation](https://docs.getdbt.com/reference/commands/compile)).
- dbt focused evidence: 3/3 pytest contracts pass; parse and compile find 1 contracted model, 10 data tests and 9 sources with warnings promoted to errors. Full gate: Ruff format/lint, mypy strict, 94 pytest pass + 5 expected live skips, 90.09% branch-aware coverage, uv lock check and locked offline dbt-group sync pass.
- No warehouse was resumed, no Snowflake/R2/OpenRouter/Chroma operation ran, and no Olist source data was read.

### Airflow 3 orchestration scaffold slice

- Added the public `airflow.sdk` `olist_pipeline` DAG with the stable 11-task path from source validation through R2/Bronze, dbt Silver, enrichment, embeddings, dbt Gold and publish. It is manual-only, fixed-start, non-catchup and limited to one active run.
- Every task has an explicit one-slot resource pool, one or two retries with five-minute delay, and a 10-60 minute execution timeout. The `reviewlens_ai` pool serializes paid OpenRouter work; all four one-slot pools are versioned in `airflow/pools.json` but are not created as an import side effect.
- Task bodies intentionally fail closed in M1. An accidental trigger stops before reading credentials, accessing Olist data, changing managed resources or spending OpenRouter budget; M2-M5 replace guards only with their owning tested implementations.
- The real DAG imports in an isolated subprocess with network connect and dotenv access blocked. Tests assert the exact 11 tasks/10 edges, retry/timeout/pool policies, manual/single-run controls, pool manifest and a static allowlist of import-safe modules.
- Native Windows is not an Airflow runtime target; the import-only test adds the missing POSIX fork hook inside its isolated process. The supported local runtime remains the Linux Compose service planned by `IMP-M1-016`.
- Focused Airflow suite: 5/5 pass. Full gate: Ruff format/lint plus Airflow 3 rules pass, mypy strict pass, pytest 99 pass + 5 expected live skips, 90.09% branch-aware coverage; uv lock check, locked offline Airflow+dbt sync and dbt warnings-as-errors parse/compile pass.
- No `.env` value was exposed, no live service/provider was called, no warehouse was resumed, no object was uploaded and no Olist source row was read.

## Execution log — 2026-08-06

### Snowflake audit-ledger migration slice

- Added `004_audit_ledgers.sql` with six versioned objects: append-only ingestion, source-file, process, release and AI invocation ledgers plus the guarded active-release pointer. A constant `SCHEMA_COMPATIBILITY` view exposes migration ID/version/artifact without storing source data.
- Ledger columns cover source/batch/run/attempt/release lineage, checksums, reconciliation counts, model/prompt/schema/policy versions, tokens, latency, cost, hashes and sanitized error codes. No raw payload, review text, prompt text, response body or credential field exists.
- Runtime access is exact-table only. Producers receive `SELECT, INSERT` on their event ledgers with no update/delete/truncate/ownership/future-table grant. The active pointer remains read-only until M3 adds the owner-executed guarded release procedure.
- The up migration is `CREATE ... IF NOT EXISTS` DDL only: no replace/drop/DML and no `USE WAREHOUSE`, so applying it does not resume compute. A deterministic adapter replay test executes the identical statement plan twice.
- Added destructive `004_audit_ledgers_down.sql` as one Snowflake Scripting block. It reads two session variables and raises a declared exception before the first DROP unless runtime is exactly `local` and confirmation exactly matches the documented phrase.
- Focused audit migration suite: 8/8 pass. Full gate: Ruff format/lint + Airflow rules pass, mypy strict pass, pytest 107 pass + 5 expected live skips, 90.09% branch-aware coverage; locked offline Airflow+dbt sync, uv lock check and dbt warnings-as-errors parse/compile pass.
- No `.env` value was printed, no live Snowflake/R2/OpenRouter/Chroma call ran, no warehouse was resumed and no Olist data was read.

## Execution log — 2026-08-07

### Structured logging, correlation and redaction slice

- Added a direct `structlog` JSONL boundary with stable event/component names, UTC timestamps and minimum-level filtering. Reconfiguration is deterministic for CLI, Airflow task and local app entrypoints.
- Added context-local `trace_id`, `source_release_id`, `ingestion_batch_id`, `dataset_run_id`, `process_run_id` and `release_id`. Call-site fields cannot spoof correlation context; a valid fallback trace is generated when no context is bound.
- Added recursive fail-closed redaction for configured secret canaries, protected field names, email, phone, URL, payment-like strings, raw/review/prompt/query fields, binary values, unsafe mapping keys, oversized/deep collections and unknown objects.
- Exception logs retain only the exception type; raw exception message and traceback values are dropped before JSON rendering. Raw free text cannot be used as an event name.
- Focused logging suite: 11/11 pass. Full offline gate: Ruff format/lint plus Airflow rules pass, mypy strict pass, pytest 118 pass + 5 expected live skips, 90.15% branch-aware coverage; locked offline Airflow+dbt sync, lock check and dbt warnings-as-errors parse/compile pass.
- No `.env` value or Olist source row was read; no Snowflake/R2/OpenRouter/Chroma call ran, no warehouse resumed and no paid usage occurred.

## Execution log — 2026-08-08

### Authenticated Streamlit foundation-shell slice

- Added `reviewlens-app`, which loads the single `config/config.toml` and launches Streamlit on the validated loopback host/port with headless mode, CORS/XSRF protection, hidden browser error details and telemetry disabled. No second environment profile or committed secret config was introduced.
- Added a masked local token gate using SHA-256 digests plus constant-time comparison. Candidate tokens are removed from session state after each attempt; anonymous, wrong, missing and oversized credentials fail closed, while sign-out clears authenticated state.
- Added boolean-only configuration readiness with explicit `ready`, `degraded` and `unavailable` states. It checks dedicated credential presence through the existing security boundary and clearly states that page load performs no Snowflake/R2/OpenRouter/Chroma request.
- The authenticated M1 page labels its content as synthetic/configuration evidence and explicitly reports that no active analytics release exists, so partial/missing backends cannot be mistaken for real data.
- Focused app suite: 15/15 pass using Streamlit 1.60 native `AppTest`, including anonymous/valid/invalid/missing auth, logout, remote-bind/auth-disable rejection, launcher flags, degraded/unavailable/config-error states and seeded token/error leak canaries.
- Full offline gate: Ruff format/lint plus Airflow rules pass, mypy strict pass, pytest 133 pass + 5 expected live skips, 91.06% branch-aware coverage; `uv lock --check`, locked offline Airflow+dbt sync and dbt warnings-as-errors parse/compile pass.
- Dependency download was limited to packages already pinned by the Streamlit extra in `uv.lock`; no `.env` value/Olist row was printed, no managed provider was called and no project service cost was incurred.

## Execution log — 2026-08-09

### CI quality, security and dependency gates

- Added a least-privilege GitHub Actions workflow for push, pull request and manual dispatch. Checkout does not persist credentials; `setup-uv` is pinned by commit SHA and the workflow never reads repository secrets or enables live-provider tests.
- The workflow performs locked Airflow/dbt sync, Ruff format/lint and Airflow 3 rules, mypy strict, full branch-aware pytest, dbt parse/compile without introspection, repository policy, dependency audit and project-status validation. Failures are not silenced.
- Added `reviewlens-policy`, which scans tracked and untracked non-ignored paths without printing file content. It blocks env/private-key files, secret patterns and credential assignments, Olist/row-level artifacts outside explicit synthetic fixtures, unsafe paths and premature Docker/Compose artifacts.
- Added 18 focused workflow/policy tests, including deliberate failing fixtures for secret, key, environment, Olist, Parquet, Docker, unsafe-path and placeholder-shadowing cases. CLI failure evidence contains only path/rule, never the seeded canary.
- Initial `pip-audit` correctly found 17 advisories across cryptography, GitPython, pyOpenSSL and pytest; an all-extras audit found one additional unpatched Chroma advisory. Patched dependencies were upgraded without suppressions; Snowflake Connector moved from 3.x to 4.7.2 because 3.x constrained vulnerable pyOpenSSL `<26`. The inactive Chroma extra was removed from M1 and may only be re-enabled in M5 after a clean audit.
- Final hash-pinned dependency audit from all locked groups/extras reports `No known vulnerabilities found`. Regression after upgrade: Ruff/Airflow rules pass, mypy strict pass, dbt-core/dbt-snowflake 1.12 parse/compile pass, repository policy 0 findings, and pytest 151 pass + 5 expected live skips with 90.87% branch-aware coverage.
- No provider credential was read, no live test/provider call ran, no warehouse resumed, no Olist row was read/uploaded and no project service cost was incurred. Actual container build/non-root verification remains owned by `IMP-M1-016`; until then CI rejects container artifacts.

## Execution log — 2026-08-10

### Fast bundle: container, local deploy metadata and health visibility

- Added separate app and Airflow images with immutable base digests. Final runtime identities are `10001:10001` and `50000:0`; the Docker context excludes secrets, keys and row-level data artifacts.
- Added one `compose.yaml` for the local portfolio runtime. All services publish only on `127.0.0.1`, use read-only roots, drop all capabilities and enable `no-new-privileges`; only app/metrics read the ignored `.env`, while Airflow receives no provider/app credentials. `docker compose config --quiet` passes.
- Chroma is deliberately absent from Compose: latest audited `chromadb` 1.5.9 remains affected by critical unauthenticated code-injection advisories. The fake-tested adapter remains available, but no vulnerable server/package is provisioned.
- Added deterministic source hashing and `deploy/artifacts.lock.json`; source changes invalidate the `local-sha256-*` tag. CI builds both images, verifies final users and scans both images with Trivy v0.36.0 pinned to a full commit SHA.
- Added provider-free `/healthz` and `/metrics` endpoints. The live loopback integration test observes ready/configured/service-error metrics without reading or returning credential values and without any provider call.
- Focused suite: 49/49 pass. Full offline gate: Ruff/Airflow rules pass, mypy strict pass, pytest 167 pass + 5 expected live skips with 88.74% branch-aware coverage; dbt 1.12 parse/compile, artifact check, repository policy and hash-pinned dependency audit pass.
- Docker Engine 29.5.3 build và runtime smoke pass. App/metrics/Airflow cùng final artifact tag đều healthy; live UIDs là 10001/50000, dependency checks sạch, four Airflow pools imported và paused `olist_pipeline` discovered.
- Docker Scout local scan không chạy vì máy chưa đăng nhập Docker ID; không yêu cầu thêm credential để build/smoke. CI giữ two Trivy v0.36.0 critical-CVE scans pinned bằng full SHA, kết quả chỉ được ghi khi workflow thực sự chạy.
- No Snowflake/R2/OpenRouter/Chroma request ran, no Olist row was read/uploaded, no warehouse resumed and no project service cost was incurred.

### Foundation operations runbook and local image cleanup

- Đối chiếu `deploy/artifacts.lock.json` với Docker inventory và giữ đúng hai final images `reviewlens/app:local-sha256-2c8290023e540a1c` cùng `reviewlens/airflow:local-sha256-2c8290023e540a1c`. Mười tag build cũ không gắn container đã được xóa bằng exact references; base images, final images, BuildKit cache và Airflow volume không bị xóa.
- Added `M1_FOUNDATION_OPERATIONS.md` cho solo Windows operator: prerequisites, clean clone, one-config/ignored-env readiness, artifact build, dry-run-first allowlisted image cleanup, Compose health, offline/dbt/audit gates, stop/update, cost-stop, troubleshooting, Airflow metadata recovery và credential break-glass.
- Default path không bật live flags, không trigger DAG, không public port, không gọi provider và không dùng Olist rows. Destructive Airflow volume reset yêu cầu exact typed confirmation; image cleanup không dùng force/global prune.
- Focused runbook suite: 6/6 pass. Full offline regression: Ruff/Airflow rules pass, mypy strict pass, pytest 173 pass + 5 expected live skips với 88.74% branch-aware coverage.
- Clean-path evidence ngày 2026-08-10 trên Windows 10.0.26200, Git 2.51.0, Python 3.13.7, uv 0.10.9, Docker Engine 29.5.3/Desktop 4.78.0 và Compose 5.1.4. Snapshot Git cục bộ `1b8ff58` có working tree sạch; `.env` được ignore, không có project key file và config readiness degraded an toàn khi thiếu credential.
- Locked offline bootstrap cài 206 packages; artifact tag `local-sha256-2c8290023e540a1c`, Compose render và clean-path build của app/Airflow pass. App/Airflow chạy UID 10001/50000, dependency checks sạch; app, metrics và Airflow healthy trên `127.0.0.1`.
- `/healthz` trả `provider_calls_performed=false`; bốn ReviewLens pool có đúng một slot và `olist_pipeline` tồn tại ở trạng thái paused. dbt 1.12 parse/compile no-introspect, repository policy, artifact/status validator và hash-pinned dependency audit đều pass.
- `docker compose down` đã xóa clean-room container/network nhưng giữ `reviewlens-local-airflow-runtime` và đúng hai final image. Không bật live flag, không gọi Snowflake/R2/OpenRouter/Chroma, không đọc/upload Olist và không phát sinh project service cost; `IMP-M1-019`/TC-M1-027 được đóng `DONE/PASS`.

## Execution log — 2026-08-11

### Chroma critical-advisory quarantine and M1 sequencing

- Official re-audit found Python package/release 1.5.9 remains latest while GitHub-reviewed `GHSA-f4j7-r4q5-qw2c`/`CVE-2026-45829` marks `>=1.0.0,<=1.5.9` critical and lists no patched version.
- Added `deploy/chroma-security-policy.json` with exact advisory range, latest observed release, review date, source URLs and the explicit M5 provisioning trigger. Architecture remains local/versioned Chroma; only unsafe provisioning timing moves from M1 to existing `IMP-M5-001`.
- Extended `reviewlens-policy` to fail closed on missing/weakened baseline, a Chroma Compose service, direct Python dependency or `uv.lock` entry. Validation is static and makes no network request; CI already runs this gate before Compose build.
- Positive policy plus negative service/dependency/lock/missing/weakened fixtures pass. Compose remains hardened app/metrics/Airflow only; no vulnerable Chroma package/image/server was installed or started.
- Full gate: Ruff/Airflow rules pass, mypy strict pass, pytest 178 pass + 5 expected live skips với 88.62% branch-aware coverage; dbt 1.12 parse/compile no-introspect, lock/artifact/status checks, repository policy và hash-pinned audit đều pass.
- New artifact tag `local-sha256-4cac8b541993b042` built app/Airflow successfully. Runtime smoke confirms app/metrics/Airflow healthy on loopback, UIDs 10001/50000, clean dependency checks, four one-slot pools, paused `olist_pipeline`, `provider_calls_performed=false` and ready metrics.
- Cost-stop removed smoke containers/network and exact old app/Airflow tag `local-sha256-2c8290023e540a1c`; named Airflow volume and only the two current final images remain. No provider credential value was printed, no live flag enabled, no provider call/Olist access occurred and no project service cost was incurred.

## Execution log — 2026-08-12

### Isolated Snowflake named-key rotation rehearsal

- Added a fixed rotation plan pinned to read-only `REVIEWLENS_ANALYTICS_SVC`/`ANALYST_ROLE` and temporary `REVIEWLENS_ROTATION_SMOKE`; callers cannot select a broader service target or mutate the active `REVIEWLENS_RUNTIME` key.
- Added exact two-layer live opt-in, safe identifier/public-key SQL rendering, one-day canary expiry and immediate old-canary revocation. Unsafe confirmation, filename, public-key body, grace period and expiry variants fail closed offline.
- The live test verifies the existing runtime key before mutation, rejects a stale active canary, generates two ephemeral RSA keys in an isolated temp directory, proves old/new authentication behavior and exact session facts, removes the active canary and suspends compute in nested `finally` cleanup, then rechecks the original runtime key.
- Credential runbook now documents the exact owner command, expected `1 passed`, evidence exclusions and narrow manual cleanup. All 13 PowerShell blocks parse with zero syntax errors.
- Focused gate: 28 pass + 1 expected live skip. Full offline regression after implementation: Ruff format/lint pass, mypy strict pass, pytest 193 pass + 6 expected live skips with 88.78% branch-aware coverage; repository policy and immutable artifact checks pass.
- At the offline rehearsal checkpoint, TC-M1-037 remained `PENDING`: no live flag was enabled, no provider call occurred and owner confirmation was still required before the isolated live authentication mutation.

### Owner-approved live rotation evidence

- Owner explicitly approved the isolated Snowflake rotation smoke on 2026-08-12. The test used `REVIEWLENS_ANALYTICS_SVC`/`ANALYST_ROLE` and temporary `REVIEWLENS_ROTATION_SMOKE`; it did not alter the active `REVIEWLENS_RUNTIME` key.
- First execution reached and passed old-key denial plus new-key exact-role authentication, then exposed one evidence-only assumption: with grace `0`, Snowflake had already purged the expired rotated-out tombstone before `SHOW`. Nested `finally` cleanup ran; the retry preflight confirmed no stale active canary remained.
- The assertion was tightened to accept an absent immediately expired tombstone, while still requiring any visible tombstone to be `DISABLED` or `EXPIRED`. Focused offline regression passed 28 tests with the live test expectedly skipped.
- Final live command: `REVIEWLENS_RUN_LIVE_SNOWFLAKE_ROTATION=1` plus exact non-secret owner confirmation, running `tests/live/test_snowflake_rotation_live.py`. Result: 1 pass in 7.80 seconds; six third-party pyOpenSSL deprecation warnings, no functional/security failure.
- Final run proved: current runtime key works before mutation; temporary old key works before rotation and fails after immediate revoke; new key works with exact user/role/warehouse/database; active smoke key is absent after cleanup; original runtime key still works; warehouse suspend executed.
- No secret/key body/path was printed or committed, no Olist/R2/OpenRouter/Chroma operation occurred and no paid AI cost was incurred. `TC-M1-037`, `IMP-M1-008` and the M1 phase are closed `PASS`/`DONE`/`COMPLETE`.
