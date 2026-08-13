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
| TC-M2-011 | IDs | Source object/batch/run/attempt/record identifiers | Deterministic/unique as declared | `PASS` | Namespaced canonical SHA-256 chain is path/runtime-free; replay stable, retry isolated to attempt, contract/run and 1,000 record positions collision-distinct; invalid values sanitized |
| TC-M2-012 | Parser | UTF-8 CSV streaming, multiline quotes and offsets | Bounded memory and exact positions | `PASS` | UTF-8 BOM, 1-byte chunk escaped quotes, multiline CRLF/LF and original-byte slices pass; malformed/encoding/shape/size failures stable; 100,000 rows peak below 2 MB |
| TC-M2-013 | Validation | Required/type/range/status/timestamp failures | Stable row/file error taxonomy | `PASS` | Nine synthetic files pass/reconcile; 10 field failure classes, nullable conversion, unique-key duplicate, row-count drift and occurrence-key semantics verified with `olist-validation-v1` |
| TC-M2-014 | Record hash | Runtime metadata/reorder/replay cases | Canonical hash stable; duplicate explicit | `PASS` | Contract order and typed normalization make map order/position/decimal formatting stable; business change differs; invalid shape/type sanitized; tracker returns `NEW`, `REPLAY`, `DUPLICATE` |
| TC-M2-015 | Preflight | License, attribution, privacy and source metadata | Real upload denied until every gate passes | `PASS` | Approved nine-file metadata and six-gate authorization pass; synthetic mode, public R2, source drift, incomplete attribution or privacy evidence deny independently and expose no source/path/secret |
| TC-M2-016 | R2 live | Immutable upload/download/replay/conflict | Hash matches; overwrite denied; intended archive retained under lifecycle | `PASS` | Offline create-only/resume/conflict suite pass; approved archive local preflight 9 files/1,550,922 rows/0 rejected; private R2 initial upload pass and forced replay confirms 0 uploads + 10 verified replays, anonymous/account-list denial pass |
| TC-M2-017 | Parquet | Raw/quarantine round trip | Types/Unicode/newlines/partitions preserved | `PASS` | Typed string/integer/decimal/timestamp and UTC lineage round-trip; Unicode/multiline review text preserved privately; raw/error partitions, metadata-only manifests, replay and conflicting-artifact denial verified |
| TC-M2-018 | Audit | Legal/illegal ingestion state transitions | Append-only, idempotent and leased | `PASS` | Legal five-state path, skip/post-terminal denial, same-state idempotency/conflict, active-owner exclusion, expired-lease retry and file-count ledger reconciliation pass |
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

### Stable lineage IDs and bounded CSV parser bundle

- Added versioned canonical identity functions for source object, ingestion batch,
  dataset run, attempt and physical record. Runtime timestamps and paths are not
  accepted as identity input; attempts use a positive retry ordinal.
- Added a binary chunk parser whose logical data rows start at source row 2. Byte
  ranges are half-open over original bytes and exclude only the outer LF/CRLF,
  while quoted embedded newlines remain part of the record.
- Focused command: `pytest tests/test_ingestion_identity.py tests/test_ingestion_csv_stream.py tests/test_ingestion_source.py tests/test_synthetic.py -q -p no:cacheprovider` → 55 pass.
- Full gate: Ruff format/lint and Airflow rules pass, mypy strict pass, pytest 241
  pass + 6 expected live skips with 89.72% branch-aware coverage; lock check,
  repository policy and immutable artifact check pass.
- No `.env`/credential was read, no real Olist row/provider was accessed and no
  R2/Snowflake/OpenRouter/Chroma call or service cost occurred.

## Execution log — 2026-08-13

### Validation, record identity and upload-preflight bundle

- Added streaming typed validation with a versioned profile and stable row/file
  taxonomy. Reports contain counts/codes only; raw values remain outside errors.
- Added SHA-256 record hashes over typed business columns in contract order.
  Lineage/runtime metadata is structurally excluded, while an explicit tracker
  separates committed replay from duplicate rows in the current candidate.
- Added package-owned approved snapshot metadata and a deterministic upload
  authorization. It checks Olist data mode, private R2, exact content identity,
  license obligations, attribution/change/no-endorsement text and versioned
  privacy evidence; it does not read credentials, providers or source rows.
