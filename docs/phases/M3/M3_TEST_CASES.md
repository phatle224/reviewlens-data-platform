# M3 Test Cases and Results

## Test matrix

| ID | Type | Scenario | Expected result | Status | Evidence |
|---|---|---|---|---|---|
| TC-M3-001 | Identity | Same processing inputs/contract are planned twice | Stable processing-run and candidate IDs | `PASS` | Deterministic order-independent identity test passes |
| TC-M3-002 | Lineage | One process consumes multiple immutable Bronze inputs | Ordered 1:N refs persist without loss | `PASS` | Two ordered unique input refs and reverse-order equivalence pass |
| TC-M3-003 | Replay | Same ledger event is appended twice | Replay is idempotent; conflicting payload is denied | `PASS` | Registry replay plus two-pass migration adapter test pass |
| TC-M3-004 | Negative/security | Invalid ID, physical identifier, secret-like metadata or raw value | Fail closed with stable row-safe error | `PASS` | Invalid/duplicate/sensitive identifiers return `WAREHOUSE_CANDIDATE_INVALID` without echoing input |
| TC-M3-005 | Candidate isolation | Two processing runs build Silver concurrently | Distinct physical namespaces and no cross-write | `PASS` | Contract-version runs produce different candidate-prefixed physical objects |
| TC-M3-006 | Concurrency | Two owners claim the same candidate | Exactly one active lease owner | `PASS` | Eight-thread test records one owner and seven denied claims |
| TC-M3-007 | Cleanup safety | Cleanup targets active/tested or foreign candidate | Denied; only terminal unreferenced candidate is eligible | `PASS` | Building/test-passed/active refs denied; failed unreferenced candidate cleans once |
| TC-M3-008 | Migration contract | Processing/input/candidate reference DDL and grants | Additive, append-only, exact-role and secret-free | `PASS` | Three-table DDL, compatibility marker, exact 8 grants and replay tests pass offline |
| TC-M3-009 | dbt source set | Parse Bronze source definitions | Exactly nine canonical Olist relations | `PASS` | YAML identifiers exactly equal the nine Bronze DDL tables |
| TC-M3-010 | dbt source columns | Compare YAML columns with Bronze DDL | Typed business and canonical lineage columns match | `PASS` | Exact name/type comparison passes for every declared column |
| TC-M3-011 | Freshness | Inspect all source freshness contracts | `INGESTED_AT` loaded-at field and bounded warn/error rules present | `PASS` | Warn 2 days/error 7 days on `ingested_at` verified |
| TC-M3-012 | dbt source tests | Inspect key, not-null and relationship-ready tests | Grain/lineage tests exist without exposing raw payload | `PASS` | Nine canonical four-column grain tests, lineage not-null and fail-closed raw metadata verified |
| TC-M3-013 | dbt parse/docs | Offline parse with synthetic environment | Zero warnings/errors; docs/meta retain privacy and license | `PASS` | dbt 1.12 parse `--warn-error` passes offline; CC BY-NC-SA/private/DLP metadata and selector verified |
| TC-M3-014 | Silver customer | Duplicate/customer geography/privacy fixtures | One customer row and minimized repeat key | `PASS` | Deterministic key/normalization oracle and static dbt grain/privacy contract pass; raw repeat ID is not an output column |
| TC-M3-015 | Silver geography | ZIP occurrences and malformed coordinates | Deterministic centroid; no join multiplication | `PASS` | Two-point centroid/count fixture plus ambiguous/no-valid-coordinate cases pass at one ZIP row |
| TC-M3-016 | Silver order | Status/time/scope edge fixtures | Declared analysis scope and intervals deterministic | `PASS` | Six scope cases plus on-time boundary and negative-interval suppression pass against versioned contract oracle |
| TC-M3-017 | Silver item/payment | Composite keys, amounts and reconciliation | Keys/ranges/counts pass | `PASS` | Compound partition/tests, valid/invalid/orphan amount oracles and zero-delta item+freight/payment fixture pass |
| TC-M3-018 | Silver product/seller | Translation, corrected length and location | Contracted columns and unknown fallback pass | `PASS` | Corrected canonical length aliases, translation `UNKNOWN` fallback, seller normalization and unique ZIP-quality lookup contracts pass |
| TC-M3-019 | Silver review/DLP | Empty, orphan, duplicate and restricted text | Base score retained; AI eligibility minimized | `PASS` | Five eligibility/interval fixtures plus invalid-score negative test pass; restricted fields deny external transfer and SQL hard-sets `ai_eligible=false` |
| TC-M3-020 | DQ gate | Critical/warn/quarantine fixtures | Critical failure blocks candidate publication | `PASS` | Order-independent severity/count/fingerprint fixtures pass; warning/quarantine remain nonblocking, critical result moves candidate to `FAILED`; duplicate/raw identifier negatives fail sanitized; dbt critical selector resolves exactly one metadata-only test |
| TC-M3-021 | Late/unknown | Reordered, late and orphan inputs | Deterministic unknown/correction policy | `PASS` | Four stable distinct unknown keys pass; shuffled/replayed revisions select the same correction and label older effective row `LATE_SUPERSEDED`; mixed-entity/unsafe-time negatives fail closed; eight Silver bases use the shared ranking macro |
| TC-M3-022 | Dimensions/facts | Declared grains and relationships | No unexpected multiplication or loss | `PASS` | Stable/version-scoped key, unknown, shuffled SCD boundary, overlap-negative and exact fact-partition fixtures pass; manifest has 5 dimensions + 4 facts in `GOLD`; relationships/grains plus count and item/payment amount reconciliation tests are selected by `m3_gold_base`; review fact has no restricted text |
| TC-M3-023 | Attribution | Multi-item order review metrics | Allocation labels present; no silent double count | `PASS` | Policy `olist-review-item-equal-weight-v1` labels every bridge row; deterministic residual makes weight/count sum exactly 1 and allocated score sum to source score for one/two/three items; zero-item fallback preserves review; shuffled inputs are invariant and duplicate/invalid grains fail closed |
| TC-M3-024 | Marts/semantic | Metric dictionary and serving allowlist fixtures | Golden outputs and approved semantic fields match declared grains | `PASS` | Golden fixtures verify order/delivery/value totals, null zero-denominators, fractional allocated review sample/score and distinct lifetime repeat-customer rate with unknown exclusion; four monthly mart grains reconcile offline; semantic catalog/dbt contracts expose only four logical views with approved dimensions/measures, policy labels and partial-AI state while physical names, restricted IDs/text and unsafe roles fail closed |
| TC-M3-025 | Candidate failure | Silver/Gold candidate fails a gate | Active serving pointer remains unchanged | `PASS` | Baseline tested release activates at pointer v1; a second untested Gold candidate is denied release-definition creation and leaves pointer/event count unchanged; no failed candidate can reach activation |
| TC-M3-026 | CAS/replay | Concurrent activation, rollback and replay | One CAS winner; rollback uses immutable release | `PASS` | Deterministic definition/replay, stale-CAS denial, two-writer race with exactly one winner, activation replay and rollback replay all pass; pointer version advances 0→1→2→3 and rollback references a prior immutable definition |
| TC-M3-027 | Request pinning | Concurrent requests during activation | Each request uses one complete release | `PASS` | Resolver snapshots one pointer then resolves only catalog logical names from its immutable definition; no-pointer, raw/physical, duplicate and unowned-type inputs fail closed, and 16 concurrent pins racing activation each contain refs from exactly one Gold candidate |
| TC-M3-028 | Equivalence/cost | Full versus incremental two-run drill | Row/hash equality, bounded X-Small usage and suspend | `PENDING` | Await IMP-M3-020; owner opt-in required |
| TC-M3-029 | Repository policy | Scan Git-visible files | No raw Olist, review text, secret or generated dbt target | `PASS` | `reviewlens-policy --root .`: 0 findings; artifact `local-sha256-1cee93f22baa9ecc`, dependency lock and project-image dry-run pass |
| TC-M3-030 | Status | Validate phase artifacts and plan synchronization | Zero errors/warnings | `PASS` | Workflow validator: M3 19/20 done, 29/30 pass, 0 errors and 0 warnings |

