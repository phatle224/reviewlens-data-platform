# M3 — Conformed Silver, Gold and atomic release

M3 builds trusted relational models from immutable Olist Bronze in isolated,
versioned candidates. A candidate can become serving data only after its lineage,
data-quality, grain, metric and concurrency gates pass; failed candidates never
change the active release pointer.

| Artifact | Purpose |
|---|---|
| [M3 checklist](./M3_CHECKLIST.md) | Status and evidence for 20 implementation items |
| [M3 test cases](./M3_TEST_CASES.md) | Offline, dbt, concurrency and opt-in live gates |
| [Implementation plan](../../IMPLEMENTATION_PLAN.md) | Dependencies and acceptance criteria |
| [ADR-005](../../ADR/ADR-005-ingestion-release-strategy.md) | Immutable candidate and atomic-release baseline |
| [ADR-013](../../ADR/ADR-013-semantic-serving-boundary.md) | Logical semantic names, approved fields and delayed activation |
| [ADR-014](../../ADR/ADR-014-atomic-release-cas.md) | Immutable release definition and CAS activation/rollback |

Phase status: `IN_PROGRESS` with 19/20 work items complete and `IMP-M3-018`
partial. Bundles
`IMP-M3-001…019` deliver processing lineage, isolated candidates, Silver/DQ
contracts, five conformed dimensions, four reconciled base facts and a versioned
review-to-item allocation bridge. Four monthly Gold marts apply metric dictionary
v1 only after pre-aggregating incompatible fact grains. Four curated semantic
views expose logical, release-bound contracts for dashboard and Text-to-SQL
consumers without leaking physical candidate identifiers, natural IDs or review
text. The Gold target reads one tested Silver candidate namespace and writes a
different Gold candidate namespace; its complete selector cannot mark a partial
or failed result as tested. An immutable release definition then binds both
candidates and every physical ref, while a versioned CAS pointer supports one
winner, replay and rollback without direct runtime role updates. The server-side
request resolver snapshots that pointer once and maps only allowlisted semantic
names to explicit refs from the same immutable definition, rejecting physical
inputs and mixed-release reads during activation races. Dimension lookups are
version-aware/as-of and multi-item review weights reconcile exactly to one
without claiming item-level evidence. Their offline gates pass without resuming
Snowflake or bypassing review DLP. `IMP-M3-020` is complete: the private
executor recorded lineage, built and deterministically replayed one immutable
Silver/Gold candidate pair with aggregate-only equivalence evidence, then
suspended the warehouse without touching the active pointer. The current graph
intentionally uses full table materializations; that second build is evidence of
deterministic replay, never incremental processing. A local registration
executor verifies every candidate lifecycle ref before it can append a
definition; a separate transition executor passes an explicit CAS version to one
owner procedure and re-reads the pointer without direct mutation/retry; migration
`008` adds the same eligibility guard inside the owner procedures. On 2026-08-20,
the migration was applied and one private immutable definition was registered
with exact 28 refs and a matching `CREATED` event; the active pointer remains
v0/uninitialized. M3 remains in progress because `IMP-M3-018` still requires
initial activation. A true
rollback cannot target v0's uninitialized sentinel: it needs an already active
prior release and a distinct second release, which requires a separate
owner acceptance/cost decision.