- Focused command: `pytest tests/test_ingestion_identity.py tests/test_ingestion_csv_stream.py tests/test_ingestion_source.py tests/test_ingestion_validation.py tests/test_ingestion_records.py tests/test_ingestion_preflight.py tests/test_synthetic.py -q -p no:cacheprovider` → 83 pass.
- Full gate: Ruff format/lint and Airflow rules pass, mypy strict pass, pytest 269
  pass + 6 expected live skips with 90.13% branch-aware coverage; lock, policy,
  artifact and status checks pass.
- No `.env`/credential/raw Olist row was read and no R2/Snowflake/OpenRouter/Chroma
  call or service cost occurred. The positive preflight uses approved metadata
  fixtures; it is not evidence that a real upload occurred.

### Immutable private R2 source archive

- Added a metadata-only completion-marker generator. It verifies all approved
  sizes, headers and streamed SHA-256 values before atomically writing the ignored
  `archive/manifest.json`; changed bytes or marker drift fail closed.
- Extended the R2 adapter with conditional file/bytes create, streaming download
  SHA-256 and explicit `412` conflict handling. The upload service verifies each
  existing object, never overwrites, resumes partial work and writes the canonical
  manifest last as the release commit marker.
- Offline focused command: `pytest tests/test_r2.py tests/test_ingestion_preflight.py tests/test_ingestion_source_upload.py -q -p no:cacheprovider` → 21 pass. Fake integration covers 10-object upload/replay, one-object resume, source conflict, manifest conflict and denied preflight with zero writes.
- Real local preflight: exact 9 approved files, 1,550,922 logical rows, 0 rejected,
  0 duplicate unique identities; source release is
  `olist_5bf5c26261b616567311d761c26f7ef83da835b82c1bbd3f4969d90a1b95682d`.
- Owner-approved private R2 gate: initial immutable upload pass in 125.22s; normal
  rerun pass in 82.10s; forced replay pass in 86.95s with exactly 0 uploads and
  10 verified replays. Download hashes, scoped account-list denial and anonymous
  access denial pass. Intended source archive remains in R2; no cleanup applies.
- Full offline gate: Ruff format/lint and Airflow rules pass, mypy strict pass,
  pytest 277 pass + 7 expected live skips with 89.23% branch-aware coverage;
  lock, repository policy and immutable artifact checks pass.
- No source row, credential or absolute local path was emitted or committed.
  Snowflake, OpenRouter and Chroma were not called. R2 now stores approximately
  126.19 MB of source CSV bytes plus one small metadata manifest.

### Typed Parquet, audit state machine and quarantine/replay selector

- Added `pyarrow` as a direct locked runtime dependency and bounded row-group
  writers for typed raw/quarantine Parquet. Private artifacts use the PRD R2 key
  layout; create-only commit denies different bytes, while sidecar manifests
  contain only object key, row/byte count and content/schema hashes.
- Added an append-only ingestion audit repository contract and deterministic
  fake. It enforces `DISCOVERED → VALIDATED → UPLOADED → BRONZE_LOADED →
  RECONCILED`, terminal failure, lease exclusion/expiry takeover, new retry
  attempts and idempotent source-file reconciliation events.
- Added the streaming selector/materializer. `NEW` records enter raw Parquet;
  committed `REPLAY` records create no new row; candidate `DUPLICATE`, typed
  validation errors and parser/file failures enter error-code partitions with
  stable source position/reference. Every observed logical row has one outcome.
- Focused command: `pytest tests/test_ingestion_parquet_processing.py
  tests/test_ingestion_audit.py -q -p no:cacheprovider` → 8 pass. Ingestion/R2
  regression command → 103 pass.
- Full offline gate: Ruff format/lint and Airflow rules pass, mypy strict pass,
  pytest 285 pass + 7 expected live skips with 88.36% branch-aware coverage;
  locked dependency sync and immutable artifact metadata pass.
- Tests use generated synthetic rows and temporary ignored outputs. No real
  `archive/` row was processed into Parquet, no R2/Snowflake/OpenRouter/Chroma
  call occurred and no managed-service cost was incurred.
