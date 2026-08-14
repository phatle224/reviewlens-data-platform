# M3 Checklist — Conformed Silver, Gold and atomic release

| Attribute | Value |
|---|---|
| Phase status | `IN_PROGRESS` |
| Completed | 3/20 work items |
| Partial | 0/20 work items |
| Blocked | 0/20 work items |
| Not started | 17/20 work items |
| Last updated | 2026-08-14 |

## Implementation-plan checklist

| Work item | Status | Required outcome | Evidence / remaining work |
|---|---|---|---|
| IMP-M3-001 | `DONE` | Processing-run/input and candidate physical-reference ledger | Deterministic SHA-256 run/input/candidate identities, ordered 1:N lineage and replay-safe in-memory registry; additive `006_processing_candidates.sql` creates three secret-free append-only ledgers with exact grants; migration replay and contract tests pass |
| IMP-M3-002 | `DONE` | Versioned Silver candidate build/cleanup strategy | Versioned candidate IDs produce isolated physical object namespaces inside least-privilege `SILVER`/`GOLD` schemas; thread-safe lease tests allow one concurrent owner and cleanup only terminal failed/unreferenced candidates |
| IMP-M3-003 | `DONE` | dbt Bronze sources, freshness, contracts and docs | All nine Bronze relations declare exact typed business/lineage columns, canonical physical-grain tests, bounded freshness, privacy/license metadata and `m3_bronze_contract`; offline dbt parse passes with warnings-as-errors |
| IMP-M3-004 | `NOT_STARTED` | `SIL_CUSTOMER`, minimized repeat-customer key and geography | Await M3-002/003 |
| IMP-M3-005 | `NOT_STARTED` | Deterministic `SIL_GEOLOCATION_ZIP` centroid/quality model | Await M3-002/003 |
| IMP-M3-006 | `NOT_STARTED` | `SIL_ORDER` status/time/scope/delivery flags | Await M3-002/003 and M0 scope rules |
| IMP-M3-007 | `NOT_STARTED` | `SIL_ORDER_ITEM` and `SIL_ORDER_PAYMENT` | Await M3-006 |
| IMP-M3-008 | `NOT_STARTED` | `SIL_PRODUCT`, translation and `SIL_SELLER` | Await M3-005 |
| IMP-M3-009 | `NOT_STARTED` | `SIL_ORDER_REVIEW` and DLP eligibility flags | Await M3-006 and privacy rules |
| IMP-M3-010 | `NOT_STARTED` | Reusable dbt DQ macros, severity and quarantine outputs | Await Silver models |
| IMP-M3-011 | `NOT_STARTED` | Unknown members, late dimensions and deterministic corrections | Await M3-004…010 |
| IMP-M3-012 | `NOT_STARTED` | Conformed date/customer/product/seller/geography dimensions | Await M3-011 |
| IMP-M3-013 | `NOT_STARTED` | Order/item/payment/review base facts | Await M3-012 |
| IMP-M3-014 | `NOT_STARTED` | Versioned multi-item review attribution policy/bridge | Await M3-013 and M0 allocation decision |
| IMP-M3-015 | `NOT_STARTED` | Delivery, product-review, seller and customer marts | Await dimensions/facts/allocation |
| IMP-M3-016 | `NOT_STARTED` | Release-bound dashboard/SQL semantic views | Await marts |
| IMP-M3-017 | `NOT_STARTED` | Candidate Gold build/test target | Await semantic views |
| IMP-M3-018 | `NOT_STARTED` | Release events, immutable definition and CAS active pointer | Await tested Gold candidate |
| IMP-M3-019 | `NOT_STARTED` | Request resolver pins explicit Silver/Gold physical refs | Await atomic release pointer |
| IMP-M3-020 | `NOT_STARTED` | Full/incremental equivalence, metrics, lineage and runbook | Await complete M3 graph |

## Exit gate

M3 remains `IN_PROGRESS` until all declared grains and metrics reconcile, critical
dbt tests pass, failed/concurrent candidates cannot affect serving, and a tested
release can be activated and rolled back atomically. Offline scaffolds and parse
tests do not count as the final Snowflake release drill.
