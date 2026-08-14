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

Phase status: `IN_PROGRESS` with 6/20 work items complete. The first two bundles,
`IMP-M3-001…006`, deliver processing lineage, isolated candidates, complete dbt
Bronze contracts and the customer/geolocation/order Silver slice. Their offline
gates pass without resuming Snowflake. The next dependency-ready bundle is
`IMP-M3-007…009`.
