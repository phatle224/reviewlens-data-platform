# M0 AI and Evaluation Plan

## 1. Model baseline

Các slug được pin, không dùng alias `latest` trong release artifact.

| Use case | Default candidate | Lý do | Gate trước real batch |
|---|---|---|---|
| Enrichment | `google/gemini-2.5-flash-lite` | Chi phí thấp, hỗ trợ structured outputs, phù hợp batch classification/extraction | JSON Schema + semantic golden set |
| RAG answer | `google/gemini-2.5-flash-lite` | Một model ban đầu giúp giảm vận hành/cost | Groundedness/citation/refusal |
| Text-to-SQL | `google/gemini-3.5-flash` | Chất lượng reasoning cao hơn cho SQL; volume tương tác thấp | Semantic + adversarial SQL corpus |
| Embedding | `qwen/qwen3-embedding-8b` | Embedding mới, multilingual, 32K context và chi phí thấp | Dimension/catalog check + Recall@k comparison |

Model catalog và pricing thay đổi theo thời gian. Trước M4/M5, pipeline phải gọi catalog endpoint, xác nhận slug còn tồn tại và snapshot price/context/supported parameters vào evaluation report. Nguồn tham khảo tại ngày M0: [OpenRouter models API](https://openrouter.ai/api/v1/models), [OpenRouter embeddings models API](https://openrouter.ai/api/v1/embeddings/models).

Nếu embedding candidate không đạt retrieval target hoặc provider policy không phù hợp, fallback được evaluation là `openai/text-embedding-3-small`; đổi model tạo `embedding_version` và ChromaDB collection mới.

Compliance gate: mọi OpenRouter live test trước explicit Yelp approval chỉ dùng synthetic reviews/questions. Không gửi raw, redacted hoặc summarized Yelp review text vì bundled Terms hạn chế third-party sharing. Real-data embedding cũng bị chặn theo cùng policy.

### 1.1 Disposition của RAG recommendation

Đã review toàn bộ [`docs/reviewlens_rag_recommendation.md`](../../reviewlens_rag_recommendation.md) trước M1. Tài liệu là design advisory; PRD, ADR, security policy và evaluation gate vẫn có precedence.

Chấp nhận vào P0 baseline:

- Review ngắn mặc định một deterministic chunk; review dài mới sentence-split với overlap và giữ offset/citation mapping.
- Contextual metadata header, strict filter extraction, evidence separation, no-evidence refusal, contradiction handling và claim-level citation.
- ChromaDB chỉ trả `chunk_id + score`; application fetch lại evidence authoritative từ Snowflake `AI.RAG_DOCUMENT` và re-check authorization.
- RAG chỉ trả insight định tính; count/ranking/trend thuộc Text-to-SQL.

Giữ ở dạng evaluation-gated/P1:

- BM25 hybrid retrieval, Reciprocal Rank Fusion và FlashRank `ms-marco-MiniLM-L-12-v2` là optimization candidates. Không thêm vào MVP mặc định trước khi vector + metadata-filter baseline được đo Recall@8/latency và chứng minh chưa đạt gate.
- Nếu promote, phải thêm implementation work items, dependency/footprint test và regression comparison thay vì thay retrieval âm thầm.

Corrections bắt buộc khi implement:

- `text[:1000]` chỉ giới hạn độ dài, không phải redaction. `serving_safe_text` phải đến từ versioned DLP/policy projection và test restricted-field leakage.
- LLM-extracted filter không được dùng trực tiếp; server resolve business name → allowed `business_id`, validate field/operator/value và enforce authorization.
- Không hard-code embedding dimension hoặc pricing từ recommendation. M5 phải đọc catalog/response, pin dimension/config và snapshot price/provider policy.
- Thiết kế và load test theo bounded portfolio corpus; không giả định BM25 in-memory hoặc embedding toàn bộ khoảng 7 triệu reviews.

## 2. Version keys

```text
enrichment_version = hash(model_slug + provider_policy + prompt_version + schema_version + taxonomy_version)
embedding_version  = hash(model_slug + dimensions + input_policy + chunking_version)
index_version      = hash(embedding_version + metadata_policy_version + release_id)
sql_policy_version = hash(prompt_version + semantic_catalog_version + AST_policy_version)
```

## 3. Evaluation datasets

| Set | Minimum MVP | Sampling |
|---|---:|---|
| Enrichment golden | 200 human-reviewed rows ban đầu; mục tiêu 500 | Stratified stars/aspect/length/city |
| Retrieval golden | 50 questions ban đầu; mục tiêu 100 | Answerable/no-evidence/filter/conflict |
| RAG security | ≥40 cases | Prompt injection, malicious review, citation spoofing |
| SQL semantic | ≥50 questions | KPI/filter/time/ranking/ambiguity |
| SQL adversarial | ≥50 cases | DDL/DML, multi-statement, comments, CTE bypass, external function, cost abuse |

Một solo developer có thể label set nhỏ trước, nhưng phải giữ blind holdout tối thiểu 20% để tránh tune vào toàn bộ test set.

## 4. Metrics và gate

| Domain | Metric | Gate ban đầu |
|---|---|---:|
| Sentiment | Macro F1 | ≥0.85 |
| Aspect sentiment | Macro F1 | ≥0.75 |
| Topic | Micro F1 | ≥0.75 |
| Summary/highlights | Schema pass | 100% committed rows |
| Retrieval | Recall@8 | ≥0.85 |
| RAG | Citation precision | 100% accepted factual claims |
| RAG | Refusal precision/recall | ≥0.85 / ≥0.80 |
| Text-to-SQL | Semantic execution accuracy | ≥0.80 baseline, ≥0.90 target |
| Text-to-SQL security | Unsafe query executed | 0 |

## 5. Current-practice safeguards

- Structured outputs + deterministic schema validation; không parse bằng regex.
- Temperature thấp cho enrichment/SQL; seed dùng khi model/provider hỗ trợ nhưng không coi là bảo đảm determinism.
- Golden regression chạy khi model, prompt, taxonomy, chunking, metadata filter hoặc SQL policy đổi.
- AI-as-judge chỉ là một signal; citation/SQL correctness ưu tiên deterministic checks và human review sample.
- Track price snapshot, input/output tokens, retry và duplicate ambiguous calls theo version.
- Không dùng free model endpoint làm release default nếu availability/rate/data policy chưa qua gate.
