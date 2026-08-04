# Olist source snapshot manifest

This metadata-only manifest identifies the local source snapshot downloaded on
2026-08-05. It contains no dataset rows. The CSV files live in the ignored
`archive/` directory and must not be committed.

| File | Rows | Bytes | SHA-256 |
|---|---:|---:|---|
| `olist_customers_dataset.csv` | 99,441 | 9,033,957 | `983a422239e1712ded753b3bf9ecf47dc73f144d306029dcfa99e70a226883d2` |
| `olist_geolocation_dataset.csv` | 1,000,163 | 61,273,883 | `b514f6fc991b9566aeba02aa5d67e2c3630f034b60a0e05aa0d082a3b66d88d6` |
| `olist_order_items_dataset.csv` | 112,650 | 15,438,671 | `0bc4d068c4fe38cbb01bd90e8746e3c613fe7b4baef75fab7b0e329701c3e279` |
| `olist_order_payments_dataset.csv` | 103,886 | 5,777,138 | `4f713964f2815dbbaa40b9488268c55aac3627bfce5aa96cf58d1f3616de3cc0` |
| `olist_order_reviews_dataset.csv` | 99,224 | 14,451,670 | `012b61c7593e34f51fa614efdf802b9c7056ce6aae5307ddb93236e7cfc797d7` |
| `olist_orders_dataset.csv` | 99,441 | 17,654,914 | `8df58ef3d2d7e9944010f7beecd9b75367f5588ec6e3c91cec19ae3345ef9ecf` |
| `olist_products_dataset.csv` | 32,951 | 2,379,446 | `3e6569628a17fbc75fd206ee357b59e20364b9afa90f5b6cd5b4d624c58aa9cc` |
| `olist_sellers_dataset.csv` | 3,095 | 174,703 | `1f643d2b950373b85735e7794b20986f528d7a000432e7c6f9bcbb44d0846a0e` |
| `product_category_name_translation.csv` | 71 | 2,613 | `a81f0d1f27b27e7293f761bc79e3ce8f348ee39c4b3ed3e49bde38f478586278` |

## Header contract

- customers: `customer_id`, `customer_unique_id`, ZIP prefix, city, state
- geolocation: ZIP prefix, latitude, longitude, city, state
- order items: order/item/product/seller IDs, shipping deadline, price, freight
- payments: order ID, sequence, type, installments, value
- reviews: review/order IDs, score, title, message, creation and answer timestamps
- orders: order/customer IDs, status and purchase/approval/delivery timestamps
- products: product/category IDs, name/description lengths, photos, dimensions
- sellers: seller ID, ZIP prefix, city, state
- translation: Portuguese and English product-category names

Row counts exclude the header. A future source replacement must update this
manifest, repeat the privacy scan and receive a new ingestion batch identifier.
