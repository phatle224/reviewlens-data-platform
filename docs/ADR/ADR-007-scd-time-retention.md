# ADR-007 — SCD, Time and Retention Baseline

- Status: Accepted baseline; Terms-dependent retention remains pending
- Date: 2026-08-04
- Owner: Solo Developer (Data/Security hats)

## Decision

Use SCD Type 2 for mutable business/user snapshots, immutable version history for reviews, deterministic event keys for check-ins/tips and long-form derived attributes. Preserve raw timestamps; naive values use `TIMESTAMP_NTZ` plus an explicit unknown/local assumption. Legal deletion is a controlled exception with tombstone/restore suppression.

Use the engineering retention defaults in `docs/phases/M0/M0_SECURITY_PRIVACY.md` until the bundled Yelp Terms are reviewed. A stricter Terms requirement overrides the default.

## Verification

Late/correction/full-vs-partial snapshot fixtures, deterministic current-row selection, DST/offset/naive timestamp tests, tombstone propagation and restore suppression drill.

