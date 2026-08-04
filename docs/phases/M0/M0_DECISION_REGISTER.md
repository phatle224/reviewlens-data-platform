# M0 Decision Register

| Decision | Status | Artifact | Version-bump trigger |
|---|---|---|---|
| R2 Standard replaces S3 | Accepted | [ADR-001](../../ADR/ADR-001-r2-object-storage.md) | Bucket/security/stage protocol changes |
| Snowflake-only warehouse | Accepted | [ADR-002](../../ADR/ADR-002-snowflake-only-warehouse.md) | Engine/dialect strategy changes |
| OpenRouter provider | Accepted | [ADR-003](../../ADR/ADR-003-openrouter-ai-provider.md) | Provider/data policy/default model changes |
| ChromaDB local | Accepted | [ADR-004](../../ADR/ADR-004-chromadb-vector-store.md) | Vector backend/persistence/security changes |
| Complete-snapshot + atomic release | Accepted | [ADR-005](../../ADR/ADR-005-ingestion-release-strategy.md) | Source/pointer semantics change |
| Solo local/private deployment | Accepted | [ADR-006](../../ADR/ADR-006-solo-deployment-auth.md) | Public exposure/auth/hosting change |
| Single-local config | Accepted | `config/config.toml` | A real second environment is introduced |
| Snapshot history/time/retention | Accepted | [ADR-007](../../ADR/ADR-007-scd-time-retention.md) | Correction/deletion/time policy changes |
| Olist is the only active source | Accepted, supersedes Yelp baseline | [ADR-008](../../ADR/ADR-008-olist-primary-dataset.md) | Dataset/source/license changes |
| Source contract | Exactly nine required relational CSVs | [Source profile](./M0_SOURCE_PROFILE.md) | Filename/header/requiredness changes |
| Analytical population | Versioned order scope; delivered core, cancelled operational only | [Product/data baseline](./M0_PRODUCT_DATA_BASELINE.md) | Scope rule changes |
| License/compliance | CC BY-NC-SA 4.0; attribution + NonCommercial + ShareAlike | [Attribution](../../DATA_ATTRIBUTION.md) | License/source/publication changes |
| AI workload | 2,000-review pilot; 10,000-review portfolio cap | [AI evaluation](./M0_AI_EVALUATION_PLAN.md) | Budget/sample policy changes |
| Cloud topology | Snowflake AWS Singapore + private APAC R2 through S3-compatible stage | [User inputs](./M0_USER_INPUTS.md) | Cloud/region/jurisdiction/protocol changes |

## Migration decision — 2026-08-05

The earlier Yelp source and restrictive academic-eligibility decision are
superseded. Ignored local Yelp files may remain for owner-controlled cleanup but
are not an active input. ReviewLens keeps its name and changes domain to
e-commerce review/delivery intelligence. Config, fixtures, tests, Snowflake CSV
format, PRD, implementation plan, phase artifacts and architecture diagram must
follow the Olist contract.
