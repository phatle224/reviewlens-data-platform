# M0 Decision Register

| Decision | Status | Artifact | Thay đổi cần version bump |
|---|---|---|---|
| R2 Standard thay S3 | Accepted | [ADR-001](../../ADR/ADR-001-r2-object-storage.md) | Bucket topology, security boundary, stage protocol |
| Snowflake-only warehouse | Accepted | [ADR-002](../../ADR/ADR-002-snowflake-only-warehouse.md) | Warehouse engine/dialect strategy |
| OpenRouter provider | Accepted | [ADR-003](../../ADR/ADR-003-openrouter-ai-provider.md) | Provider/data policy hoặc default model |
| ChromaDB local | Accepted | [ADR-004](../../ADR/ADR-004-chromadb-vector-store.md) | Vector backend/persistence/security model |
| Full-snapshot batch + atomic release | Accepted baseline | [ADR-005](../../ADR/ADR-005-ingestion-release-strategy.md) | Source semantics/pointer contract |
| Solo local/private deployment | Accepted | [ADR-006](../../ADR/ADR-006-solo-deployment-auth.md) | Public exposure/auth/hosting |
| SCD/time/retention | Accepted baseline | [ADR-007](../../ADR/ADR-007-scd-time-retention.md) | Correction/deletion/time/Terms policy |
| JSON source set | 5 required + 1 derived + photo optional | [Source profile](./M0_SOURCE_PROFILE.md) | Extracted archive chứng minh khác baseline |
| Restaurant population | Exact normalized token `Restaurants` | [Product/data baseline](./M0_PRODUCT_DATA_BASELINE.md) | Taxonomy inclusion rule |
| AI workload | 2,000-review pilot; 10,000-review portfolio cap | [Product/data baseline](./M0_PRODUCT_DATA_BASELINE.md) | Budget/sample policy |
| Yelp Terms | Real data giữ local; cloud/LLM transfer và public data/metrics denied đến khi eligibility/Yelp approval rõ ràng | [Security/privacy](./M0_SECURITY_PRIVACY.md) | New written permission hoặc qualified review |
| M1 cloud topology | Snowflake Standard trên AWS Singapore + private R2 Standard bucket tại APAC qua S3-compatible stage | [User inputs](./M0_USER_INPUTS.md), [ADR-001](../../ADR/ADR-001-r2-object-storage.md) | Đổi Snowflake region/cloud, R2 location/jurisdiction hoặc stage protocol |
| RAG recommendation | Đã review; P0 safeguards được chấp nhận, hybrid/reranking giữ evaluation-gated/P1 | [AI evaluation](./M0_AI_EVALUATION_PLAN.md), [recommendation](../../reviewlens_rag_recommendation.md) | Promote optimization vào MVP hoặc đổi retrieval/model contract |

## M1 entry input status

Không ghi secret trong tài liệu. Trạng thái hiện tại:

1. `RESOLVED`: Snowflake account facts và R2 bucket topology.
2. `RESOLVED_RESTRICTIVE`: project không thuộc chương trình academic chính thức và không có Yelp approval; synthetic-only gate cho managed cloud/external AI/public demo được giữ nguyên.
3. `OPEN_NON_BLOCKING`: public URL strategy, explicit budget acceptance và model candidate acceptance.
4. `OPEN_BEFORE_REAL_LOCAL_USE`: Yelp dataset access/effective date để tính license expiry/cleanup.
