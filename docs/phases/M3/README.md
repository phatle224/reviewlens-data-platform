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

Phase status: `IN_PROGRESS` with 19/20 work items complete and `IMP-M3-020`
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
Snowflake or bypassing review DLP. `IMP-M3-020` now has the fail-closed
aggregate-only comparison engine and operations runbook, but the final drill
remains pending until a true incremental dbt materialization is implemented;
the current graph contains only full table materializations.
