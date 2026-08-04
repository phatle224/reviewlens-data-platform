# ADR-004 — Local ChromaDB Vector Store

- Status: Accepted
- Date: 2026-08-04
- Owner: Solo Developer (AI/Platform hats)

## Decision

Use ChromaDB local with a persistent volume. Each candidate `index_version` maps to a distinct collection. Snowflake `AI.RAG_DOCUMENT` and release maps are authoritative; ChromaDB is a rebuildable retrieval index and stores only serving-safe document/filter metadata.

## Consequences

- No Cortex Search or pgvector in MVP.
- Local disk, backup and service availability must be monitored.
- Release activation binds an explicit collection name; candidate collection is never queried by active traffic.

## Verification

Restart persistence, idempotent upsert, metadata filter isolation, expected-vs-index reconciliation, candidate invisibility, active/rollback collection switch and rebuild from Snowflake.

