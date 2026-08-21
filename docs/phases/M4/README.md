# M4 — DLP-approved review enrichment

M4 turns a private, eligible Olist review into a versioned structured enrichment
only after a fail-closed DLP/minimization projection. Base review facts remain
independent of AI coverage. No raw review text, natural identifier, prompt body,
provider response body, embedding or row-level output may enter Git, public
evidence, or an audit ledger.

| Artifact | Purpose |
|---|---|
| [M4 checklist](./M4_CHECKLIST.md) | Status and evidence for all 15 M4 items |
| [M4 test cases](./M4_TEST_CASES.md) | Contract, privacy, replay, cost and later live gates |
| [Implementation plan](../../IMPLEMENTATION_PLAN.md) | Dependencies and acceptance criteria |
| [ADR-016](../../ADR/ADR-016-m4-enrichment-contract-and-dlp-projection.md) | Frozen output and transfer contract |
| [M0 security/privacy baseline](../M0/M0_SECURITY_PRIVACY.md) | DLP-before-AI and retention boundary |

Phase status: `IN_PROGRESS` with 8/15 work items complete and one partial. The first three bundles
freeze the schema/taxonomy/version-key contract, append-only enrichment ledgers,
a minimized review-text projection, catalog evidence, deterministic selection and
a Portuguese prompt that isolates untrusted evidence, schema/semantic validation,
one repair, bounded retry and quarantine/resume. The structured provider path has
fake coverage and an unexecuted opt-in synthetic smoke; it does not select real
rows, call chat/completion OpenRouter APIs, apply Snowflake migration `009`,
persist an AI result or write an embedding. Those actions remain gated by the
following M4 work items and the approved DLP projection.