## Execution log — 2026-08-14

- M3 artifacts initialized after M2 closed 18/18 work items and its full private
  nine-file DAG/replay exit gate.
- Active bundle is `IMP-M3-001…003`. It is offline-only: no Snowflake warehouse,
  R2, OpenRouter or Chroma call is authorized in this bundle.
- `IMP-M3-001…003` implementation gate: Ruff format/lint, strict mypy and 26
  focused tests pass. Offline dbt 1.12 parse passes with warnings-as-errors.
- Full repository regression: 352 passed, 8 expected opt-in live skips and
  86.17% coverage. Repository policy reports 0 findings; immutable artifact
  metadata is `local-sha256-eb995b79eda8a3c4` and both artifact/dependency locks pass.
- Workflow status validator reports M3 at 3/20 work items and 15/30 passing tests
  with 0 errors and 0 warnings.
- No managed provider was called. Applying migration `006` and executing the live
  dbt source/freshness selector remain explicit later gates, not evidence claimed
  by this offline bundle.
- `IMP-M3-004…006` adds three candidate-prefixed, contract-enforced dbt tables and
  a fail-closed runtime identifier test. Ruff, strict mypy, offline dbt parse and
  41 focused M3/retention tests pass; no Snowflake model was built in this session.
- Docker inventory found 12 unused Airflow tags caused by repeated source-hash
  builds. Eleven exact stale `reviewlens/airflow:*` references were removed while
  preserving the latest tested Airflow image, the only app image and the named
  Airflow volume. `reviewlens-images` now provides allowlisted dry-run/apply
  retention; it never performs global prune or build-cache/volume deletion.
