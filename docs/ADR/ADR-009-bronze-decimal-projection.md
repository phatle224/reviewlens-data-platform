# ADR-009 — Deterministic Bronze decimal projection

- Status: Accepted
- Date: 2026-08-14
- Owner: Solo Developer (Data Architecture hat)

## Context

The approved Olist geolocation snapshot contains valid latitude values with up
to 20 fractional digits. The versioned Bronze physical contract uses
`DECIMAL(38,18)` in Parquet and `NUMBER(38,18)` in Snowflake. PyArrow correctly
rejects a scale-20 value instead of silently coercing it, which blocked the first
owner-approved full M2 ingestion run before any Snowflake COPY occurred.

## Decision

Keep the existing typed Bronze `DECIMAL(38,18)` contract and apply an explicit,
deterministic `ROUND_HALF_EVEN` projection to decimal columns when constructing
the physical Parquet row. Preserve the exact parsed decimal string in
`RAW_PAYLOAD`; canonical record hashes and source/release identities continue to
use the unprojected typed source value.

This is a physical analytics projection, not a mutation of the immutable source:
the original CSV remains checksum-addressed in private R2 and the exact decimal
remains recoverable from private Bronze `RAW_PAYLOAD`. No rounded value is used
to identify a source record or release.

## Consequences

- Scale-20 Olist coordinates load into the existing Snowflake Bronze schema
  without an unsafe destructive table rebuild.
- Typed decimal comparisons are stable across Python, Parquet and Snowflake.
- Coordinates can differ from source by at most half of `10^-18` degrees in the
  typed projection; exact source precision remains available privately.
- Decimal values whose total precision cannot fit `DECIMAL(38,18)` still fail
  closed with `PARQUET_ARTIFACT_INVALID`.

## Verification

- Regression fixture writes scale-20 latitude/longitude values, verifies
  half-even typed projection and exact `RAW_PAYLOAD` preservation.
- Full approved nine-file M2 DAG run and replay must reconcile source,
  quarantine and Bronze counts before the phase can close.
