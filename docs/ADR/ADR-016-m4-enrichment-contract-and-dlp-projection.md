# ADR-016 — M4 enrichment contract and DLP projection

## Status

Accepted — 2026-08-21.

## Context

Olist review title/comment fields are restricted, untrusted UGC. M3 keeps their
base facts private and sets `ai_eligible=false`; M4 must not treat a length cap
as redaction or send review/order/customer/seller identifiers to OpenRouter.
The system needs a reproducible output shape and a transfer boundary before any
provider call, selection, prompt, or result persistence is introduced.

## Decision

- The v1 enrichment result has only: `sentiment`, `confidence`,
  `aspect_sentiments`, `topics`, `summary`, and `highlights`.
- Sentiment values are `positive`, `neutral`, `negative`, and `mixed`. The
  aspect taxonomy is `product_quality`, `delivery`, `packaging`,
  `customer_service`, `price_value`, `product_description`, `payment`, and
  `other`. Topic values are versioned with the same contract and are not free
  text identifiers.
- `enrichment_version` is the SHA-256 of pinned model slug, provider-policy,
  prompt, schema and taxonomy versions. Changing any component requires a new
  version and regression evaluation.
- A DLP projection accepts only a source-record hash and restricted title/comment
  in private process memory. It replaces recognized email, URL, phone and
  CPF-like values; excludes natural IDs from its output; hashes the minimized
  text; and emits an opaque review reference. Empty, over-limit, secret-like or
  ambiguous input is quarantined fail-closed with a sanitized code.
- The provider boundary accepts `ApprovedAIText` only. Audit ledgers store IDs,
  hashes, versions, state, tokens, latency, cost and sanitized error codes, never
  review text, prompt text, response body, natural IDs, credentials or payment
  fields.

## Consequences

M4 can build/test all contracts with synthetic text offline. A real OpenRouter
call remains blocked until the catalog/policy/price snapshot, eligible selector,
prompt injection tests, validation, retry and budget controls are complete.
Redacted text is still restricted source-derived data: it remains private and is
never committed, publicly displayed by default, or reused as a claim of public
evidence.