- Full repository regression after bundle 2: 369 passed, 8 expected opt-in live
  skips and 85.62% coverage. Repository policy reports 0 findings; artifact and
  dependency locks pass. Final retention dry-run reports no stale project image.

## Execution log — 2026-08-15

- `IMP-M3-007…009` adds six candidate-prefixed, contract-enforced dbt models for
  item/payment, category/product/seller and restricted review bases. No raw
  payload is selected and review rows cannot become AI-eligible before M4 DLP.
- Ruff format/lint, strict mypy, dbt 1.12 parse with warnings-as-errors and 41
  focused M3 tests pass using contract/static and deterministic synthetic oracles.
- No Docker build and no Snowflake, R2, OpenRouter or Chroma call was performed.
  Live candidate build remains an explicit later owner-approved gate.
- Full repository regression: 380 passed, 8 expected opt-in live skips and
  85.77% coverage. Repository policy reports 0 findings; artifact/dependency
  locks and status validator pass with 0 errors and 0 warnings.
- `IMP-M3-010…011` adds a privacy-safe Silver DQ relation, explicit critical
  selector, typed candidate quality gate, four stable unknown members and
  order-independent late/correction policy. All existing deduplicated Silver
  bases now call the shared revision-rank macro.
- Focused bundle gate: 42 tests pass with Ruff, strict mypy and dbt 1.12 parse
  `--warn-error`. Selector inspection resolves one critical test and all 11
  Silver candidate models without opening a Snowflake connection.
- Full repository regression after implementation: 389 passed, 8 expected
  opt-in live skips and 86.05% coverage. Repository policy reports 0 findings;
  dependency audit finds no known vulnerability; artifact lock is
  `local-sha256-fc561bc55d692647`; project-image retention dry-run is empty.
- No Docker image was built and no Snowflake, R2, OpenRouter or Chroma call was
  performed. The first live DQ build remains part of a later explicit gate.
- `IMP-M3-012…013` adds five conformed dimensions and four base facts in exact
  `GOLD`, with version-aware member keys, stable unknown rows, half-open SCD
  intervals, as-of fact joins and reusable overlap tests.
- The Gold reconciliation gate compares eligible Silver/Gold row counts and
  additive item/payment amounts. `FACT_REVIEW_BASE` is independent of AI
  coverage and contains no title/comment fields.
- Focused Gold/Silver/dbt gate: 43 tests pass; Ruff, strict mypy and dbt 1.12
  parse `--warn-error` pass. Full repository logic: 397 tests pass, 8 expected
  live skips and 86.11% coverage after refreshing the generated artifact lock.
- No Docker image or provider call was made; the live Gold build remains an
  explicit later Snowflake candidate gate.
- Final artifact for this bundle is `local-sha256-05a6bf64fae55a3c`; the
  repository-scoped image-retention dry-run reports no stale project image.

## Execution log — 2026-08-15 (`IMP-M3-014`)

- `IMP-M3-014` adds ADR-011 and candidate-bound
  `BRIDGE_REVIEW_ITEM_ATTRIBUTION`. One review contributes exactly one allocated
  review count and its original score across eligible item rows; an explicit
  unknown-item fallback prevents loss when no eligible Gold item exists.
- Python allocation fixtures cover single/two/three/zero items, deterministic
  input reorder, exact residual and sanitized invalid/duplicate failures. The
  dbt reconciliation gate covers review-set equality, row grain, policy version,
  weight/count/score equality and unknown-member relationships.
