# ReviewLens project map

Use this as a routing guide, not as a replacement for the live project documents.

## Canonical files

| Need | Read/update |
|---|---|
| One-page current state | `docs/PROJECT_STATUS.md` |
| Product scope and requirements | `docs/PRD.md` |
| Phase ordering and work items | `docs/IMPLEMENTATION_PLAN.md` |
| Per-item progress and evidence | `docs/phases/Mx/Mx_CHECKLIST.md` |
| Test design and executed results | `docs/phases/Mx/Mx_TEST_CASES.md` |
| Material technical decisions | `docs/ADR/ADR-*.md` |
| M0 accepted decisions | `docs/phases/M0/M0_DECISION_REGISTER.md` |
| Data/privacy boundary | `docs/phases/M0/M0_SECURITY_PRIVACY.md` |
| Budget and SLO | `docs/phases/M0/M0_SLO_BUDGET.md` |
| AI evaluation gates | `docs/phases/M0/M0_AI_EVALUATION_PLAN.md` |
| RAG design advisory | `docs/reviewlens_rag_recommendation.md` — read before M5/AI work; PRD/ADR/evaluation gates take precedence |

## Frozen baseline

- Solo portfolio project; role names represent responsibility hats.
- Cloudflare R2 Standard object storage, private by default.
- Snowflake-only warehouse from development through portfolio demo.
- Airflow batch orchestration and dbt-snowflake transformations.
- OpenRouter for chat and embeddings through application-side adapters.
- Local persistent, versioned ChromaDB index.
- Streamlit consumption layer.
- One local runtime with versioned non-secret `config/config.toml`; credentials come only from process environment/ignored `.env`. No staging/production profiles in current scope.
- Real Yelp data remains local while the Terms/approval gate is closed; cloud, external AI, CI, and public artifacts use synthetic fixtures.

## Phase order

`M0` decisions → `M1` foundation → `M2` ingestion/Bronze → `M3` Silver/Gold/releases → `M4` enrichment → `M5` embeddings/RAG → `M6` Text-to-SQL → `M7` application → `M8` hardening/launch.

Do not skip an unmet upstream gate. A downstream scaffold may use fakes only when the implementation plan explicitly allows it.

Before RAG implementation, read the RAG design advisory and its disposition in `M0_AI_EVALUATION_PLAN.md`. Do not silently promote hybrid retrieval/reranking from P1 or treat truncation as redaction.
