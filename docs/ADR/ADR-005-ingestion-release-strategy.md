# ADR-005 — Snapshot Ingestion and Atomic Release Strategy

- Status: Accepted baseline
- Date: 2026-08-04
- Owner: Solo Developer (Data Architecture hat)

## Decision

Treat each Yelp JSON archive as a complete source snapshot unless manifest evidence says otherwise. Fingerprint source bytes, archive originals, generate Parquet/Snappy, load immutable Bronze and build isolated Silver/Gold candidates. AI map and ChromaDB collection are release-addressable. A guarded pointer changes only after all gates pass.

## Consequences

- Replay and same-name/new-content cases are explicit.
- Absence becomes deletion only for a confirmed complete snapshot.
- A failed/partial run never mutates the active serving release.

## Verification

Snapshot conflict, duplicate replay, partial source, concurrent run, failure injection, pointer compare-and-set, rollback and revoked-release tests.

