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

Phase status: `IN_PROGRESS` with 15/20 work items complete. Bundles
`IMP-M3-001…015` deliver processing lineage, isolated candidates, Silver/DQ
contracts, five conformed dimensions, four reconciled base facts and a versioned
review-to-item allocation bridge. Four monthly Gold marts apply metric dictionary
v1 only after pre-aggregating incompatible fact grains. Dimension lookups are
version-aware/as-of, review text stays outside Gold, and multi-item review
weights reconcile exactly to one without claiming item-level evidence. Their
offline gates pass without resuming Snowflake or bypassing review DLP. The next
dependency-ready work item is `IMP-M3-016`.
