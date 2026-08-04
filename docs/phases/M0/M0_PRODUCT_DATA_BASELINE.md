# M0 Product and Data Baseline

| Thuộc tính | Quyết định |
|---|---|
| Product type | Solo portfolio project, single-tenant |
| Default exposure | Local/private; public portfolio chỉ dùng code/architecture/synthetic demo cho đến khi có Yelp approval phù hợp |
| Primary language | English cho data, UI, prompt và evaluation; tài liệu delivery có thể dùng tiếng Việt |
| Warehouse | Snowflake-only từ dev đến portfolio demo |
| Delivery strategy | Business + review vertical slice trước; mở rộng đủ 5 JSON datasets sau D1 |
| AI scope | Deterministic stratified subset, không enrich toàn bộ gần 7 triệu review ở MVP |

## 1. MVP population

### Restaurant scope v1

Normalize `categories` thành case-insensitive trimmed tokens.

| Điều kiện | `restaurant_scope_status` | Lý do |
|---|---|---|
| Có exact token `Restaurants` | `IN_SCOPE` | Yelp parent category xác nhận restaurant |
| Categories non-null nhưng không có `Restaurants` | `OUT_OF_SCOPE` | Không đưa business ngoài restaurant vào product KPI/RAG |
| Categories null/empty/unparseable | `UNKNOWN` | Không đủ bằng chứng để include |

Hybrid business có `Restaurants` cùng category khác vẫn `IN_SCOPE`. `Food` một mình không đủ vì có thể là grocery, market hoặc specialty retail. Rule được version bằng `restaurant_scope_version='restaurant_scope_v1'`.

### AI sampling v1

- D3 đầu tiên: tối đa 2,000 reviews, stratified theo stars, city và review length.
- Portfolio MVP: tối đa 10,000 reviews trừ khi budget gate được nâng.
- Fixed seed và lưu `sample_definition_version` để evaluation/replay tái lập được.
- Chỉ review của `IN_SCOPE` business, qua DLP policy và có valid Silver record mới đủ điều kiện.

## 2. Data modeling decisions

| Domain | Strategy |
|---|---|
| Bronze | Immutable append, raw `VARIANT` + source metadata |
| Business | SCD Type 2 theo `business_id + record_hash`; current row deterministic |
| User | SCD Type 2 nhưng Gold/RAG chỉ giữ pseudonymous ID và field cần thiết |
| Review | Immutable version history theo `review_id + source_record_hash`; correction tạo version mới |
| Check-in | Explode timestamp list ở Silver với deterministic event key |
| Tip | Deterministic hash từ canonical business/user/date/text làm source key nếu source không có ID |
| Attributes | Long-form derived table từ `business.attributes`; version theo business record |
| Deletion | Tombstone chỉ từ complete snapshot hoặc approved correction list; legal purge là controlled exception |

## 3. Time policy

- Không giả định source timestamp naive là UTC.
- Raw string luôn được giữ.
- Parsed naive timestamp dùng Snowflake `TIMESTAMP_NTZ` và `timezone_assumption`.
- Reporting date dùng documented reporting timezone; default MVP là source calendar date khi không thể suy ra timezone.
- Mọi metric time-based phải nêu grain, timezone và late-arrival rule.

## 4. Metric dictionary v1

| Metric | Grain | Công thức baseline | Guardrail |
|---|---|---|---|
| Active businesses | Date/release/filter | Count distinct in-scope `business_id` với `is_open=1` | Hiển thị population version |
| Review count | Date/business/filter | Count valid in-scope reviews | Không dùng AI coverage làm denominator |
| Average stars | Business/release | Average review `stars` | Hiển thị `review_count` |
| Weighted rating | Business/release | Bayesian weighted mean; prior và minimum count config | Không xếp hạng sample quá nhỏ |
| Sentiment distribution | Business/aspect/release | Valid enriched count theo label / valid enriched total | Luôn hiển thị AI coverage |
| Negative aspect rate | Business/aspect/release | Negative aspect rows / reviews có valid aspect label | Không chia cho toàn bộ reviews |
| Check-in count | Business/date | Count exploded check-in events | Deduplicate event key |
| AI coverage | Release/filter | Valid enriched eligible reviews / eligible reviews | Error/reused count tách riêng |

Weighted-rating prior, minimum sample threshold và dashboard comparison window sẽ được tune bằng fixture ở M3; không hard-code trong UI.

## 5. Product acceptance baseline

- Dashboard, RAG và Text-to-SQL luôn pin một `data_release_id`.
- RAG dùng review làm evidence định tính; count/ranking/trend phải đi Text-to-SQL.
- RAG phải từ chối khi không đủ evidence và mọi factual claim phải resolve về serving-safe excerpt.
- SQL chỉ `SELECT`, một statement, curated Gold views, tối đa 1,000 rows và timeout 30 giây.
- Local/private demo có thể dùng local access boundary; trước mọi public deployment phải bật authenticated access và chạy security test suite.
- Không public raw Yelp rows, review excerpts, screenshots có identifiable Yelp Data hoặc dataset-derived metrics khi chưa có approval theo bundled Terms.