- Focused M3 suite: 59 tests pass. Ruff format/lint, strict mypy and dbt 1.12
  parse `--warn-error` pass; selector inspection resolves the bridge, singular
  gate and all schema tests.
- Full offline regression: 405 tests pass, 8 expected live skips and 86.16%
  coverage. Repository policy and artifact/status gates pass; final artifact is
  `local-sha256-d7ada72f9e6c6bf7`.
- No Docker image was built and no Snowflake, R2, OpenRouter or Chroma call was
  performed. The first live candidate execution remains a later explicit gate.

## Execution log — 2026-08-15 (`IMP-M3-015`)

- Added four candidate-bound monthly marts for order delivery, product review,
  seller performance and customer overview. Item/payment facts are first reduced
  to compatible order or seller-order grains, preventing metric multiplication.
- ADR-012 freezes purchase-month grains, delivery denominator, payment delta and
  lifetime repeat-customer cohort semantics. ADR-011 allocated fields are the
  only review measures used by product/seller marts; raw review text is absent.
- Deterministic Python fixtures cover delivery/value totals, zero denominators,
  fractional review allocation, repeat identity deduplication, unknown exclusion
  and sanitized invalid/conflicting inputs. Singular dbt tests reconcile mart
  counts and amounts to facts/bridge.
- M3 focused suite: 71 tests pass. Ruff, strict mypy, dbt 1.12 parse
  `--warn-error` and the `m3_gold_marts` selector pass offline.
- Full offline regression: 417 tests pass, 8 expected live skips and 86.39%
  coverage. Final artifact is `local-sha256-47fd6d176c1fa12d`.
- No Docker image was built and no Snowflake, R2, OpenRouter or Chroma call was
  performed. Live mart execution remains part of the later candidate build gate.

## Execution log — 2026-08-15 (`IMP-M3-016`)

- Added semantic catalog v1 and four candidate-bound dbt views for order
  delivery, product review, seller performance and customer overview. Consumers
  use stable logical names; server-side release resolution remains reserved for
  `IMP-M3-018/019` and candidate views receive no early serving grants.
- Exact catalog/YAML contracts allow only approved dimensions and measures for
  `ANALYST_ROLE` and `TEXT_TO_SQL_ROLE`. Natural IDs, review text, raw/physical
  identifiers and unapproved roles fail closed. Product/seller order counts are
  labeled nonadditive and AI enrichment remains explicitly unavailable until M4.
- ADR-013 records the serving boundary. Offline dbt 1.12 parse with
  warnings-as-errors and the `m3_semantic` selector pass; focused M3 suite reports
  82 passed. Ruff, strict mypy and schema/catalog negative tests pass.
- Full offline regression: 428 passed, 8 expected live skips and 86.41% coverage.
  Final artifact is `local-sha256-49e72eb94ce0de2a`.
- No Docker image was built and no Snowflake, R2, OpenRouter or Chroma call was
  performed. The candidate execution target is the next offline work item.

## Execution log — 2026-08-16 (`IMP-M3-017`)

- Added a typed Gold candidate planner that converts exactly ten immutable
  Silver candidate relations into a deterministic, distinct Gold candidate.
  Gold output aliases remain in `GOLD`; all direct Silver reads resolve through
  a quoted, explicit `silver_candidate_namespace` in `SILVER`.
- `m3_gold_candidate` selects the complete 18-model Gold graph, reconciliation
  gates and a runtime contract. It rejects placeholder/malformed/equal input and
  output namespaces. In-memory test evidence advances only a complete successful
  selector result; a missing model or failed outcome becomes `FAILED`.
- Focused M3 suite: 90 tests pass. Ruff, strict mypy, dbt 1.12 parse with
  warnings-as-errors and selector inventory pass offline. The live dbt command
  is documented but deferred until an owner-approved Snowflake gate.
- Full offline regression: 436 passed, 8 expected live skips and 86.36% coverage.
  Final artifact is `local-sha256-51468cf4c3fcb0d0`.
- No Docker image was built and no Snowflake, R2, OpenRouter or Chroma call was
  performed. Active-release grants, CAS activation and rollback remain M3-018.

## Execution log — 2026-08-16 (`IMP-M3-018`)

- Added a deterministic immutable release definition that binds one tested
  Silver candidate, one tested Gold candidate, source/batch/process identities,
  semantic catalog version and all 28 candidate physical refs. A definition is
  hash-addressed and cannot carry mutable serving state.
