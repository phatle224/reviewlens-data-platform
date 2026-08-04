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

## Inputs còn phải xác minh

Không ghi secret trong tài liệu. Chỉ cần các giá trị không nhạy cảm sau để đóng M0:

1. Snowflake account cloud/region/edition, expiry date và remaining credit hiển thị trong account.
2. Cloudflare R2 account đã bật hay chưa; bucket name và location/jurisdiction mong muốn.
3. Portfolio chỉ local/private hay cần public URL.
4. Monthly budget mong muốn; default hiện tại là tối đa 5 USD OpenRouter và 10 Snowflake credits/tháng trong giai đoạn build.
5. Chấp nhận model candidates và AI sample cap trong evaluation plan hay muốn đổi.
6. Xác nhận project này thuộc ongoing academic course/qualified academic use hay bạn có Yelp written approval. Nếu không, M1+ chỉ dùng synthetic data trên R2/Snowflake/OpenRouter và real Yelp data chỉ được profile local trong phạm vi Terms cho phép.
