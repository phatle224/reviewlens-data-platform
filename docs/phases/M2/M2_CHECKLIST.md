# M2 Checklist — Olist ingestion, R2 and immutable Bronze

| Thuộc tính | Giá trị |
|---|---|
| Phase status | `COMPLETE` |
| Completed | 18/18 work items |
| Partial | 0/18 work items |
| Blocked | 0/18 work items |
| Not started | 0/18 work items |
| Last updated | 2026-08-14 |

## Checklist theo implementation plan

| Work item | Status | Outcome cần đạt | Evidence / việc còn lại |
|---|---|---|---|
| IMP-M2-001 | `DONE` | Machine-readable contract cho 9 filename/header/type/key | `olist_source_contract.json` + frozen Pydantic models; exact nine datasets, source-spelling headers, logical types, nullability, identity semantics và privacy classes; weakened/unknown/duplicate/invalid-key fixtures fail closed |
| IMP-M2-002 | `DONE` | Discover complete local snapshot và completion manifest | Exact directory/manifest set, symlink boundary, bounded manifest/header reads, streaming SHA-256 and size/header verification; missing/extra/partial/duplicate/integrity/encoding failures use stable row-safe codes before provider access |
| IMP-M2-003 | `DONE` | Canonical manifest và `source_release_id` conflict detection | Path-free sorted manifest covers required PRD metadata; ID hashes sorted filename/bytes/SHA only; path/order/runtime changes replay, changed bytes create candidate, same-ID stable metadata drift raises `SOURCE_RELEASE_CONFLICT` |
| IMP-M2-004 | `DONE` | Stable source object, batch, run, attempt và record IDs | Namespaced SHA-256 IDs use canonical versioned inputs only; two paths/replays are identical, 1,000 record positions unique, contract change produces a new run and retry changes only `attempt_id`; invalid inputs fail closed without echo |
| IMP-M2-005 | `DONE` | Bounded streaming CSV parser với row/byte offsets | Binary chunk scanner supports UTF-8 BOM, LF/CRLF, multiline/escaped quotes and exact half-open offsets; stable row-safe errors cover encoding, malformed shape, field count and record cap; 100,000-row benchmark peaks below 2 MB |
| IMP-M2-006 | `DONE` | Field/file validation và stable error taxonomy | Versioned typed validation covers required/null, integer/finite decimal/timestamp, score/geolocation/non-negative ranges, status/payment allowlists and ZIP/state formats; nine synthetic files reconcile, unique keys/declared rows fail closed while geolocation occurrence duplicates remain valid |
| IMP-M2-007 | `DONE` | Canonical record hash và replay detection | Contract-ordered typed canonical JSON excludes row/runtime position; map reorder and equivalent decimals are stable, business changes differ, invalid/untyped input is denied; tracker explicitly distinguishes `NEW`/`REPLAY`/candidate `DUPLICATE` |
| IMP-M2-008 | `DONE` | License/privacy preflight trước real upload | Package-owned approved snapshot + deterministic six-gate decision verifies Olist mode, private R2, immutable source metadata, CC BY-NC-SA, attribution/change/no-endorsement notices and versioned privacy/DLP evidence; all missing-gate variants deny without row/path/secret exposure |
| IMP-M2-009 | `DONE` | Immutable original CSV upload và checksum verify | R2 adapter streams files and download SHA-256 with conditional `If-None-Match: *`; service writes nine release-addressed originals then manifest commit marker, resumes partial uploads, denies different bytes/metadata and supports stable replay. Real archive preflight reconciled 1,550,922 rows; initial private R2 upload and forced 10/10 replay live gates pass |
| IMP-M2-010 | `DONE` | Typed raw/quarantine Parquet partitions và manifests | Bounded PyArrow writers preserve string/integer/decimal/timestamp, Unicode and multiline text; create-only partition commit, content/schema hashes and metadata-only sidecar manifests pass replay/conflict tests |
| IMP-M2-011 | `DONE` | Ingestion/file/source audit repositories và state transitions | Typed repository port + deterministic append-only fake enforce exact state order, terminal failure, active lease exclusion/takeover, retry attempt identity, source/file count reconciliation and idempotency conflict detection |
| IMP-M2-012 | `DONE` | Row/file quarantine và replay selector | Streaming processor emits only `NEW` rows to raw; committed `REPLAY` has zero new effect; candidate `DUPLICATE`, validation errors and parser/file failures receive stable code, source row/byte/raw reference and reconcile exactly |
| IMP-M2-013 | `DONE` | Nine immutable Bronze DDLs/stages/grants | `005_bronze.sql` maps all nine typed contracts and canonical lineage to additive tables, a Parquet format and metadata-only audit ledger; migration replay passes live and `INGEST_ROLE` is insert-only on Bronze with live SELECT denial |
| IMP-M2-014 | `DONE` | Airflow-managed `COPY INTO` và load history | Exact-file allowlisted COPY service records Snowflake query IDs/counts in an append-only ledger; `FORCE=FALSE`, `PURGE=FALSE`, fail-closed result parsing and live `LOAD_SKIPPED` replay have zero duplicate committed effect; DAG wiring remains IMP-M2-016 |
| IMP-M2-015 | `DONE` | Source→R2→Bronze physical reconciliation | Deterministic nine-dataset reconciliation covers source dispositions, local/R2 bytes and SHA-256, COPY rows, Bronze batch rows and distinct record hashes; synthetic R2→Bronze live smoke reconciles 1 row/1 hash and cleans up |
| IMP-M2-016 | `DONE` | Implement three ingestion DAG tasks | Typed metadata-only XCom contracts wire `validate_source → upload_to_r2 → copy_to_bronze`; runtime is explicit-opt-in, provider-free at DAG import, immutable/replay-safe and container-smoked from the locked Airflow image |
| IMP-M2-017 | `DONE` | Late/change/backfill/concurrent same-key handling | Deterministic synthetic scenarios block incomplete/ambiguous source, classify changed bytes as a new release, preserve lineage while changing backfill attempt ID, serialize same-key lease claims and recover from an injected upload failure before COPY |
| IMP-M2-018 | `DONE` | Metrics, alerts, replay/quarantine runbook | Bounded metadata-only Prometheus payload and atomic stable-code alert artifact cover reconciliation/quarantine/task-error/warehouse cleanup; private run, replay, backfill, recovery and shutdown drill is documented and contract-tested |

## Exit gate

M2 is `COMPLETE`. Owner-approved run `m2_exit_normal_20260814_0122` and immutable
replay `m2_exit_clean_replay_20260814_0153` both finished successfully. All nine
datasets reconcile 1,550,922 source rows into 1,289,091 accepted/Bronze rows plus
261,831 deterministic exact duplicates, with zero invalid quarantine and zero parse
failures. Replay reports 19 verified/skipped objects, zero duplicate committed
effect, an empty alert list, reconciliation `1` and warehouse-suspended `1`.

Raw data remains outside Git and private provider artifacts remain under the
approved lifecycle policy. The local Airflow volume retains metadata-only run
evidence; provider resources were left private and Snowflake warehouse cleanup was
confirmed.
