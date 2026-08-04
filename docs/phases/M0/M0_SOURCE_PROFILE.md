# M0 Source Profile — Olist Brazilian E-Commerce Dataset

## Source decision

| Field | Accepted value |
|---|---|
| Dataset | Brazilian E-Commerce Public Dataset by Olist |
| Source | `https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce` |
| Accessed | 2026-08-05 |
| License | CC BY-NC-SA 4.0 |
| Local location | ignored `archive/` directory |
| Snapshot semantics | One complete snapshot containing exactly nine required CSV files |
| Active source ADR | [ADR-008](../../ADR/ADR-008-olist-primary-dataset.md) |
| Metadata manifest | [OLIST_SOURCE_MANIFEST.md](../../data/OLIST_SOURCE_MANIFEST.md) |

The files were profiled using filename, byte size, header, row count and SHA-256
only. Review-row values were not printed or committed.

## Required source contract

| Dataset | Physical file | Grain/key | Main relationships | Rows in snapshot |
|---|---|---|---|---:|
| Customers | `olist_customers_dataset.csv` | one row per `customer_id` | parent of orders; `customer_unique_id` groups repeat buyers | 99,441 |
| Geolocation | `olist_geolocation_dataset.csv` | one coordinate record per ZIP-prefix occurrence | customer/seller ZIP prefixes | 1,000,163 |
| Order items | `olist_order_items_dataset.csv` | `order_id + order_item_id` | orders, products, sellers | 112,650 |
| Payments | `olist_order_payments_dataset.csv` | `order_id + payment_sequential` | orders | 103,886 |
| Reviews | `olist_order_reviews_dataset.csv` | source review row; dedup by `review_id + order_id` | orders | 99,224 |
| Orders | `olist_orders_dataset.csv` | one row per `order_id` | customers; parent of item/payment/review | 99,441 |
| Products | `olist_products_dataset.csv` | one row per `product_id` | order items; category translation | 32,951 |
| Sellers | `olist_sellers_dataset.csv` | one row per `seller_id` | order items | 3,095 |
| Category translation | `product_category_name_translation.csv` | one row per Portuguese category | products | 71 |

All nine files are required. Missing, duplicate, truncated or header-incompatible
files make the source release incomplete. Row counts above exclude headers and
identify this snapshot; they are not timeless product claims.

## Relationship and data-quality risks

- `customer_id` identifies an order-scoped customer record;
  `customer_unique_id` is the repeat-customer grouping key.
- Review comments and titles are nullable; score remains analytically useful.
- Orders may be cancelled, unavailable or not delivered; delivery metrics must
  use an explicit eligible-status policy.
- A review can be associated with a multi-item order, so product/category review
  attribution is many-to-many and must avoid silent double counting.
- Geolocation has repeated ZIP prefixes. Use an explicit centroid/quality rule,
  not an unconstrained join that multiplies facts.
- Product source fields contain the original `*_lenght` spelling; Bronze keeps
  source headers while Silver uses corrected canonical column names.
- Timestamps are source-local civil times without offsets. Preserve raw values
  and apply the versioned Brazilian-time policy only in Silver.
- Free-text comments are untrusted content and require DLP/prompt-injection
  controls before AI or public presentation.

## Snapshot identity

`source_release_id` is a canonical hash over the sorted nine-file manifest
(filename, byte count and SHA-256), not the directory name or download date.
Same manifest is an idempotent replay; same filename with different bytes is a
new candidate snapshot; a missing required file cannot produce a release.
