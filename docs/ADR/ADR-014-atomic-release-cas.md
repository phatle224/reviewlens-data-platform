# ADR-014 — Immutable release definition and CAS activation

- Status: Accepted
- Date: 2026-08-16
- Owner: Solo Developer (Data/Security hats)

## Context

M3 has isolated, tested Silver/Gold candidate namespaces but no serving release
or active pointer. A successful dbt target must not itself become visible to
dashboard, Text-to-SQL or RAG consumers. Retrying an operator command or racing
two activation attempts must not create mixed versions or overwrite a newer
release.

## Decision

Create one immutable release definition only when both the referenced Silver and
Gold candidates are `TEST_PASSED`. Its deterministic SHA-256 identity covers
source/batch identifiers, processing runs, both candidate IDs, semantic catalog
version and every Silver/Gold physical relation. The definition has no mutable
status field.

Append `CREATED`, `ACTIVATED`, `ROLLED_BACK`, `INVALIDATED` and `REVOKED` events.
The sole active-pointer row is seeded with version `0` and an uninitialized
sentinel. Owner-executed, versioned Snowflake procedures insert the event and
perform one `UPDATE ... WHERE POINTER_VERSION = expected` in a transaction.
Exactly one concurrent caller can advance a version; an already-applied request
returns replay rather than creating another pointer transition.

`GOLD_BUILDER_ROLE` may append definitions/object references/events and execute
the two guarded procedures. It receives no direct `UPDATE`/`DELETE` privilege on
the pointer. Candidate physical references remain private from analyst and
Text-to-SQL roles; M3-019 will expose only server-side, request-pinned logical
resolution.

## Consequences

Failed/partial candidates cannot form a release definition. Terminally
invalidated or revoked releases cannot be activated. An active release must be
rolled back before terminal invalidation/revocation. The live migration and
procedure smoke test remain owner-approved Snowflake work; in-memory race,
rollback and failure tests are not a substitute for it.

## Verification

Deterministic definition/replay fixtures, failed-candidate pointer preservation,
two-writer CAS race, stale CAS denial, activation/rollback replay, terminal-state
denial, migration/RBAC contract scans and future opt-in Snowflake procedure
smoke tests.
