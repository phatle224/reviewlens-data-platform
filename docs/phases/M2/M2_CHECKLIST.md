# M2 Checklist — Olist ingestion, R2 and immutable Bronze

| Thuộc tính | Giá trị |
|---|---|
| Phase status | `IN_PROGRESS` |
| Completed | 3/18 work items |
| Partial | 0/18 work items |
| Blocked | 0/18 work items |
| Not started | 15/18 work items |
| Last updated | 2026-08-12 |

## Checklist theo implementation plan

| Work item | Status | Outcome cần đạt | Evidence / việc còn lại |
|---|---|---|---|
| IMP-M2-001 | `DONE` | Machine-readable contract cho 9 filename/header/type/key | `olist_source_contract.json` + frozen Pydantic models; exact nine datasets, source-spelling headers, logical types, nullability, identity semantics và privacy classes; weakened/unknown/duplicate/invalid-key fixtures fail closed |
| IMP-M2-002 | `DONE` | Discover complete local snapshot và completion manifest | Exact directory/manifest set, symlink boundary, bounded manifest/header reads, streaming SHA-256 and size/header verification; missing/extra/partial/duplicate/integrity/encoding failures use stable row-safe codes before provider access |
| IMP-M2-003 | `DONE` | Canonical manifest và `source_release_id` conflict detection | Path-free sorted manifest covers required PRD metadata; ID hashes sorted filename/bytes/SHA only; path/order/runtime changes replay, changed bytes create candidate, same-ID stable metadata drift raises `SOURCE_RELEASE_CONFLICT` |
| IMP-M2-004 | `NOT_STARTED` | Stable source object, batch, run, attempt và record IDs | Determinism/uniqueness/property tests |
| IMP-M2-005 | `NOT_STARTED` | Bounded streaming CSV parser với row/byte offsets | Multiline/encoding/malformed/large-file memory tests |
| IMP-M2-006 | `NOT_STARTED` | Field/file validation và stable error taxonomy | Required/type/range/status/timestamp tests |
| IMP-M2-007 | `NOT_STARTED` | Canonical record hash và replay detection | Metadata exclusion, reorder và duplicate tests |
| IMP-M2-008 | `NOT_STARTED` | License/privacy preflight trước real upload | Attribution/NC/SA/DLP/source-manifest gate |
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
