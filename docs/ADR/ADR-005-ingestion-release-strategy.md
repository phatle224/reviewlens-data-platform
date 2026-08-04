# ADR-005 — Snapshot Ingestion and Atomic Release Strategy

- Status: Accepted baseline
- Date: 2026-08-04
- Owner: Solo Developer (Data Architecture hat)

## Decision

Treat the nine-file Olist CSV bundle as one complete source snapshot. A batch is eligible only when every required filename, header and checksum matches a manifest. Fingerprint source bytes, archive originals privately in R2, load immutable Bronze and build isolated Silver/Gold candidates. AI maps and ChromaDB collections are release-addressable. A guarded pointer changes only after all gates pass.

## Consequences

- Replay and same-name/new-content cases are explicit.
- Absence becomes deletion only for a confirmed complete snapshot.
- A failed/partial run never mutates the active serving release.

## Verification

Snapshot conflict, duplicate replay, partial source, concurrent run, failure injection, pointer compare-and-set, rollback and revoked-release tests.
