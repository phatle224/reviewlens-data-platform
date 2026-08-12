# M2 Checklist — Olist ingestion, R2 and immutable Bronze

| Thuộc tính | Giá trị |
|---|---|
| Phase status | `IN_PROGRESS` |
| Completed | 8/18 work items |
| Partial | 0/18 work items |
| Blocked | 0/18 work items |
| Not started | 10/18 work items |
| Last updated | 2026-08-13 |

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
| IMP-M2-009 | `NOT_STARTED` | Immutable original CSV upload và checksum verify | Create-only/replay/conflict/download-hash tests |
| IMP-M2-010 | `NOT_STARTED` | Typed raw/quarantine Parquet partitions và manifests | Unicode/newline/type/partition round-trip tests |
| IMP-M2-011 | `NOT_STARTED` | Ingestion/file/source audit repositories và state transitions | Lease/idempotency/illegal-transition tests |
| IMP-M2-012 | `NOT_STARTED` | Row/file quarantine và replay selector | Accepted+rejected+parse-failed reconciliation |
| IMP-M2-013 | `NOT_STARTED` | Nine immutable Bronze DDLs/stages/grants | Schema/metadata/RBAC/idempotency tests |
| IMP-M2-014 | `NOT_STARTED` | Airflow-managed `COPY INTO` và load history | Query-ID/replay/copy/cleanup tests |
| IMP-M2-015 | `NOT_STARTED` | Source→R2→Bronze physical reconciliation | Rows/bytes/checksums zero unexplained loss |
| IMP-M2-016 | `NOT_STARTED` | Implement three ingestion DAG tasks | Retry/resume/idempotency/import-side-effect tests |
| IMP-M2-017 | `NOT_STARTED` | Late/change/backfill/concurrent same-key handling | Scenario and race/failure-injection suite |
| IMP-M2-018 | `NOT_STARTED` | Metrics, alerts, replay/quarantine runbook | Operational drill and evidence |

## Exit gate

M2 chỉ `COMPLETE` khi chín source/Bronze counts reconcile, mọi invalid row được
giải thích, replay không tạo duplicate committed effect, raw data không Git-visible,
live resources được cleanup và warehouse suspend. Chưa chạy test phải giữ
`PENDING`/`NOT_STARTED`, không giả lập `PASS`.
