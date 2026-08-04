# M0 Product and Data Baseline — Olist

## Portfolio scope

| Decision | Baseline |
|---|---|
| Product domain | E-commerce review, order and delivery intelligence |
| Primary personas | Portfolio viewer, analyst, operator/owner |
| Demo exposure | Local/private; GitHub contains code, synthetic fixtures and safe evidence only |
| Delivery strategy | Synthetic nine-table slice first; private Olist snapshot ingestion in M2 |
| Warehouse | Snowflake only |
| Data lake | Private Cloudflare R2 |

## Analytical population v1

Every order receives `analysis_scope_status`, `analysis_scope_reason` and
`analysis_scope_version='olist_order_scope_v1'`.

| Condition | Status | Use |
|---|---|---|
| Delivered order with valid customer and at least one valid item | `IN_SCOPE` | Core delivery, payment and review analytics |
| Cancelled or unavailable order | `OUT_OF_SCOPE_DELIVERY` | Operational counts only; excluded from delivery SLA metrics |
| Missing required parent/invalid key | `QUARANTINED` | Audit and repair only |
| Status not recognized by contract | `UNKNOWN` | Visible in DQ coverage, not silently included |

Review AI eligibility is narrower: a valid in-scope review must have a score,
pass DLP/policy projection and belong to an active candidate release. Empty
comment text may contribute to score KPIs but cannot be embedded or summarized.

## Data history and time

| Entity | Rule |
|---|---|
| Customer/product/seller | Snapshot history; SCD2 only when a later snapshot changes descriptive fields |
| Order | Immutable business event plus deterministic correction history |
| Order item/payment/review | Preserve source rows; deterministic dedup by declared compound key/source hash |
| Geolocation | Conform ZIP prefix through versioned centroid/quality rule |
| Timestamps | Preserve raw `TIMESTAMP_NTZ`; derive Brazilian local calendar fields through a versioned policy |

Absence is deletion only for a confirmed complete later snapshot and an accepted
source rule. Legal/privacy deletion is a controlled tombstone exception that is
reapplied during restore or rebuild.

## Metric dictionary v1

| Metric | Grain/filter | Definition/guardrail |
|---|---|---|
| Orders | release/date/status | distinct `order_id`; never count item rows as orders |
| Delivered orders | release/date | distinct orders with delivered status |
| Gross merchandise value | order/item | sum item `price`; label as dataset GMV proxy, not Olist accounting revenue |
| Freight value | order/item | sum `freight_value`; preserve currency context from dataset documentation |
| Payment value | order/payment | sum payment rows; report reconciliation delta versus item + freight |
| Average review score | release/filter | average valid `review_score` 1–5 with sample size |
| Review response latency | review | answer timestamp minus creation timestamp; invalid negative durations quarantined |
| Delivery lead time | delivered order | delivered-to-customer minus purchase timestamp |
| Delivery delay | delivered order | delivered-to-customer minus estimated-delivery date; define on-time as `<= 0` days |
| On-time delivery rate | eligible delivered orders | on-time / orders with both actual and estimated dates |
| Cancellation rate | orders | cancelled / all valid orders in selected cohort |
| Repeat-customer rate | customer unique ID | unique customers with more than one order / unique customers |
| Sentiment distribution | enriched review/version | label count / valid enriched reviews; always display AI coverage |
| Negative aspect rate | aspect/version | negative aspect records / reviews with a valid aspect result |

Product/category/seller attribution from reviews must display its allocation
policy. A multi-item order review cannot be copied to every product then summed
as if the rows were independent.

## AI taxonomy v1

- Sentiment: `positive`, `neutral`, `negative`, `mixed`.
- Aspects: `product_quality`, `delivery`, `packaging`, `customer_service`,
  `price_value`, `product_description`, `payment`, `other`.
- Topics: controlled multi-label taxonomy versioned separately.
- Outputs: sentiment, aspect sentiment, topics, short summary, highlights,
  confidence and schema/model/prompt versions.

The portfolio pilot enriches at most 2,000 stratified comments initially and
10,000 comments total without a budget revision.
