# M0 Capacity, SLO and Budget Baseline

## 1. Capacity envelope

| Stage | Data envelope | Mục tiêu |
|---|---|---|
| D1 fixture | 100 orders, related customers/items/payments/products/sellers and reviews | Fast deterministic CI/integration |
| D2 vertical slice | 10,000 orders with relational children | Validate ingestion/dbt/dashboard design |
| D3 AI pilot | Tối đa 2,000 stratified reviews | Tune schema, prompt, rate/cost |
| Portfolio MVP | Full nine-CSV ingest nếu Snowflake runway cho phép; tối đa 10,000 AI-enriched comments | Portfolio demonstration |
| Scale gate | Named full release, AI subset vẫn bounded | Prove streaming/idempotency without full LLM cost |

Không dùng Pandas để load toàn bộ CSV lớn. Parser/writer phải streaming/chunked và memory được đo trên representative large chunk.

## 2. Cost guardrails

| Service | Baseline | Warning | Hard/degrade action |
|---|---|---|---|
| Cloudflare R2 | Standard class; target ≤15 GB stored | 10 GB hoặc 80% cap | Không tạo duplicate raw artifact; pause new backfill ở cap |
| Snowflake | `X-SMALL`, `AUTO_SUSPEND=60`, `AUTO_RESUME=TRUE`; target ≤10 credits/tháng portfolio | 50% và 80% monitor | Suspend warehouse ở 100%; query manual restore bằng explicit action |
| OpenRouter | Project budget mặc định 5 USD; daily 0.50 USD | 50%/80% budget | Disable new AI jobs ở 100%; analytics vẫn hoạt động |
| AI batch | 2,000 reviews/pilot, concurrency ban đầu 2 | 80% estimated job budget | Không submit batch mới; committed results được giữ |
| ChromaDB | ≤5 GB local disk cho MVP | 80% disk budget | GC non-active collections theo retention; không xóa active/rollback |

Olist source snapshot hiện khoảng 124 MB. Kể cả source, Parquet và manifest,
capacity vẫn phải được đo và không được giả định vĩnh viễn miễn phí. Nguồn:
[Cloudflare R2 pricing](https://developers.cloudflare.com/r2/pricing/).

Snowflake expiry và credit thực tế phải được ghi từ account trước M1. Resource monitor chỉ kiểm soát warehouse credit; storage/serverless usage phải theo dõi riêng.

Account facts xác nhận ngày `2026-08-04`: Snowflake Standard Edition trên AWS Singapore (`AWS_AP_SOUTHEAST_1`), trial balance hiển thị `US$400`, hết hạn `2026-09-03`. Khoản balance không thay hard guardrail 10 credits/tháng cho đến khi owner explicit điều chỉnh; ưu tiên M2 Olist vertical slice trước expiry.

## 3. SLO baseline

| SLO | Target MVP | Measurement |
|---|---:|---|
| Ingestion reconciliation | 100% explained physical records | accepted + quarantined + parse-failed |
| Replay duplicate committed effect | 0 | R2/Bronze/Silver/Gold/AI/vector counts |
| Critical dbt tests | 100% pass trước publish | dbt artifacts |
| AI valid output rate | ≥99% trên submitted eligible batch sau bounded retry | invocation ledger |
| Embedding/index coverage | ≥99.9% valid RAG documents | Snowflake expected map vs ChromaDB |
| Citation resolution | 100% factual claims trong accepted RAG answer | RAG evaluation |
| RAG groundedness | ≥90% trên golden set; tune ở M5 | evaluator + human sample |
| SQL unsafe execution | 0 | adversarial suite dưới service role |
| Dashboard p95 | ≤5 giây warm trên portfolio workload | app telemetry |
| RAG p95 | ≤12 giây warm | request telemetry |
| Text-to-SQL p95 | ≤15 giây warm | generation + validation + query |

SLO là baseline để đo và tune, không phải tuyên bố production SLA. Cold-start metrics được báo tách nhưng không bị giấu khỏi portfolio performance report.

## 4. Operational degrade rules

- OpenRouter unavailable/budget exhausted: dashboard và Text-to-SQL execution trên approved SQL vẫn hoạt động; AI generation báo unavailable.
- ChromaDB unavailable: RAG báo unavailable, không fallback sang ungrounded LLM answer.
- Snowflake suspended/expired: app báo data backend unavailable; không dùng mock data như dữ liệu thật.
- R2 unavailable: không ingest batch mới; active Snowflake release tiếp tục phục vụ.
