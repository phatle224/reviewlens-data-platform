# ADR-003 — OpenRouter for Chat and Embeddings

- Status: Accepted with model candidates subject to evaluation
- Date: 2026-08-04
- Owner: Solo Developer (AI/Security hats)

## Decision

Use OpenRouter through an OpenAI-compatible Python adapter for enrichment, RAG answer, Text-to-SQL generation and embeddings. Calls run in Airflow/app Python workers, not Snowflake external functions. Pin explicit model slugs and store provider/model/prompt/schema/taxonomy versions with every committed result.

Initial candidates are defined in `docs/phases/M0/M0_AI_EVALUATION_PLAN.md`. Model changes require catalog validation, price snapshot and regression evaluation.

## Consequences

- One API key/provider boundary reduces integration work.
- Underlying providers can differ, so routing/data policy must be explicit and audited.
- Analytics must degrade independently when OpenRouter is unavailable or budget-exhausted.

## Verification

No-key fail-closed test, catalog/model presence, structured-output/schema test, retry/429 test, token/cost ledger and DLP/prompt-injection suite.

