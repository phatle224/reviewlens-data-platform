# ADR-008 — Olist as the Primary Dataset

- Status: Accepted
- Date: 2026-08-05
- Owner: Solo Developer (Product/Data/Security hats)
- Supersedes: active Yelp source assumptions and the previous Yelp compliance gate

## Context

The original design used the Yelp Open Dataset, but its applicable terms and the
project's non-academic status prevented the intended R2 → Snowflake → AI
portfolio flow. The Olist Brazilian E-Commerce Public Dataset supplies review
text plus richer relational order, payment, product, seller, customer and
delivery context, and is published under CC BY-NC-SA 4.0.

## Decision

Use the Olist Brazilian E-Commerce Public Dataset as ReviewLens's only active
real-data source. Preserve the ReviewLens brand while changing the product
domain from restaurant intelligence to e-commerce review and delivery
intelligence.

The source contract contains exactly nine CSV files. All nine are required for a
complete snapshot. Raw files stay outside Git. Private R2 and Snowflake use is
permitted for this non-commercial portfolio after manifest and privacy gates.
External AI receives only the minimized, DLP-approved review projection. Public
evidence contains aggregates, redacted screenshots or synthetic fixtures, not
raw reviews, embeddings or row-level exports.

Attribution, NonCommercial and ShareAlike obligations are enforced through
`docs/DATA_ATTRIBUTION.md`, config validation and release checks.

## Consequences

- `data_mode` supports `synthetic` and `olist`; synthetic remains the default
  until M2 source-ingestion gates pass.
- Source parsing changes from JSONL to CSV and all nine files become required.
- Warehouse models shift to orders, customers, items, payments, reviews,
  products, sellers, geolocation and category translation.
- Product insights focus on satisfaction, delivery, freight, payment, product
  category, seller and geography.
- Yelp files may remain ignored locally for owner-controlled cleanup, but no
  active requirement, pipeline or public claim depends on them.

## Verification

- Source snapshot filename/header/row/checksum manifest is recorded.
- Config rejects a weakened license contract.
- Synthetic fixtures reproduce all nine headers and valid foreign keys.
- Git/data-leak scan rejects raw Olist CSVs and row-level artifacts.
- Active docs, DAG name and diagram use Olist terminology.
