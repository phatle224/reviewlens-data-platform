# M0 Test Cases and Results

## Test matrix

| ID | Type | Scenario | Expected result | Status | Evidence |
|---|---|---|---|---|---|
| TC-M0-001 | Artifact | Phase documentation exists | Checklist/test/source artifacts resolve | `PASS` | M0 files present |
| TC-M0-002 | Integrity | Local source snapshot fingerprint | Nine SHA-256 values and sizes recorded without row content | `PASS` | [Manifest](../../data/OLIST_SOURCE_MANIFEST.md) |
| TC-M0-003 | Contract | Physical inventory | Exactly nine expected CSVs identified | `PASS` | [Source profile](./M0_SOURCE_PROFILE.md) |
| TC-M0-004 | Contract | Required datasets and headers | All nine required; exact headers versioned | `PASS` | Manifest + fixture contract |
| TC-M0-005 | Semantics | Replay/changed/missing snapshot | Same hash skips; changed hash creates candidate; missing file fails | `PASS` | ADR-005 review |
| TC-M0-006 | Product | Order analysis-scope cases | Delivered in scope; cancelled operational; unknown/quarantine explicit | `PASS` | Product baseline |
| TC-M0-007 | Data model | Snapshot history/correction/deletion | Deterministic history and controlled tombstone | `PASS` | ADR-007 review |
| TC-M0-008 | Time | Source timestamps lack offsets | Raw NTZ preserved; no silent UTC assumption | `PASS` | ADR-007 review |
| TC-M0-009 | Architecture | Frozen stack consistency | R2/Snowflake/OpenRouter/ChromaDB only | `PASS` | ADR/static review |
| TC-M0-010 | Storage | R2/Snowflake stage contract | Private `s3compat://`; manual Airflow batch | `PASS` | ADR-001/002 contract |
| TC-M0-011 | AI | Model/version/evaluation plan | Pinned candidates, golden/security gates and budget | `PASS` | AI evaluation plan |
| TC-M0-012 | Vector | Chroma persistence/rebuild/version | Candidate and active collection isolation | `PASS` | ADR-004 |
| TC-M0-013 | Security | Local auth/public exposure boundary | Loopback/private default; public launch needs new ADR | `PASS` | ADR-006 |
| TC-M0-014 | Release | Candidate failure/concurrent activation | Active release unchanged; CAS/rollback defined | `PASS` | ADR-005 |
| TC-M0-015 | Capacity | Portfolio cost envelope | Hard/degrade actions defined | `PASS` | SLO/budget baseline |
| TC-M0-016 | Threat | Injection/SQL/data/secret/license risks | Mandatory controls and negative suites defined | `PASS` | Security baseline |
| TC-M0-017 | Compliance | Olist license supports intended portfolio use | Attribution, NC, SA and change notice enforced | `PASS` | ADR-008 + attribution |
| TC-M0-018 | Privacy | Real review external-processing boundary | DLP/minimized projection required; public raw denied | `PASS` | Security baseline |
| TC-M0-019 | Snowflake live | Account and warehouse smoke | Runtime evidence belongs to M1 | `DEFERRED` | Executed under M1 TC-M1-016 |
| TC-M0-020 | R2 live | Private bucket round trip | Runtime evidence belongs to M1 | `DEFERRED` | Executed under M1 TC-M1-014 |
| TC-M0-021 | OpenRouter live | Catalog/key smoke without real text | Runtime evidence belongs to M1 | `DEFERRED` | Planned under IMP-M1-011 |

## Result

18 `PASS`, 3 `DEFERRED`, 0 `FAIL`. M0 is complete because deferred cases are
provider-runtime checks owned by M1 and do not weaken the accepted decisions.
