# ADR-007 — SCD, Time and Retention Baseline

- Status: Accepted baseline; revised for Olist source
- Date: 2026-08-04
- Owner: Solo Developer (Data/Security hats)

## Decision

Use immutable snapshot history for Olist source rows. Customer, product and seller conformed dimensions may use SCD Type 2 when a future snapshot changes descriptive attributes. Orders, order items, payments and reviews keep source-event history and deterministic current/correction rules. Preserve raw timestamps as `TIMESTAMP_NTZ`; the source is interpreted as Brazilian local civil time only through a versioned time policy, never by silently attaching UTC.

Use the engineering retention defaults in `docs/phases/M0/M0_SECURITY_PRIVACY.md`. CC BY-NC-SA 4.0 has no fixed dataset-expiry date, but non-commercial, attribution, ShareAlike, privacy and provider-processing controls remain mandatory. A deletion/privacy obligation is a controlled exception with tombstone and restore suppression.

## Verification

Late/correction/full-vs-partial snapshot fixtures, deterministic current-row selection, Brazilian local-time boundary tests, tombstone propagation and restore suppression drill.
