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

Phase status: `IN_PROGRESS` with 13/15 work items complete and two partial. The first three bundles
freeze the schema/taxonomy/version-key contract, append-only enrichment ledgers,
a minimized review-text projection, catalog evidence, deterministic selection and
a Portuguese prompt that isolates untrusted evidence, schema/semantic validation,
one repair, bounded retry and quarantine/resume. The structured provider path has
fake coverage and an unexecuted opt-in synthetic smoke; it does not select real
rows, call chat/completion OpenRouter APIs, apply Snowflake migration `009`,
persist an AI result or write an embedding. Those actions remain gated by the
following M4 work items and the approved DLP projection. The local synthetic
provider smoke is now protected by a durable, aggregate-only cost reservation
ledger using the catalog-pinned price snapshot: it warns at 0.50 USD/day and
stops a new call before the 5 USD project cap. It remains opt-in and unexecuted.
Validated output now has a private current-result contract and an aggregate-only
coverage projection, while `FACT_REVIEW_BASE` stays independent of AI coverage.
The corresponding Snowflake DDL is offline-validated only and is not applied.
The evaluator contract is also complete offline. Its real private human-reviewed
golden set now has 200 approved labels and a deterministic 40-item blind holdout,
but no private model predictions or aggregate metric report yet exist; therefore
the evaluation work item and real quality gate remain partial.
The quality-gate contract already rejects a bad, missing-evaluation or
version-mismatched AI candidate before any publish callback runs; the actual
Snowflake release transition will not be wired until a private golden report
exists. The local observability contract has a reproducible aggregate-only
dashboard payload for terminal token/cost/latency/error/coverage data. It
reconciles exactly to the committed budget and current valid-enrichment
coverage, and fails closed on ledger/version drift without retaining raw text,
prompt, response, natural identifier or row-level result.
The recovery runbook now defines pause/triage, bounded retryable resume,
versioned model change and fail-closed purge-request procedures. Its executed
evidence is synthetic tabletop only, so it does not replace the pending provider
smoke, private golden evaluation or guarded live release integration.
A 200-row private annotation pack now exists under ignored
`private_evaluation/m4_enrichment_v1/`; it is intentionally not evidence of a
golden evaluation until the solo developer completes the human labels and
validates the blind holdout using the annotation runbook.
An owner-authorized offline score/delivery heuristic has populated a separate
`machine_assisted` suggestion file, but the loader rejects it as human-golden
evidence until each row is reviewed and explicitly approved.

## Latest private pilot evidence

The owner-authorized 40-item prediction run on 2026-08-23 stopped fail-closed
with `AI_ENRICHMENT_SCHEMA_INVALID`. It created neither private predictions nor
an aggregate report; a recovery dispatch is a new cost-bearing owner decision.
The offline recovery path now uses prompt v2 and permits exactly one schema-only
repair per invalid DLP-approved item; a second invalid response still stops the
batch without a partial report or public artifact.
