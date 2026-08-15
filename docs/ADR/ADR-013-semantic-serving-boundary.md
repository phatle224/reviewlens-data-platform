# ADR-013 — Curated semantic serving boundary

- Status: Accepted
- Date: 2026-08-15
- Owner: Solo Developer (Data/Security hats)

## Context

Dashboards and generated SQL must not depend on Bronze, Silver, base facts,
allocation bridge rows or candidate physical identifiers. At the same time, M3
does not yet have the compare-and-set active release mechanism planned for
`IMP-M3-018/019`.

## Decision

Define four logical semantic contracts in `semantic_catalog.v1.json`:
`ORDER_DELIVERY`, `PRODUCT_REVIEW`, `SELLER_PERFORMANCE` and
`CUSTOMER_OVERVIEW`. Each maps to one candidate-bound dbt view, exposes an exact
column allowlist and includes `data_release_id`, metric policy and semantic
contract version on every row.

The application and future Text-to-SQL layer resolve only catalog logical names.
They never accept a database, schema, candidate namespace, physical relation or
dbt model name from a user/model response. Catalog physical resolution policy is
`resolve_active_release_server_side`; the active pointer implementation remains
owned by `IMP-M3-018/019` and is not simulated early.

Semantic views read only the four approved marts. They exclude source natural
IDs, source hashes, review text, bridge rows and AI outputs. Product/seller
views expose fractional allocated review sample size and explicit non-additive
order-count usage. AI state is `NOT_AVAILABLE_UNTIL_M4`, not a fabricated zero.
GMV is labeled as a dataset proxy rather than accounting revenue.

Only `ANALYST_ROLE` and `TEXT_TO_SQL_ROLE` are valid catalog grant roles. A
candidate view is not automatically granted or published; exact stable-view
grants happen only during the later atomic activation workflow.

## Consequences

M6 can derive table/column/metric allowlists from one typed catalog. Candidate
builds remain testable without changing serving access. Dashboards can display
release and partial-AI context without reading internal tables.

Adding a view or column, changing aggregation semantics, or widening a grant
requires an explicit catalog/contract version review.

## Verification

Strict catalog parsing, duplicate/unknown-field/unsafe-identifier negatives,
logical-name-only resolution, exact dbt-YAML/catalog column equality, mart-only
lineage, privacy scans, view materialization and role allowlist tests.
