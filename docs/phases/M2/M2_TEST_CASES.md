# M2 Test Cases and Results

## Test matrix

| ID | Loại | Scenario | Expected result | Status | Evidence |
|---|---|---|---|---|---|
| TC-M2-001 | Contract | Nine Olist datasets have exact filename/header/type/key metadata | Versioned contract loads with 9 unique required datasets | `PASS` | Exact file/dataset sets, types, nullability, keys, occurrence semantics, restricted review class and source `*_lenght` headers verified |
| TC-M2-002 | Contract negative | Unknown fields/types, duplicate names and invalid keys | Contract fails closed with stable code | `PASS` | 7 weakened/malformed mutations return only `SOURCE_CONTRACT_INVALID`; seeded value absent |
| TC-M2-003 | Discovery | Complete synthetic directory + completion manifest | Exact nine-file snapshot discovered deterministically | `PASS` | Generated snapshot and reversed manifest order both discover nine files in canonical order |
| TC-M2-004 | Discovery negative | Missing/extra/partial/duplicate manifest entries | Candidate blocked with filename-safe error | `PASS` | Missing dir/marker/file, extra entry, duplicate and incomplete manifest cases return stable codes |
| TC-M2-005 | Integrity negative | Header/size/SHA mismatch, unsafe entry or invalid manifest | Candidate blocked before any provider call | `PASS` | Non-directory root, malformed/wrong-version manifest, size, same-size checksum, header and invalid UTF-8 tests fail before provider access |
| TC-M2-006 | Manifest | Canonical manifest contains required PRD fields | Stable, sorted, path-free artifact | `PASS` | Nine sorted file records include dataset/required/bytes/hash/header/rows/class/license; JSON deterministic and path-free |
| TC-M2-007 | Identity | Reorder/path/timestamp/snapshot-date changes | `source_release_id` unchanged | `PASS` | Two generated directories, reversed file order and changed runtime dates produce identical 64-hex content ID |
| TC-M2-008 | Replay/change | Same content versus same filename/new bytes | Replay versus new candidate deterministic | `PASS` | Same bytes classify `REPLAY`; same filename with refreshed different bytes classifies `NEW_CANDIDATE` |
| TC-M2-009 | Conflict | Same release ID with incompatible stable metadata | `SOURCE_RELEASE_CONFLICT` | `PASS` | Manifest-version drift under same ID fails closed; runtime-only date/time drift remains replay |
| TC-M2-010 | Privacy | Errors/manifests exclude row text, absolute paths and credentials | Leak canaries absent | `PASS` | Paths excluded from model dumps/canonical JSON; invalid-header canary and absolute temp path absent from errors |
| TC-M2-011 | IDs | Source object/batch/run/attempt/record identifiers | Deterministic/unique as declared | `PENDING` | Planned IMP-M2-004 |
| TC-M2-012 | Parser | UTF-8 CSV streaming, multiline quotes and offsets | Bounded memory and exact positions | `PENDING` | Planned IMP-M2-005 |
| TC-M2-013 | Validation | Required/type/range/status/timestamp failures | Stable row/file error taxonomy | `PENDING` | Planned IMP-M2-006 |
| TC-M2-014 | Record hash | Runtime metadata/reorder/replay cases | Canonical hash stable; duplicate explicit | `PENDING` | Planned IMP-M2-007 |
| TC-M2-015 | Preflight | License, attribution, privacy and source metadata | Real upload denied until every gate passes | `PENDING` | Planned IMP-M2-008 |
| TC-M2-016 | R2 live | Immutable upload/download/replay/conflict | Hash matches; overwrite denied; cleanup bounded | `PENDING` | Planned IMP-M2-009; owner-operated synthetic-first |
| TC-M2-017 | Parquet | Raw/quarantine round trip | Types/Unicode/newlines/partitions preserved | `PENDING` | Planned IMP-M2-010/012 |
| TC-M2-018 | Audit | Legal/illegal ingestion state transitions | Append-only, idempotent and leased | `PENDING` | Planned IMP-M2-011 |
| TC-M2-019 | Bronze contract | Nine tables, lineage metadata and immutable grants | DDL/RBAC/idempotency pass | `PENDING` | Planned IMP-M2-013 |
| TC-M2-020 | COPY integration | Airflow load history and replay | No duplicate committed effect | `PENDING` | Planned IMP-M2-014/016 |
| TC-M2-021 | Reconciliation | Source→R2→Bronze rows/bytes/checksums | Zero unexplained loss | `PENDING` | Planned IMP-M2-015 |
| TC-M2-022 | Failure/concurrency | Retry/backfill/late/change/same-key race | Active state remains consistent | `PENDING` | Planned IMP-M2-017 |
| TC-M2-023 | Operations | Metrics/alerts/replay/quarantine drill | Expected observability and recovery evidence | `PENDING` | Planned IMP-M2-018 |
| TC-M2-024 | Security | Repository/raw-data/secret/provider boundary | No raw source or secret in Git/output | `PASS` | `reviewlens-policy --root .`: 0 findings; ingestion source module has no provider/environment import |
| TC-M2-025 | Status | Phase artifacts and implementation plan synchronize | Validator has 0 errors/warnings | `PASS` | Status validator: M2 has 18 planned work items and 25 synchronized tests; 0 errors/warnings |

## Execution log — 2026-08-12

- M2 artifacts initialized after M1 closed 20/20 work items and 41/41 tests.
- Active bundle is `IMP-M2-001…003`; it uses generated synthetic Olist files only.
- No raw Olist read/upload, provider call, warehouse resume or paid AI call is authorized in this bundle.

### Contract, discovery and canonical manifest bundle

- Added package-owned `olist_source_contract.json` and strict typed models. The synthetic generator now derives filenames/headers/version metadata from this single source of truth, preventing contract drift.
- Discovery accepts exactly nine regular CSVs plus `manifest.json`, validates manifest versions/set/duplicates, file size, streaming SHA-256 and bounded UTF-8 header. Errors expose stable code and known filename only—never row text or absolute path.
- Canonical manifest serializes only source/file metadata. `source_release_id` is `olist_` plus SHA-256 over sorted filename/bytes/hash entries; directory, ordering, snapshot date and creation time are excluded.
- Focused command: `pytest tests/test_ingestion_source.py tests/test_synthetic.py -q -p no:cacheprovider` → 37 pass.
- Full gate: Ruff format/lint pass, mypy strict pass, pytest 223 pass + 6 expected live skips with 89.31% branch-aware coverage; lock check, repository policy, immutable artifact and status checks pass.
- No `.env`/credential was read, no real source row was accessed, no R2/Snowflake/OpenRouter/Chroma call occurred and no service cost was incurred.
