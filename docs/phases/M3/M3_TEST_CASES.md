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
| TC-M3-014 | Silver customer | Duplicate/customer geography/privacy fixtures | One customer row and minimized repeat key | `PENDING` | Await IMP-M3-004 |
| TC-M3-015 | Silver geography | ZIP occurrences and malformed coordinates | Deterministic centroid; no join multiplication | `PENDING` | Await IMP-M3-005 |
| TC-M3-016 | Silver order | Status/time/scope edge fixtures | Declared analysis scope and intervals deterministic | `PENDING` | Await IMP-M3-006 |
| TC-M3-017 | Silver item/payment | Composite keys, amounts and reconciliation | Keys/ranges/counts pass | `PENDING` | Await IMP-M3-007 |
| TC-M3-018 | Silver product/seller | Translation, corrected length and location | Contracted columns and unknown fallback pass | `PENDING` | Await IMP-M3-008 |
| TC-M3-019 | Silver review/DLP | Empty, orphan, duplicate and restricted text | Base score retained; AI eligibility minimized | `PENDING` | Await IMP-M3-009 |
| TC-M3-020 | DQ gate | Critical/warn/quarantine fixtures | Critical failure blocks candidate publication | `PENDING` | Await IMP-M3-010 |
| TC-M3-021 | Late/unknown | Reordered, late and orphan inputs | Deterministic unknown/correction policy | `PENDING` | Await IMP-M3-011 |
| TC-M3-022 | Dimensions/facts | Declared grains and relationships | No unexpected multiplication or loss | `PENDING` | Await IMP-M3-012/013 |
| TC-M3-023 | Attribution | Multi-item order review metrics | Allocation labels present; no silent double count | `PENDING` | Await IMP-M3-014 |
| TC-M3-024 | Marts | Metric dictionary fixture | Golden outputs match declared grain | `PENDING` | Await IMP-M3-015/016 |
| TC-M3-025 | Candidate failure | Silver/Gold candidate fails a gate | Active serving pointer remains unchanged | `PENDING` | Await IMP-M3-017/018 |
| TC-M3-026 | CAS/replay | Concurrent activation, rollback and replay | One CAS winner; rollback uses immutable release | `PENDING` | Await IMP-M3-018 |
| TC-M3-027 | Request pinning | Concurrent requests during activation | Each request uses one complete release | `PENDING` | Await IMP-M3-019 |
| TC-M3-028 | Equivalence/cost | Full versus incremental two-run drill | Row/hash equality, bounded X-Small usage and suspend | `PENDING` | Await IMP-M3-020; owner opt-in required |
| TC-M3-029 | Repository policy | Scan Git-visible files | No raw Olist, review text, secret or generated dbt target | `PASS` | `reviewlens-policy --root .`: 0 findings; artifact metadata and dependency lock pass |
| TC-M3-030 | Status | Validate phase artifacts and plan synchronization | Zero errors/warnings | `PASS` | Workflow validator: M3 3/20 done, 15/30 pass, 0 errors and 0 warnings |

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
