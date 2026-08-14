# ADR-011 — Review-to-item attribution policy

- Status: Accepted
- Date: 2026-08-15
- Owner: Solo Developer (Product/Data hats)

## Context

Olist reviews describe an order, while an order can contain multiple items,
products and sellers. The source does not identify which item a reviewer meant.
Copying a full review count and score to every item would silently inflate
product, category and seller aggregates.

## Decision

Use policy `olist-review-item-equal-weight-v1` in a separate review-to-item
bridge. One valid order review contributes a total allocation weight and review
count of exactly `1`:

- one eligible item receives weight `1`;
- multiple eligible items receive equal weights at 18-decimal precision;
- item keys are sorted deterministically and the final item receives any decimal
  residual, so weights sum exactly to `1`;
- a review with no eligible Gold item receives one explicit unknown-product and
  unknown-seller fallback row with weight `1`, so it remains reconcilable.

`allocated_review_count` and `allocated_review_score` are additive measures.
The repeated `review_score`, bridge rows and row count are not naturally
additive. Product/category/seller outputs must display the policy version and a
sample size based on allocated review count. Order-level review KPIs continue to
use `FACT_REVIEW_BASE`.

## Consequences

Equal weighting is transparent and does not invent item-level evidence. It is an
allocation for aggregate reporting, not a claim that every item received the
same opinion. Price weighting is rejected because the source provides no basis
for treating price as review relevance. Full-credit duplication is rejected
because it inflates counts and scores.

Changing the method requires a new policy version and metric comparison; an
existing release is never reinterpreted silently.

## Verification

Single-, two-, three- and zero-item fixtures; input-order invariance; duplicate
item rejection; exact per-review weight/count/score reconciliation; dbt grain,
relationship, unknown-fallback and privacy contracts.
