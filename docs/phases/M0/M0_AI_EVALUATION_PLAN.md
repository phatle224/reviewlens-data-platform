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