- Added append-only release events, terminal invalidation/revocation guard and a
  one-row versioned CAS pointer fake. Candidate failure cannot create a
  definition; stale or concurrent CAS is denied; activation and rollback retry
  idempotently without emitting an additional transition.
- Migration `007_atomic_release.sql` seeds the v0 pointer and defines owner-
  executed `ACTIVATE_RELEASE_V1`/`ROLLBACK_RELEASE_V1` procedures. Runtime roles
  receive no direct pointer update privilege. ADR-014 records this contract.
- Focused release/candidate/audit suite: 30 tests pass; full M3 focused suite:
  97 tests pass. Ruff, strict mypy and dbt parse with warnings-as-errors pass
  offline. Live migration/procedure smoke remains an explicit owner-approved
  Snowflake gate.
- Final offline regression on 2026-08-16: 443 tests pass, 8 expected opt-in
  live tests skip and coverage is 86.28%. Repository policy, dependency lock,
  artifact validation, project-image retention dry-run and the workflow status
  validator pass; final artifact is `local-sha256-9e3e57dc893d4279`.
- Executed focused command: `uv run pytest tests/test_m3_processing_migration.py
  tests/test_m3_dbt_sources.py tests/test_m3_silver_models.py
  tests/test_m3_silver_relational_models.py tests/test_m3_quality_revisions.py
  tests/test_m3_gold_models.py tests/test_m3_gold_marts.py
  tests/test_m3_semantic_views.py tests/test_m3_gold_candidate.py
  tests/test_m3_releases.py tests/test_dbt.py -q -p no:cacheprovider --basetemp
  .tmp/pytest-m3-phase-018` returned `97 passed`.
- Executed full command: `uv run pytest -q -p no:cacheprovider --basetemp
  .tmp/pytest-full-m3-018 --cov=reviewlens --cov-report=term-missing` returned
  `443 passed, 8 skipped`.
- No Docker image was built and no Snowflake, R2, OpenRouter or Chroma call was
  performed. M3-019 must pin request reads to this release before any serving
  object is exposed.

## Execution log — 2026-08-16 (`IMP-M3-019`)

- Added `ActiveReleaseResolver`: it snapshots `ACTIVE_DATA_RELEASE` once and
  resolves only allowlisted catalog logical names to the exact Gold refs of that
  immutable definition. Callers cannot provide a schema, candidate namespace,
  physical relation or release ID.
- Each `ReleaseRequestPin` retains the full private immutable release definition
  (all Silver and Gold refs), release/definition identity, pointer version,
  activation event and semantic contract version; only Gold semantic refs are
  resolved for consumers. The release definition now also enforces exactly 28
  unique logical refs in the namespace of its own Silver or Gold candidate.
- Offline request-pinning tests cover valid dashboard resolution, no active
  pointer, raw/physical/lowercase/duplicate inputs, non-enum caller arguments,
  cross-candidate refs and a 16-request activation race with no mixed release.
- Focused resolver/release/semantic suite: 28 tests pass; full M3 focused suite:
  107 tests pass. Ruff, strict mypy and dbt parse with warnings-as-errors pass
  offline. Live migration/procedure smoke remains an explicit owner-approved
  Snowflake gate.
- Final offline regression on 2026-08-16: 453 tests pass, 8 expected opt-in
  live tests skip and coverage is 86.34%. Repository policy, dependency lock,
  artifact validation, project-image retention dry-run and the workflow status
  validator pass; final artifact is `local-sha256-1cee93f22baa9ecc`.
- Executed focused command: `uv run pytest tests/test_m3_processing_migration.py
  tests/test_m3_dbt_sources.py tests/test_m3_silver_models.py
  tests/test_m3_silver_relational_models.py tests/test_m3_quality_revisions.py
  tests/test_m3_gold_models.py tests/test_m3_gold_marts.py
  tests/test_m3_semantic_views.py tests/test_m3_gold_candidate.py
  tests/test_m3_releases.py tests/test_m3_release_resolver.py tests/test_dbt.py
  -q -p no:cacheprovider --basetemp .tmp/pytest-m3-phase-019` returned
  `107 passed`.
- Executed full command: `uv run pytest -q -p no:cacheprovider --basetemp
  .tmp/pytest-full-m3-019 --cov=reviewlens --cov-report=term-missing` returned
  `453 passed, 8 skipped`.
- No Docker image was built and no Snowflake, R2, OpenRouter or Chroma call was
  performed. `IMP-M3-020` is the remaining M3 work item.
