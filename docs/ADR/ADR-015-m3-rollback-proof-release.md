# ADR-015 — M3 rollback-proof release revision

- Status: Accepted
- Date: 2026-08-20
- Owner: Solo Developer (Data/Security hats)

## Context

The first M3 immutable Olist release is active at pointer v1. A live server-side
rollback cannot target the v0 uninitialized sentinel, so proving rollback needs a
second eligible immutable release. The Olist portfolio source is static; changing
source data or semantic metrics solely for a demo would misrepresent the product.

## Decision

Create one private rollback-proof candidate pair using the fixed processing
contract revision `reviewlens-silver-candidate-v1.rollback-proof-v1`. It retains
the same approved nine Bronze inputs, source release, ingestion batch, dbt
selectors, semantic catalog and 28-relation contract as the active release.

The revision intentionally changes only processing-run/candidate identity. It
must complete the normal private full-refresh/deterministic-replay, DQ and
aggregate-fingerprint gates before a second immutable definition can be
registered. Then activate release 2 with CAS v1 and roll back to the existing
release 1 with CAS v2. All transitions use the guarded procedures; no direct
pointer update or public data artifact is permitted.

## Consequences

This proves activation and rollback mechanics without claiming a different Olist
data state or semantic interpretation. It creates private candidate tables and
bounded Snowflake usage only; R2, OpenRouter and Chroma remain untouched. The
revision is an M3 verification artifact, not a general reprocessing API.

## Verification

Offline tests require distinct candidate/release identities with equal source,
batch, selector and semantic contracts. Live evidence requires two eligible
definitions, pointer transitions v1→v2→v3, one `ACTIVATED` event per release,
one `ROLLED_BACK` event to release 1, and a suspended warehouse.

## Outcome

Passed live on 2026-08-20: the private rollback-proof pair completed aggregate
equivalence, registered a second 28-ref definition, activated v1→v2 and rolled
back to release 1 v2→v3. Aggregate evidence records 2 definitions, 56 refs, 2
`CREATED`, 2 `ACTIVATED`, 1 `ROLLED_BACK` and a suspended warehouse.
