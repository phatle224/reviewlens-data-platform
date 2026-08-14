# M3 Checklist — Conformed Silver, Gold and atomic release

| Attribute | Value |
|---|---|
| Phase status | `IN_PROGRESS` |
| Completed | 14/20 work items |
| Partial | 0/20 work items |
| Blocked | 0/20 work items |
| Not started | 6/20 work items |
| Last updated | 2026-08-15 |

## Implementation-plan checklist

| Work item | Status | Required outcome | Evidence / remaining work |
|---|---|---|---|
| IMP-M3-001 | `DONE` | Processing-run/input and candidate physical-reference ledger | Deterministic SHA-256 run/input/candidate identities, ordered 1:N lineage and replay-safe in-memory registry; additive `006_processing_candidates.sql` creates three secret-free append-only ledgers with exact grants; migration replay and contract tests pass |
| IMP-M3-002 | `DONE` | Versioned Silver candidate build/cleanup strategy | Versioned candidate IDs produce isolated physical object namespaces inside least-privilege `SILVER`/`GOLD` schemas; thread-safe lease tests allow one concurrent owner and cleanup only terminal failed/unreferenced candidates |
| IMP-M3-003 | `DONE` | dbt Bronze sources, freshness, contracts and docs | All nine Bronze relations declare exact typed business/lineage columns, canonical physical-grain tests, bounded freshness, privacy/license metadata and `m3_bronze_contract`; offline dbt parse passes with warnings-as-errors |
| IMP-M3-004 | `DONE` | `SIL_CUSTOMER`, minimized repeat-customer key and geography | Candidate-bound table contract deduplicates by deterministic lineage order, excludes raw `customer_unique_id`, emits versioned SHA-256 repeat key and normalized ZIP/city/state; privacy/type/dedup fixture tests pass |
| IMP-M3-005 | `DONE` | Deterministic `SIL_GEOLOCATION_ZIP` centroid/quality model | One row per normalized ZIP, fixed-scale valid-point centroid, occurrence/reconciliation counts and explicit valid/ambiguous/partial/no-valid quality states; known-count/no-multiplication fixtures pass |
| IMP-M3-006 | `DONE` | `SIL_ORDER` status/time/scope/delivery flags | One deterministic order with M0 `olist_order_scope_v1`, Brazilian local-civil policy, parent/item guards and nonnegative delivery interval/on-time rules; delivered/canceled/missing/unknown/time-edge fixtures pass |
| IMP-M3-007 | `DONE` | `SIL_ORDER_ITEM` and `SIL_ORDER_PAYMENT` | Candidate-bound compound grains deduplicate deterministically, retain typed amounts, expose parent-order and versioned quality states, and preserve exact item+freight/payment reconciliation semantics; composite-key/range/orphan/delta fixtures pass |
| IMP-M3-008 | `DONE` | `SIL_PRODUCT`, translation and `SIL_SELLER` | Translation has deterministic category grain/fallback; product corrects source `*_lenght` names and flags missing translation; seller normalizes private location and joins unique ZIP quality without multiplication; contract/static fixtures pass |
| IMP-M3-009 | `DONE` | `SIL_ORDER_REVIEW` and DLP eligibility flags | Restricted review base deduplicates at `review_id + order_id`, retains score-only analytics, guards response interval and labels orphan/out-of-scope/score-only/`PENDING_DLP`; `ai_eligible=false` until a separate M4 DLP projection; privacy/negative fixtures pass |
| IMP-M3-010 | `DONE` | Reusable dbt DQ macros, severity and quarantine outputs | Versioned DQ projection macro emits only hashed-grain metadata; `SIL_DQ_QUARANTINE` covers order/geography/item/payment/product/seller/review findings at `CRITICAL`, `WARN` or `QUARANTINE`; typed Python gate is replay deterministic and moves a candidate to `FAILED` on any critical finding; `m3_silver_critical` selects the fail-closed singular test |
| IMP-M3-011 | `DONE` | Unknown members, late dimensions and deterministic corrections | Four entity-specific SHA-256 unknown members and candidate-bound registry are stable; Python revision resolver orders effective time, ingestion time, row number and record hash, records replay duplicates and labels late versus superseded corrections; all deduplicated Silver bases use one reusable deterministic rank macro |
| IMP-M3-012 | `DONE` | Conformed date/customer/product/seller/geography dimensions | Five candidate-bound models resolve to exact `GOLD` schema; event-complete date keys, version-aware SHA-256 member keys, stable entity unknowns, half-open SCD intervals and reusable non-overlap/as-of tests pass; customer/seller geography joins cannot multiply the declared grain |
| IMP-M3-013 | `DONE` | Order/item/payment/review base facts | Four candidate-bound facts enforce order, compound item/payment and review/order grains; invalid Silver rows are filtered through explicit quality states, dimension lookup is as-of with unknown fallback, and a singular gate reconciles eligible counts plus item/payment amounts; review fact contains no title/comment and remains independent of AI coverage |
| IMP-M3-014 | `DONE` | Versioned multi-item review attribution policy/bridge | ADR-011 freezes transparent equal-item weighting with deterministic 18-decimal residual and unknown-item fallback; candidate-bound bridge exposes policy labels and only allocated additive measures; Python single/two/three/zero-item, reorder and invalid/duplicate fixtures plus dbt grain/relationship/privacy and exact per-review reconciliation gates pass |
| IMP-M3-015 | `NOT_STARTED` | Delivery, product-review, seller and customer marts | Dependency ready after M3-014; implement metric-dictionary fixtures next |
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
