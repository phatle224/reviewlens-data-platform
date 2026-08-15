# ADR-012 — Gold mart grains and metric semantics

- Status: Accepted
- Date: 2026-08-15
- Owner: Solo Developer (Product/Data hats)

## Context

Metric dictionary v1 defines order, value, delivery, review and repeat-customer
measures, but the aggregate grains and join order must also be fixed. Joining
order, item, payment and review rows directly would multiply non-matching fact
grains and make otherwise familiar KPIs irreproducible.

## Decision

Use purchase month as the period for the four M3 marts:

- `MART_ORDER_DELIVERY`: purchase month plus customer geography;
- `MART_PRODUCT_REVIEW`: purchase month plus conformed product;
- `MART_SELLER_PERFORMANCE`: purchase month plus conformed seller;
- `MART_CUSTOMER_OVERVIEW`: purchase month plus customer geography.

Item and payment facts are aggregated to order grain before joining order-level
metrics. Seller delivery measures first collapse items to one seller/order row.
Product and seller review measures use only the additive fields from ADR-011;
their fractional allocated review count is the displayed sample size.

A delivery denominator includes only `delivered` orders with a valid interval,
lead time, delay and on-time flag. A zero denominator produces `NULL`, never a
zero rate. Cancellation follows the normalized Olist status `canceled`.

Repeat-customer rate uses policy `olist-repeat-customer-lifetime-v1`: among
known repeat identities active in a purchase-month/geography cohort, the
numerator is identities having more than one valid lifetime order. Unknown
customers remain visible as order counts but are excluded from both customer
rate numerator and denominator.

All marts publish `olist-metric-dictionary-v1`. GMV is the dataset proxy defined
in M0, not accounting revenue. Payment reconciliation delta is payment value
minus item price minus freight.

## Consequences

Monthly rows are reproducible and additive only for explicitly additive
measures. Product/seller `order_count` must not be summed across products or
sellers because one order may belong to several members. Later semantic views
must expose these usage rules and the active release.

Changing a grain, denominator or allocation requires a new policy/model version;
an existing release is never reinterpreted.

## Verification

Golden order/delivery/value, fractional-review and repeat-customer fixtures;
zero-denominator and invalid-input tests; dbt unique-grain/relationship tests;
cross-mart count, amount and allocated-review reconciliation.
