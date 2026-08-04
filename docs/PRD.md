# PRD — ReviewLens Data Platform

> AI-Powered Yelp Restaurant Intelligence Platform

| Thuộc tính | Giá trị |
|---|---|
| Phiên bản | 1.1 |
| Trạng thái | Draft đã đồng bộ kiến trúc cost-optimized cho solo implementation |
| Ngày cập nhật | 2026-08-04 |
| Nguồn đầu vào | [Sơ đồ kiến trúc](./images/plan.png) |
| Product Owner | Solo Developer |
| Technical Owner | Solo Developer |

Tài liệu này chuyển sơ đồ kiến trúc thành yêu cầu sản phẩm có thể dùng để thiết kế, phát triển, kiểm thử và nghiệm thu. Các giá trị định lượng trong PRD là baseline đề xuất cho MVP; chúng được dùng làm tiêu chí mặc định cho đến khi Product Owner phê duyệt giá trị khác.

Trong tài liệu:

- **Bắt buộc / MUST**: điều kiện phải có để nghiệm thu MVP.
- **Nên / SHOULD**: yêu cầu có giá trị cao nhưng có thể lùi sau MVP nếu được phê duyệt.
- **Có thể / MAY**: hướng mở rộng.
- **P0 = MUST**, **P1 = SHOULD**, **P2 = MAY**. Yêu cầu “P0 trước dữ liệu thật/production” là gate bắt buộc tại thời điểm được nêu, không phải yêu cầu tùy chọn.

---

## 1. Tóm tắt sản phẩm

ReviewLens là nền tảng dữ liệu và AI end-to-end biến Yelp Open Dataset từ các file JSON/JSONL thô thành:

1. Dữ liệu đáng tin cậy theo kiến trúc Medallion trên Snowflake.
2. Các business mart phục vụ phân tích nhà hàng theo thời gian, địa điểm và danh mục.
3. Review đã được LLM làm giàu với sentiment, aspect sentiment, chủ đề, tóm tắt và điểm nổi bật.
4. Dashboard BI cho analyst và business user.
5. RAG chatbot trả lời câu hỏi định tính dựa trên review và luôn kèm nguồn.
6. Text-to-SQL cho câu hỏi định lượng, chỉ thực thi truy vấn đọc an toàn trên Gold semantic views.

Cloudflare R2 Standard là data lake/landing zone thông qua API tương thích S3; Snowflake là warehouse duy nhất cho development và portfolio demo, đồng thời cung cấp storage và compute cho Bronze/Silver/Gold; dbt quản lý mọi transformation từ Bronze sang Silver và Gold; Apache Airflow điều phối pipeline; Streamlit là giao diện MVP; OpenRouter được dùng qua lớp provider adapter cho enrichment, embedding và answer/SQL generation; ChromaDB chạy local là vector store duy nhất của MVP.

### 1.1 Vấn đề cần giải quyết

- Dữ liệu Yelp thô lớn, lồng nhau và khó dùng trực tiếp cho analytics.
- Cùng một khái niệm có thể xuất hiện dưới nhiều dạng, có null, duplicate, orphan relation hoặc schema drift.
- Nội dung review tự do chưa cung cấp sẵn insight về cảm xúc, món ăn, dịch vụ, giá và không gian.
- Người dùng nghiệp vụ cần insight mà không phải hiểu cấu trúc dữ liệu hoặc tự viết SQL.
- Kết quả AI cần được truy vết về dữ liệu nguồn, đo chất lượng, kiểm soát chi phí và bảo vệ khỏi prompt injection/hallucination.
- Pipeline cần hỗ trợ replay, backfill và lỗi từng phần mà không làm mất hoặc nhân đôi dữ liệu.

### 1.2 Tầm nhìn

Tạo một nguồn dữ liệu nhà hàng duy nhất, có kiểm thử và lineage rõ ràng, để cả người dùng kỹ thuật lẫn phi kỹ thuật có thể khám phá xu hướng và phản hồi khách hàng một cách an toàn, giải thích được và lặp lại được.

---

## 2. Mục tiêu, ngoài phạm vi và nguyên tắc

### 2.1 Mục tiêu sản phẩm

| ID | Mục tiêu |
|---|---|
| G-01 | Ingest được toàn bộ dataset theo batch, idempotent và có đối soát từng file/từng record. |
| G-02 | Xây dựng Bronze → Silver → Gold có data contract, dbt tests, audit và lineage. |
| G-03 | Làm giàu review theo kiểu incremental, structured output, có model/prompt version và error handling. |
| G-04 | Cung cấp KPI nhất quán về business, city, category, rating, review, check-in, sentiment, aspect và topic. |
| G-05 | RAG trả lời câu hỏi định tính có citation đúng, đồng thời từ chối khi không đủ bằng chứng. |
| G-06 | Text-to-SQL trả lời câu hỏi định lượng mà không thể ghi dữ liệu hoặc truy cập object ngoài allowlist. |
| G-07 | Theo dõi freshness, chất lượng, latency, lỗi, token, Snowflake credit, storage và embedding cost. |
| G-08 | Có CI/CD, RBAC, secrets management, runbook và môi trường tách biệt để vận hành lặp lại được. |

### 2.2 Ngoài phạm vi MVP

- Crawl Yelp hoặc tích hợp trực tiếp với Yelp production API.
- Streaming hoặc near-real-time; MVP là batch.
- Cho phép người dùng tạo, sửa hoặc xóa business/review từ ứng dụng.
- Recommendation cá nhân hóa hoặc xếp hạng quảng cáo.
- Huấn luyện foundation model riêng.
- Phân tích nội dung ảnh; MVP chỉ ingest `photo.json` và metadata.
- Public multi-tenant SaaS, billing và tenant isolation.
- Tự động ra quyết định thay người vận hành nhà hàng.
- Dùng RAG để tính toán chính xác các câu hỏi count, trend hoặc ranking; loại câu hỏi này thuộc Text-to-SQL.

### 2.3 Nguyên tắc kiến trúc bắt buộc

1. Bronze mặc định immutable và không bị update/delete bởi pipeline thông thường.
2. Snowflake là warehouse duy nhất của dự án từ development đến portfolio demo; không duy trì DuckDB hoặc warehouse fallback song song. Mọi transformation Silver và Gold được định nghĩa trong dbt và thực thi trên Snowflake.
3. Airflow là control plane; dữ liệu không được truyền qua Airflow task payload ngoài metadata nhỏ.
4. AI enrichment nằm giữa Silver và Gold; chỉ record hợp lệ mới được promote vào mart.
5. OpenRouter chat/embedding calls chạy trong Python worker do Airflow/app điều phối, không chạy qua Snowflake external function; kết quả đã validate mới được ghi lại Snowflake/ChromaDB.
6. Review và kết quả retrieve là dữ liệu không tin cậy, không phải instruction cho LLM.
7. Generated SQL không bao giờ được chạy chỉ vì LLM tạo ra; nó phải qua parser, policy validator và role chỉ đọc.
8. Không có record nào bị bỏ qua âm thầm: mọi input phải được load hoặc quarantine với lý do.
9. Mọi output quan trọng phải truy vết được về source, batch, code, model, prompt và query liên quan.

### 2.4 Chỉ số giá trị sản phẩm

Product Owner phải đặt target tại M0 và review sau pilot cho:

| Metric | Định nghĩa |
|---|---|
| Weekly active users | Số actor duy nhất thực hiện ít nhất một meaningful dashboard/RAG/SQL action mỗi tuần |
| Task completion rate | Tỷ lệ task trong pilot script đạt insight đúng mà không cần can thiệp từ data engineer |
| Useful-answer rate | Tỷ lệ RAG response được đánh giá hữu ích trên feedback hợp lệ; luôn kèm response rate |
| SQL zero-repair success | Tỷ lệ supported questions có semantic result đúng ngay lần generation đầu |
| Time-to-insight | Thời gian từ submit question/filter đến khi người dùng xem result/citation hữu dụng |
| Repeat usage | Tỷ lệ pilot user quay lại sử dụng trong tuần kế tiếp |

Telemetry chỉ thu thập sau privacy review, dùng actor pseudonymous và không lưu raw question/answer ngoài approved retention.

---

## 3. Người dùng mục tiêu và nhu cầu

| Persona | Nhu cầu chính | Quyền điển hình |
|---|---|---|
| Data Engineer | Ingest, replay/backfill, xử lý schema drift, theo dõi DAG và quarantine | Vận hành pipeline; không mặc định xem dữ liệu nhạy cảm ở UI |
| Analytics Engineer | Phát triển dbt model, test, metric, docs và lineage | Đọc Bronze; CRUD Silver/Gold qua service role |
| Data Analyst | Khám phá mart, tạo báo cáo và kiểm tra kết quả | Read-only Gold |
| Restaurant/Business Analyst | Hiểu rating, sentiment, vấn đề dịch vụ/món ăn và xu hướng | Dashboard, RAG, Text-to-SQL |
| Người dùng phi kỹ thuật | Đặt câu hỏi tự nhiên và nhận câu trả lời dễ hiểu | Chỉ qua ứng dụng và policy đã cấu hình |
| Platform/Security Admin | Quản lý role, secrets, chi phí, audit, incident và retention | Quyền quản trị tách biệt, được audit |
| Product Owner | Theo dõi adoption, chất lượng AI, SLO và giá trị nghiệp vụ | Dashboard sản phẩm và báo cáo chất lượng |

### 3.1 User stories trọng tâm

| ID | User story |
|---|---|
| US-01 | Là Data Engineer, tôi muốn chạy lại cùng batch mà không sinh duplicate để recovery an toàn. |
| US-02 | Là Data Engineer, tôi muốn biết file/record nào lỗi, lỗi ở bước nào và cách replay. |
| US-03 | Là Analytics Engineer, tôi muốn tất cả metric có công thức, grain, timezone và test để dashboard và AI cho cùng một kết quả. |
| US-04 | Là Analyst, tôi muốn so sánh hiệu suất business theo thời gian, city và category. |
| US-05 | Là Business User, tôi muốn hỏi “Khách hàng thường phàn nàn gì về dịch vụ của nhà hàng X?” và nhận câu trả lời kèm review nguồn. |
| US-06 | Là Business User, tôi muốn hỏi “Top 10 nhà hàng Italian theo sentiment trong quý gần nhất là gì?” và nhận bảng/biểu đồ từ dữ liệu Gold. |
| US-07 | Là Security Admin, tôi muốn mọi truy vấn do AI tạo chỉ đọc curated views và bị giới hạn chi phí/thời gian. |
| US-08 | Là Product Owner, tôi muốn so sánh chất lượng và chi phí giữa các model/prompt version trước khi rollout. |

---

## 4. Phạm vi phát hành

### 4.1 P0 — MVP bắt buộc

- Batch ingestion, validation, Cloudflare R2 landing, manifest, audit, quarantine và idempotency.
- Snowflake Bronze, Silver, Gold; dbt models, tests và docs.
- LLM enrichment cho review; validation, retry, error table và versioning.
- Embedding và một vector store duy nhất.
- Streamlit dashboard với KPI/filter cốt lõi.
- RAG chatbot định tính có citation.
- Text-to-SQL định lượng có AST guardrails và read-only role.
- Airflow DAG end-to-end, logs, metrics, notifications và backfill.
- RBAC, secrets, privacy baseline, cost tracking và CI/CD.
- Bộ evaluation cho enrichment, RAG và Text-to-SQL.

### 4.2 P1 — Sau MVP

- Automatic intent router giữa RAG, Text-to-SQL và câu hỏi hybrid.
- Reranking, query rewrite và hội thoại nhiều lượt nâng cao cho RAG.
- Enterprise SSO/group provisioning nâng cao nếu MVP dùng authenticated reverse proxy hoặc IdP đơn giản; production vẫn không được anonymous.
- Kết nối thêm Power BI/Tableau hoặc công cụ BI được chọn.
- Data anomaly detection nâng cao và automated remediation có kiểm soát.
- Hỗ trợ tiếng Việt được đánh giá chính thức nếu MVP chỉ dùng tiếng Anh.

### 4.3 P2 — Tương lai

- Multi-tenant/public product.
- Near-real-time ingestion.
- Phân tích ảnh và multimodal search.
- Recommendation/prediction hoặc fine-tuned model.
- Tích hợp nguồn dữ liệu nhà hàng khác.

---

## 5. Giả định và quyết định mặc định cho MVP

Các quyết định dưới đây giúp solo developer có thể bắt đầu. Những mục có nhãn **P0-confirm** phải được ghi thành quyết định/ADR trước khi đóng technical design; các role khác trong tài liệu là “mũ trách nhiệm” do cùng một người đảm nhiệm, không hàm ý có team riêng.

| Chủ đề | Mặc định MVP | Trạng thái |
|---|---|---|
| Loại sản phẩm | Ứng dụng analytics nội bộ, single-tenant | P0-confirm |
| Cadence nguồn | Ingest khi có source release; scheduler có thể chạy hằng ngày để phát hiện batch mới, nhưng không giả định Yelp thật sự phát hành increment mỗi ngày | P0-confirm |
| Semantics nguồn | Source snapshot được fingerprint; pipeline suy ra new/changed rows bằng checksum/hash. Không coi append-only là đủ để chống trùng | P0-confirm |
| Ảnh | Chỉ xử lý metadata trong `photo.json`, không lưu/xử lý binary image | Đã chọn cho MVP |
| Business attributes | Nếu không có `attributes.json` độc lập, tách nested `attributes` từ `business.json` thành contract tương đương | P0-confirm sau khi xem package thật |
| Object storage | Cloudflare R2 Standard, private bucket, scoped API token và S3-compatible endpoint; không dùng AWS S3 | Đã chọn cho MVP |
| Warehouse | Snowflake dùng ngay từ development và là warehouse duy nhất; không có DuckDB fallback | Đã chọn cho MVP |
| Snowflake trial | Owner cung cấp account/trial; ngày hết hạn và credit thực tế phải đọc từ chính account và ghi vào runbook. Kiến trúc không phụ thuộc advertised trial duration | P0-verify |
| Bronze loader | Airflow-managed batch `COPY INTO` từ R2 external stage; không dùng auto-refresh/Snowpipe cho MVP | Đã chọn cho MVP |
| Vector store | ChromaDB chạy local, persistent volume riêng, một collection vật lý theo `index_version`; không dùng Cortex Search hoặc pgvector trong MVP | Đã chọn cho MVP |
| UI | Streamlit; Snowsight dùng cho analyst kỹ thuật | Mặc định |
| Ngôn ngữ | Dữ liệu review tiếng Anh; UI/query tiếng Anh ở MVP. Ngôn ngữ khác chỉ bật sau evaluation riêng | P0-confirm |
| Timezone | Giữ raw timestamp/offset. Chỉ đổi sang UTC khi source có offset hoặc mapping đáng tin; timestamp naive dùng `TIMESTAMP_NTZ` + `timezone_assumption`. Reporting timezone phải hiển thị rõ | P0-confirm trong data contract |
| LLM | OpenRouter là provider; model slug cấu hình qua environment, không hard-code; thay model phải chạy regression evaluation | Đã chọn provider, model P0-confirm |
| Embedding | OpenRouter Embeddings API; model slug phải được xác nhận có trong embedding catalog, pin cùng `embedding_version` và dimension lấy từ response/config | Đã chọn provider, model P0-confirm |
| AI publish gate | Permanent enrichment error >1% của batch chặn toàn bộ release mới; ứng dụng tiếp tục dùng release đã publish gần nhất | Baseline cần duyệt |
| AI confidence/retry | Confidence threshold 0.70; tối đa 3 total attempts với tối đa 1 schema-repair attempt | Baseline cần tune trên golden set |
| Topic taxonomy | Closed, versioned taxonomy với `other/unknown`; label set được khóa từ sample thật ở M0, không cho free-form topic ở MVP | Baseline |
| RAG retrieval | `top_k=8` trước reranking; tune bằng Recall@k/latency evaluation | Baseline |
| Text-to-SQL execution | 1 statement, max 1.000 rows, 30 giây statement timeout, tối đa 1 repair; scan/credit cap chốt ở M0 | Baseline |
| User data | Hash/pseudonymize `user_id`; không đưa tên, friends hoặc trường user không cần thiết vào RAG/Gold public views | Mặc định bảo mật |

### 5.1 Điều kiện P0 phải được xác nhận trước production

1. License/Terms của Yelp cho mục đích sử dụng dự kiến, gồm lưu review, tạo embedding, gửi text tới LLM và hiển thị citation.
2. Manifest và schema thật của source package; đặc biệt `attributes.json`, photo metadata và cơ chế release.
3. Cloudflare R2 jurisdiction/location, Snowflake cloud/region, cross-cloud latency và chính sách retention/training của OpenRouter/model provider.
4. Nơi chạy Airflow/Streamlit/ChromaDB, persistent volume, container registry và network topology.
5. Monthly budget và quota cho Snowflake, R2, OpenRouter chat/embedding và local storage.
6. App authentication, nhóm người dùng và yêu cầu SSO/RLS/masking.

---

## 6. Luồng trải nghiệm và luồng hệ thống

### 6.1 Luồng batch dữ liệu

```text
Yelp JSON/JSONL
  → validate + manifest + checksum
  → archive source + Parquet/Snappy trên Cloudflare R2
  → Snowflake Bronze (raw VARIANT + metadata)
  → dbt Silver (typed, cleaned, deduplicated, conformed)
  → OpenRouter LLM enrichment + JSON/schema/semantic validation
  → OpenRouter embeddings + versioned ChromaDB collection
  → dbt Gold (dimensions, facts, marts)
  → dashboard / RAG / Text-to-SQL
```

Airflow gọi và theo dõi các job trên; Airflow không phải nơi lưu hoặc chuyển payload dữ liệu lớn.

### 6.2 Luồng RAG định tính

1. Người dùng nhập câu hỏi về nội dung/ý kiến trong review.
2. Ứng dụng xác thực người dùng, chuẩn hóa câu hỏi và trích xuất filter.
3. Vector search lấy review/chunk phù hợp trong phạm vi quyền.
4. LLM chỉ dùng evidence đã retrieve để tạo câu trả lời.
5. Câu trả lời hiển thị citation tới business, `review_id`, source release và excerpt.
6. Nếu evidence yếu/không có, hệ thống nói rõ không đủ dữ liệu thay vì đoán.

### 6.3 Luồng Text-to-SQL định lượng

1. Người dùng nhập câu hỏi count, average, trend, comparison hoặc ranking.
2. LLM nhận semantic catalog đã allowlist và sinh một câu SQL ứng viên.
3. SQL parser tạo AST; policy engine kiểm tra statement, table, column, function, join, cost, timeout và row limit.
4. SQL hợp lệ được chạy bằng `TEXT_TO_SQL_ROLE` trên warehouse riêng.
5. Ứng dụng hiển thị SQL thực tế, table/chart, freshness và query ID.
6. Câu hỏi mơ hồ phải yêu cầu làm rõ; câu hỏi trái policy bị từ chối và audit.

### 6.4 Phân tách loại câu hỏi trong MVP

- Tab **Ask Reviews (RAG)** dành cho câu hỏi định tính như “khách phàn nàn điều gì”.
- Tab **Ask Data (Text-to-SQL)** dành cho câu hỏi định lượng như “top 10”, “bao nhiêu”, “xu hướng”.
- Dashboard dành cho KPI lặp lại.
- Automatic router là P1; RAG không được tự suy luận số liệu tổng hợp từ một mẫu review.

---

## 7. Data source và data contract

### 7.1 Dataset đầu vào

| Dataset | Mục đích | Business key tối thiểu | Xử lý đích trong MVP |
|---|---|---|---|
| `business.json` | Business/restaurant | `business_id` | Chuẩn hóa địa chỉ, city/state, tọa độ, stars, categories, hours, trạng thái mở cửa |
| `review.json` | User feedback | `review_id` | Chuẩn hóa `user_id`, `business_id`, stars, timestamp, text và vote fields |
| `user.json` | User metadata | `user_id` | Tối thiểu hóa dữ liệu, pseudonymize ID, không publish trường không cần thiết |
| `checkin.json` | Check-in events | `business_id` + event timestamp | Tách danh sách timestamp thành một event mỗi dòng và deduplicate |
| `tip.json` | Tips ngắn | Hash ổn định từ user/business/date/text nếu không có ID | Chuẩn hóa text/date và quan hệ business/user |
| `photo.json` | Photo metadata | `photo_id` | Bronze-only; chỉ metadata, không binary image. `SIL_PHOTO` cần change request |
| `attributes.json` | Business attributes | `business_id` + attribute name | Flatten có kiểm soát hoặc giữ semi-structured; có thể được trích từ `business.json` |

Trong core MVP, `business` và `review` là dataset bắt buộc. `user`, `checkin`, `tip` và `photo` là optional theo source release nhưng nếu manifest khai báo chúng thì file thiếu/truncate làm release fail. `attributes` là `DERIVED_OR_OPTIONAL`: ưu tiên file độc lập khi contract xác nhận, nếu không được tách từ `business`. Data release phải ghi coverage từng dataset; feature phụ thuộc dataset absent phải disabled hoặc hiển thị `not available`, không hiện zero.

#### 7.1.1 Restaurant population

Yelp business data không được mặc định coi toàn bộ là nhà hàng. MVP MUST có versioned `restaurant_scope_version` với category taxonomy/rules do Product + Analytics duyệt:

- `IN_SCOPE`: business có exact category `Restaurants` hoặc category con nằm trong inclusion taxonomy đã duyệt.
- `OUT_OF_SCOPE`: không có bất kỳ inclusion category nào.
- `UNKNOWN`: categories null/malformed/chưa map; giữ ở Bronze/Silver và DQ dashboard nhưng không đưa vào product-facing mart/RAG.
- Business hybrid vẫn `IN_SCOPE` nếu có ít nhất một inclusion category; exclusion/precedence ngoại lệ phải ghi rõ trong versioned rule, không hard-code rải rác.
- Nếu source package tuyên bố đã pre-filter restaurants, data contract/fixture vẫn phải chứng minh và gắn cùng scope status/version.

`SIL_BUSINESS` phải có `restaurant_scope_status`, `restaurant_scope_reason` và `restaurant_scope_version`. Chỉ review/check-in/tip liên kết tới `IN_SCOPE` business mới được enrich, đưa vào restaurant Gold marts, embedding/RAG và product KPI. Raw/Silver data ngoài scope vẫn được audit; mọi dashboard/answer hiển thị population definition và coverage. Đổi scope taxonomy tạo processing/data release mới và re-evaluation tương ứng.

Trước khi code production, mỗi dataset MUST có schema contract versioned (JSON Schema hoặc YAML tương đương) mô tả:

- Required/optional fields, data type, enum/range và nullability.
- Business key và deduplication key.
- Nested field policy và maximum supported text/array length.
- Timestamp type, source offset/timezone, DST behavior và fallback cho timestamp naive.
- PII classification.
- Backward-compatible và breaking change policy.
- Ví dụ record hợp lệ/không hợp lệ.
- Owner và schema version.

### 7.2 Batch manifest

Định nghĩa identity/cardinality:

- `source_release_id`: một package/release logic từ nguồn; nếu nguồn không cấp ID, derive từ canonical manifest checksum.
- `source_object_id`: `dataset_name + source_checksum`, định danh bytes nguồn không phụ thuộc contract xử lý.
- `batch_id`: một lần hệ thống nhận và ingest source release; retry/resume giữ nguyên `batch_id`.
- `dataset_run_id`: một dataset bên trong batch.
- `ingestion_attempt_id`: mỗi attempt thực thi của dataset run.
- `processing_run_id`: lần reprocess Bronze bằng code/contract/dbt version mới, không tạo lại source object/Bronze row.

Một manifest document đại diện cho một `source_release_id` và chứa một file record cho mỗi dataset/object. Mỗi source file record MUST có ít nhất:

| Field | Ý nghĩa |
|---|---|
| `batch_id` | UUID/ULID ổn định cho một lần nhận source |
| `source_object_id` | Identity từ dataset + checksum |
| `dataset_run_id` | Identity cho dataset trong batch |
| `dataset_name` | Một trong các dataset allowlist |
| `dataset_requirement` | `REQUIRED`, `OPTIONAL` hoặc `DERIVED_OR_OPTIONAL` |
| `source_uri` | Vị trí object nguồn |
| `source_file` | Tên file gốc |
| `source_size_bytes` | Kích thước file |
| `source_checksum` | SHA-256 của nội dung, không chỉ tên file |
| `schema_version` | Contract được dùng để validate |
| `source_release_id` | ID/version release từ nguồn hoặc canonical manifest hash do hệ thống derive |
| `source_release_type` | `FULL_SNAPSHOT` hoặc `PARTIAL_FEED` |
| `completion_marker` | Bằng chứng package/file đã upload hoàn tất |
| `received_at` | Thời điểm hệ thống nhận đủ file |
| `ingestion_date` | Partition date theo UTC |
| `expected_record_count` | Nếu nguồn/manifest cung cấp; nếu không để null |

Fallback `source_release_id` phải deterministic và không tự tham chiếu:

```text
release_fingerprint = SHA-256(canonical_json({
  source_release_type,
  stable_provider_metadata,
  files: sort_by(dataset_name, source_object_id, dataset_requirement)
}))
```

Canonical JSON dùng UTF-8, object keys sorted và representation ổn định. Fingerprint MUST loại `source_release_id`, `batch_id`, `dataset_run_id`, `ingestion_attempt_id`, `processing_run_id`, `source_uri`, `received_at`, `ingestion_date`, runtime status và mọi temporary/signed URL. Nếu provider cung cấp cùng release ID nhưng canonical fingerprint khác, ingest fail `SOURCE_RELEASE_CONFLICT`; không overwrite hoặc âm thầm coi là update.

Idempotency/source identity ở cấp file là `source_object_id = dataset_name + source_checksum`; `schema_version` không thuộc source identity. File cùng tên nhưng nội dung đổi là source object mới; file khác tên nhưng checksum trùng không được load lại vào Bronze. Reprocess cùng bytes bằng schema/code version mới tạo `processing_run_id` và lineage Silver/Gold mới nhưng không nhân đôi Bronze.

Absence semantics MUST được khóa trong source contract:

- Chỉ khi `source_release_type=FULL_SNAPSHOT`, đủ completion marker và nguồn được định nghĩa authoritative thì record có ở snapshot trước nhưng mất ở snapshot mới mới được suy ra là deleted/superseded.
- Với `PARTIAL_FEED`, source thiếu record không bao giờ được hiểu là deletion.
- Tombstone/correction chỉ được promote sau reconciliation toàn release và phải giữ source release lineage.

### 7.3 Metadata chuẩn trên mỗi record

- `_batch_id`
- `_dataset_run_id`
- `_source_object_id`
- `_source_file`
- `_source_uri`
- `_source_checksum`
- `_source_row_number`
- `_record_hash`
- `_ingested_at`
- `_schema_version`
- `_source_release_id`

`_record_hash` được tính từ canonical representation của payload nghiệp vụ; metadata ingestion không tham gia hash.

### 7.4 Cloudflare R2 layout, stage và format

```text
r2://<bucket>/source/<source_release_id>/<original-file>
r2://<bucket>/raw/<dataset_name>/ingestion_date=YYYY-MM-DD/<batch-id>-*.snappy.parquet
r2://<bucket>/quarantine/<dataset_name>/ingestion_date=YYYY-MM-DD/<batch-id>-*.jsonl
r2://<bucket>/manifests/ingestion_date=YYYY-MM-DD/<batch-id>.json
```

`r2://` ở trên là logical URI dùng trong audit/documentation. Snowflake external stage MUST dùng `URL='s3compat://<bucket>/<prefix>/'` cùng `ENDPOINT='<account_id>.r2.cloudflarestorage.com'` và credentials của R2 token chỉ có quyền trên bucket cần thiết. Metadata auto-refresh của S3-compatible external stage không được giả định; Airflow là owner duy nhất của batch discovery, `LIST`/manifest validation và `COPY INTO`.

- `source/` giữ byte gốc để audit/reprocess; versioning được bật. Object Lock chỉ được bật sau ADR Security/Legal xác nhận mode/retention tương thích deletion obligations.
- `raw/` dùng format Parquet và compression Snappy như sơ đồ.
- Parquet MUST chứa payload đủ để tái tạo `RAW_RECORD` và toàn bộ metadata chuẩn.
- Không overwrite object của batch đã công bố.
- R2 bucket phải private, truyền qua TLS, dùng provider-managed encryption at rest, scoped token và lifecycle/retention policy đã duyệt; public development URL không được bật.

Thiết kế này giải quyết điểm mơ hồ trong sơ đồ: JSON/JSONL gốc vẫn được bảo toàn, còn landing tối ưu cho load bằng Parquet/Snappy; Bronze chuyển payload thành Snowflake `VARIANT`.

### 7.5 State machines: ingestion, processing và release

```text
Ingestion run:
RECEIVED → VALIDATING → VALIDATED → LANDED → BRONZE_LOADED → COMPLETED

Processing run:
CREATED → SILVER_BUILT → ENRICHING → ENRICHED → EMBEDDED
→ GOLD_BUILT → QUALITY_VALIDATED → COMPLETED

Release activation:
CANDIDATE_CREATED → BUILD_COMPLETED → ACTIVATED
```

Trạng thái lỗi/nhánh: `FAILED_VALIDATION`, `FAILED`, `PARTIAL`, `QUARANTINED`, `CANCELLED`.

`PARTIAL` là trạng thái vận hành cho run đã hoàn tất một số stage nhưng không qua đủ publish gate; nó không đổi data release hiện hành. Chuyển trạng thái phải atomic trong audit store. Chỉ release được `AUDIT.ACTIVE_RELEASE_POINTER` trỏ tới mới được phục vụ; ứng dụng tiếp tục dùng release thành công gần nhất khi run mới `PARTIAL` hoặc `FAILED`.

Không dùng chung một status enum cho mọi entity:

| Entity | Store | Trạng thái tiêu biểu |
|---|---|---|
| Source release/batch | `AUDIT.INGESTION_RUN` | `RECEIVED`, `VALIDATING`, `LANDED`, `FAILED`, `PARTIAL`, `COMPLETED` |
| Processing run | `AUDIT.PROCESSING_RUN` | `CREATED`, layer build states, `FAILED`, `PARTIAL`, `COMPLETED` |
| Dataset/file attempt | `AUDIT.FILE_LOAD` | `PENDING`, `LEASED`, `LOADED`, `QUARANTINED`, `FAILED`, `SKIPPED_DUPLICATE` |
| Record | Bronze/quarantine metadata | `ACCEPTED`, `PARSE_FAILED`, `SCHEMA_REJECTED`, `DQ_REJECTED` |
| AI/embedding operation | Invocation ledgers | `PENDING`, `LEASED`, `SUBMITTED`, `COMMITTED`, retry/permanent failure |
| Data release | `AUDIT.DATA_RELEASE_EVENT` + `AUDIT.ACTIVE_RELEASE_POINTER` | Append-only candidate/build/activate/fail/supersede/rollback/invalidate/revoke events + một guarded pointer |

Mỗi state machine MUST có allowed transitions, terminal states, lease expiry, retry/resume owner và crash recovery rule. `QUARANTINED` là outcome của dataset/record, không đồng nghĩa toàn batch đã publish.

Audit contracts tối thiểu:

- `AUDIT.INGESTION_RUN`: `batch_id`, `source_release_id`, `release_type`, `started_at`, `ended_at`, `files_expected`, `files_processed`, `physical_records`, `records_accepted`, `records_quarantined`, `records_parse_failed`, `bytes_received`, `status`, `error_log_ref`.
- `AUDIT.SOURCE_RELEASE_OBJECT`: mapping many-to-many `source_release_id + source_object_id + dataset_name + requirement + ordinal/status`; bắt buộc ghi cả khi object được `SKIPPED_DUPLICATE`, để release mới có lineage tới Bronze bytes đã tồn tại.
- `AUDIT.FILE_LOAD`: `dataset_run_id`, `ingestion_attempt_id`, `source_object_id`, file/checksum/bytes, physical record count, parsed/accepted/quarantined/parse-failed counts, R2 object refs, Bronze COPY query/load IDs, retry/lease/status và timestamps.
- `AUDIT.PROCESSING_RUN`: `processing_run_id`, input `batch_id/source_release_id`, code/contract/dbt/prompt/model versions, started/ended timestamps, layer states, status và error refs. Một ingestion run có thể có nhiều processing runs.
- `AUDIT.PROCESSING_INPUT`: mapping `processing_run_id + source_object_id + bronze_table + bronze_key/range`, tạo lineage cho reprocess mà không update/duplicate Bronze.

Reconciliation MUST tính cả input không parse được:

```text
physical_record_count
  = parsed_accepted_count
  + parsed_quarantined_count
  + parse_failed_count
```

Với JSONL, physical record là nonblank line; malformed line vẫn có line/byte offset và quarantine reference. Với JSON array, physical record là top-level element; file không parse được ở cấp container được đánh dấu file failure, đối soát bằng bytes/checksum và không giả tạo row count.

### 7.6 Schema evolution

- Thêm optional field tương thích: accept, ghi nhận schema drift và tạo ticket cập nhật contract.
- Thiếu required field, đổi type không an toàn hoặc nested shape breaking: quarantine dataset/batch và không promote.
- Không tự động drop field không biết.
- Mọi contract version phải đi qua pull request, test fixture và migration note.
- Reprocessing bằng schema/model version mới phải tạo lineage mới, không sửa audit history cũ.

---

## 8. Mô hình dữ liệu Snowflake

### 8.1 Quy ước object

Mỗi environment dùng database riêng hoặc prefix tương đương:

```text
REVIEWLENS_<ENV>.BRONZE
REVIEWLENS_<ENV>.SILVER
REVIEWLENS_<ENV>.AI
REVIEWLENS_<ENV>.GOLD
REVIEWLENS_<ENV>.AUDIT
REVIEWLENS_<ENV>.QUARANTINE
```

Tên warehouse, stage, storage integration và service account phải có environment suffix. Không dùng production credentials ở dev/test.

### 8.2 Bronze — raw, immutable

Các bảng bắt buộc:

- `BRZ_BUSINESS_RAW`
- `BRZ_REVIEW_RAW`
- `BRZ_USER_RAW`
- `BRZ_CHECKIN_RAW`
- `BRZ_TIP_RAW`
- `BRZ_PHOTO_RAW`
- `BRZ_ATTRIBUTES_RAW`

Canonical columns:

```text
RAW_RECORD VARIANT
BATCH_ID STRING
DATASET_RUN_ID STRING
SOURCE_OBJECT_ID STRING
SOURCE_FILE STRING
SOURCE_URI STRING
SOURCE_CHECKSUM STRING
SOURCE_ROW_NUMBER NUMBER
RECORD_HASH STRING
INGESTED_AT TIMESTAMP_TZ
SCHEMA_VERSION STRING
SOURCE_RELEASE_ID STRING
```

Yêu cầu:

- `SOURCE_RELEASE_ID` trên Bronze là release đầu tiên đưa object vào; quan hệ reuse qua release khác lấy từ `AUDIT.SOURCE_RELEASE_OBJECT`, không nhân bản Bronze row.
- Load qua `COPY INTO` từ external stage trong MVP.
- Load history và `SOURCE_CHECKSUM + SOURCE_ROW_NUMBER` ngăn duplicate vật lý.
- Không update/delete trong hoạt động bình thường.
- Correction được biểu diễn bằng version/tombstone ở layer sau, không sửa lịch sử Bronze.
- Legal deletion hoặc incident response là ngoại lệ có approval/audit và purge/tombstone theo policy. Với immutable backup/Object Lock, hệ thống phải ngăn record bị restore lại và expire theo approved retention; không hứa xóa tức thì khi platform không cho phép. Crypto-erasure chỉ dùng khi Security/Legal duyệt.
- Có thể rebuild Silver hoàn toàn từ Bronze mà không đọc lại nguồn bên ngoài.

### 8.3 Silver — cleaned, typed, conformed

Các tên `SIL_*` dưới đây là logical model names bên trong versioned processing schema `SILVER_RUN_<processing_run_id>`. MVP không cho hai processing runs ghi chung mutable Silver current tables: mỗi run clone/build/test target riêng, và AI/Gold nhận explicit `silver_physical_ref`. `SILVER_CURRENT` nếu có chỉ là convenience view cho operator, không được dùng làm input của candidate processing run.

| Bảng | Grain | Quy tắc chính |
|---|---|---|
| `SIL_BUSINESS` | Một current record cho mỗi `business_id`; history strategy phải được chốt bằng ADR | Typed fields, normalized categories/hours/location, record hash, DQ flags |
| `SIL_REVIEW` | Một current record cho mỗi `review_id` | Stars 1–5, valid text/date, deduplicate, business/user relation, source hash |
| `SIL_USER` | Một record tối thiểu hóa cho mỗi `user_id` | Pseudonymous key; loại bỏ fields không cần cho use case |
| `SIL_CHECKIN` | Một check-in event mỗi `business_id + event_timestamp` | Explode timestamp list; preserve raw/timezone; convert chỉ theo verified contract; deduplicate |
| `SIL_TIP` | Một tip theo stable hash/business key | Typed date/text, deduplicate, relationship checks |
| `SIL_ATTRIBUTES` | Một `business_id + attribute_name` hoặc một structured record theo ADR | Normalize nested/string boolean, giữ raw value khi parse không chắc chắn |

`photo.json` được giữ ở Bronze trong MVP; nếu dashboard cần photo metadata thì bổ sung `SIL_PHOTO` qua change request, không xử lý binary image.

Mọi Silver model MUST:

- Do dbt quản lý.
- Có unique/not-null/relationship/accepted-values tests phù hợp.
- Gắn `_processing_run_id`, `_valid_from`, `_loaded_at`, `_record_hash`, `data_quality_status`, `data_quality_flags` hoặc metadata tương đương; Bronze chỉ giữ ingestion-origin metadata.
- Không âm thầm loại invalid row; row bị loại phải xuất hiện trong quarantine/audit.
- Có deterministic deduplication order.
- Candidate Silver schema được giữ immutable sau khi quality gate pass và tồn tại ít nhất hết release rollback/lineage window.

### 8.4 AI schema

Quy ước mapping tên: nhãn logic trong sơ đồ `AI_REVIEW_ENRICHED` và `AI_REVIEW_ENRICHMENT_ERRORS` được triển khai lần lượt thành object schema-qualified `AI.REVIEW_ENRICHED` và `AI.REVIEW_ENRICHMENT_ERRORS`. Code/config không được trộn hai convention.

Lịch sử `AI.REVIEW_ENRICHED` có khóa logic immutable `review_id + source_record_hash + enrichment_version`. Không dùng cờ/current view toàn cục trên application request path vì nó làm pin/rollback không nhất quán. `AI.REVIEW_RELEASE_MAP(data_release_id, review_id, source_record_hash, enrichment_version)` chọn đúng một enrichment cho mỗi review trong từng release; application resolve release-specific secure projection bằng explicit `data_release_id`:

```text
review_id
business_id
source_record_hash
enrichment_version
sentiment_label              -- positive | neutral | negative | mixed
sentiment_score              -- -1.0 .. 1.0
confidence_score             -- 0.0 .. 1.0
aspect_sentiments            -- array/object theo versioned taxonomy
topics                       -- array theo versioned taxonomy
summary
key_highlights
language_code
model_name
model_version
prompt_version
taxonomy_version
input_tokens
output_tokens
latency_ms
estimated_cost
enriched_at
batch_id
validation_status
```

Aspect taxonomy ban đầu:

- `food`
- `service`
- `price_value`
- `ambiance`
- `cleanliness`
- `location`
- `waiting_time`

Canonical mapping so với nhãn rút gọn trong sơ đồ:

| Nhãn sơ đồ | Canonical value/field |
|---|---|
| `pos`, `neg`, `neutral` | `positive`, `negative`, `neutral` |
| `mixed` | Extension cho review có overall sentiment mâu thuẫn; phải có trong eval set trước khi bật |
| `price` | Aspect `price_value` |
| `ambience` | Aspect `ambiance` |
| `Topics / Category` | Field `topics` là taxonomy chủ đề review; không nhầm với business `categories` từ source |

`enrichment_version` là composite bất biến của output-schema version, model version, prompt version và taxonomy version. JSON Schema phải khóa object của mỗi `aspect_sentiments` tối thiểu gồm `aspect`, `label`, `score`, `confidence` và optional `evidence_text`; đồng thời khóa maximum length/count của summary, highlights và topics. `estimated_cost` luôn đi cùng currency/unit trong cost ledger.

`AI.REVIEW_ENRICHMENT_ERRORS` tối thiểu có:

```text
review_id, batch_id, source_record_hash, error_type, error_message,
raw_response_reference, attempt_count, first_failed_at, last_failed_at,
next_retry_at, model_version, prompt_version, status
```

External call được quản lý bởi `AUDIT.AI_INVOCATION_LEDGER` và `AUDIT.EMBEDDING_INVOCATION_LEDGER`; vector publication dùng `AUDIT.VECTOR_UPSERT_LEDGER`. Mỗi ledger có unique operation key, `request_payload_hash`, `state` (`PENDING`, `LEASED`, `SUBMITTED`, `COMMITTED`, `RETRYABLE_FAILED`, `PERMANENT_FAILED`), `lease_owner`, `lease_expires_at`, provider request/idempotency ID nếu có, attempt, token/cost và result reference. Enrichment key là hash của `review_id + source_record_hash + enrichment_version`; embedding/vector keys được tách theo mục 9.4.

Pipeline bảo đảm **exactly one committed effect**, không cam kết exactly one billable provider call khi worker chết sau response nhưng trước durable commit và provider không hỗ trợ idempotency. Trường hợp không chắc chắn phải được đánh dấu, đối soát và tính vào duplicate-call cost metric.

Invariant validation: chỉ candidate qua JSON Schema, semantic rules và confidence threshold mới được ghi vào `AI.REVIEW_ENRICHED` và release map; tại đó `validation_status` luôn là `VALID`. Candidate đang xử lý nằm trong restricted staging object. Invalid hoặc low-confidence sau bounded repair/retry bắt buộc vào `AI.REVIEW_ENRICHMENT_ERRORS` với error code tương ứng và không được promote.

Publish-gate denominator là toàn bộ valid `SIL_REVIEW` thuộc `IN_SCOPE` restaurant trong candidate release cần `enrichment_version` mục tiêu. Reused committed enrichment cùng source hash/version được tính success; review không có valid target version sau retry được tính permanent failure. `permanent_error_rate = permanent_failed_reviews / eligible_reviews`; batch rỗng được xử lý riêng, không chia cho 0.

Không log raw review/prompt/response mặc định. Nếu cần lưu để debug, dùng encrypted restricted store, redaction và retention ngắn đã được phê duyệt.

### 8.5 Gold — dimensions, facts và marts

| Object | Grain | Nội dung/quan hệ chính |
|---|---|---|
| `DIM_BUSINESS` | Một row mỗi `IN_SCOPE` business version/current theo SCD ADR | Business surrogate key, restaurant scope, location, category, open status, attributes dùng cho analytics |
| `DIM_USER` | Một row pseudonymous mỗi user liên kết in-scope review/tip | Chỉ thuộc tính đã được data classification cho phép |
| `DIM_DATE` | Một row mỗi calendar date | Day/week/month/quarter/year và timezone label |
| `FACT_REVIEW` | Một row mỗi valid review trong release | Serving view: base review left join enrichment được release chọn |
| `FACT_CHECKIN` | Một row mỗi check-in event của in-scope business | Business/date/time keys và event count |
| `MART_BUSINESS_PERFORMANCE` | Business × calendar month | Rating, review, sentiment, aspect, topic, check-in và growth metrics |
| `MART_CATEGORY_TRENDS` | Category × city/state × calendar month | Volume, rating, sentiment, topic và ranking |
| `MART_CITY_OVERVIEW` | City/state × calendar month | Business coverage, review/check-in, rating và sentiment summary |

Gold requirements:

- Star schema dùng surrogate keys và unknown member cho late-arriving dimensions.
- Physical model MUST tách `FACT_REVIEW_BASE` (mọi review hợp lệ thuộc `IN_SCOPE` restaurant từ Silver, không phụ thuộc LLM) và `FACT_REVIEW_ENRICHMENT` (AI fields + version/status). Published `FACT_REVIEW` là release-addressable left join của hai object này.
- Mọi review hợp lệ thuộc restaurant scope MUST xuất hiện trong `FACT_REVIEW`; AI fields nullable và có `enrichment_status`/version. Review chưa enrich vẫn được tính cho review/rating KPI, nhưng không được tính vào denominator của AI metric ngoài định nghĩa rõ.
- Semantic views cho Text-to-SQL phải tách khỏi base tables và chỉ expose fields/metrics được duyệt.
- Incremental dbt model phải cho kết quả giống full refresh trên cùng input.
- `dbt_test_gold` là quality gate trước khi candidate release được activate.
- Category/topic/aspect là quan hệ many-to-many. Implementation MUST dùng bridge/child fact có unique grain (ví dụ `BRIDGE_BUSINESS_CATEGORY`, `FACT_REVIEW_ASPECT`, `FACT_REVIEW_TOPIC`) hoặc flatten deterministic trong mart; không sum category totals như các partition loại trừ lẫn nhau.

### 8.6 Metric dictionary tối thiểu

| Metric | Công thức MVP | Quy tắc |
|---|---|---|
| `review_count` | `COUNT(DISTINCT review_id)` | Chỉ valid review trong active data release |
| `average_review_stars` | `AVG(FACT_REVIEW_BASE.stars)` | Stars trong 1–5; khác với aggregate stars từ business source; hiển thị sample size |
| `business_source_stars` | Giá trị stars current/as-of từ `DIM_BUSINESS` | Không dùng thay cho review-period average |
| `rating_distribution` | Count/share theo từng stars | Denominator là review có stars hợp lệ |
| `review_growth_rate` | `(current_count - prior_count) / NULLIF(prior_count, 0)` | Null khi kỳ trước bằng 0; không hiển thị vô cực |
| `sentiment_share` | Count label / count review enriched hợp lệ | Hiển thị enrichment coverage |
| `average_sentiment_score` | `AVG(sentiment_score)` trên enrichment hợp lệ được release chọn | Hiển thị enriched count và coverage |
| `aspect_sentiment_score` | AVG aspect score cho review có aspect đó | Không coi missing aspect là neutral |
| `topic_frequency` | Count review có topic / enriched review count | Một review chỉ tính một lần mỗi topic |
| `checkin_count` | Count distinct check-in event | Theo reporting timezone đã duyệt; timestamp naive luôn kèm assumption label |
| `rating_sentiment_gap` | `((average_review_stars - 3) / 2) - average_sentiment_score` | Cả hai thang -1..1 |
| `business_rank` | `DENSE_RANK` theo metric và filter | Mặc định chỉ rank khi sample ≥10 review; threshold cấu hình |

`review_growth_rate` mặc định so sánh calendar month với month liền trước trong cùng filter. Category mart có tính non-additive qua category: một business/review có thể đóng góp cho nhiều category, nên tổng category không được trình bày như tổng business/review duy nhất.

Mọi metric bổ sung MUST có owner, grain, formula, filter, null behavior, timezone, sample threshold và test fixture trước khi expose cho BI/Text-to-SQL.

### 8.7 Data release và publish consistency

Để ứng dụng không trộn Gold của batch mới với vector index của batch cũ, release definition, event history và active pointer được tách rõ.

`AUDIT.DATA_RELEASE` là immutable artifact definition, chỉ append sau khi các artifact và quality gate bắt buộc đã sẵn sàng:

```text
data_release_id
processing_run_id
source_release_ids
batch_ids
silver_dbt_invocation_id
silver_physical_ref
enrichment_version
embedding_version
vector_index_version
gold_dbt_invocation_id
gold_physical_ref
ai_physical_ref
quality_gate_result
published_at
supersedes_release_id
```

`AUDIT.DATA_RELEASE_EVENT` là append-only audit log:

```text
event_id, data_release_id, event_type,
event_at, actor_or_run_id, reason, metadata

event_type = CANDIDATE_CREATED | BUILD_COMPLETED | ACTIVATED |
             SUPERSEDED | FAILED | ROLLBACK_ACTIVATED |
             INVALIDATED | REVOKED
```

`AUDIT.ACTIVE_RELEASE_POINTER(environment, active_data_release_id, pointer_version, activation_event_id, updated_at)` là state nhỏ duy nhất được update bằng compare-and-swap/transaction có audit.

- `validate_source` cấp `data_release_id` và append `CANDIDATE_CREATED` ngay sau khi manifest hợp lệ, trước AI release map/vector/Gold build. ID này được truyền xuyên mọi task; failure append `FAILED` dù chưa có immutable release definition.
- Mặc định MVP: tạo versioned/zero-copy clone `SILVER_RUN_<processing_run_id>` và `GOLD_RELEASE_<data_release_id>`, chạy dbt incremental/test trong target riêng. Alternative dùng row-level version keys chỉ được áp dụng bằng ADR chứng minh isolation/rollback tương đương. Không build trực tiếp vào shared current/serving target.
- `silver_physical_ref`, `gold_physical_ref`, `ai_physical_ref` và `vector_index_version` phải định danh immutable snapshot/version đủ để query, reproduce và rollback thật; chỉ lưu dbt invocation ID là chưa đủ.
- `publish_metrics` finalizer insert immutable `AUDIT.DATA_RELEASE`, append activation/supersede events và chuyển pointer **sau cùng** khi mọi gate pass. Failure trước/sau mỗi bước phải recovery được, không tạo mixed active release.
- Mỗi online request đọc pointer một lần, pin `data_release_id`, resolve trusted `gold_physical_ref`/`ai_physical_ref`/`vector_index_version`, rồi dùng explicit version đó từ đầu đến cuối.
- Application Text-to-SQL không query mutable `*_CURRENT` view: service map logical semantic names sang fully-qualified release schema sau AST validation và reject mọi physical identifier do model tự cung cấp. Dashboard cũng query release-bound views; RAG dùng explicit index version.
- Stable `*_CURRENT` views/aliases chỉ là convenience cho Snowsight/BI không hỗ trợ request pinning; chúng được đổi cùng activation và luôn hiển thị release ID/freshness.
- Rollback append `ROLLBACK_ACTIVATED` rồi compare-and-swap pointer về release definition cũ; không sửa/xóa release/event history. Retention MUST giữ đủ Gold/AI/index artifact để đáp ứng rollback window/RTO.
- Activation/rollback guard MUST reject release có `INVALIDATED` (data/artifact không còn đáng tin) hoặc `REVOKED` (legal/security purge), thiếu artifact, sai checksum/policy hoặc không còn trong retention. Release bị purge không bao giờ được “hồi sinh” bởi rollback.
- Nếu active release cần legal/security revoke, hệ thống phải activate sanitized rebuilt release trước; khi không có safe release, fail closed bằng cách disable affected serving features/pointer thay vì tiếp tục phục vụ dữ liệu bị revoke.
- Run `PARTIAL`/`FAILED` không chuyển pointer; AI feature không được dùng candidate vector/AI mart chưa đồng bộ.

---

## 9. Yêu cầu chức năng chi tiết

### 9.1 Ingestion và validation

| ID | Yêu cầu | Ưu tiên | Tiêu chí nghiệm thu |
|---|---|---|---|
| ING-001 | Phát hiện đầy đủ file bắt buộc theo source manifest và chỉ bắt đầu khi upload hoàn tất. | P0 | Partial upload không kích hoạt load; file thiếu tạo `FAILED_VALIDATION` với tên file. |
| ING-002 | Validate filename/dataset allowlist, JSON/JSONL syntax, UTF-8, schema version, required fields, type/range và empty/truncated file. | P0 | Test fixtures cho valid, empty hợp lệ, empty bất thường, malformed line, wrong type và missing field cho kết quả dự kiến. |
| ING-003 | Tính SHA-256 source checksum, stable record hash và sinh `batch_id`. | P0 | Cùng nội dung có cùng checksum; metadata-only thay đổi không đổi record hash. |
| ING-004 | Chuyển record hợp lệ thành Parquet/Snappy và partition theo dataset/date. | P0 | File output đọc được, schema đúng, partition đúng, Unicode/emoji không hỏng. |
| ING-005 | Bảo đảm idempotency khi replay cùng file/batch. | P0 | Re-run cùng checksum không tăng object/row count và audit ghi `SKIPPED_DUPLICATE`. |
| ING-006 | Hỗ trợ file cùng tên nhưng nội dung đổi, late-arriving dataset và historical backfill. | P0 | New checksum tạo version mới; backfill không thay đổi partition hiện hành ngoài rule đã định. |
| ING-007 | Quarantine record lỗi kèm raw/line/byte reference, error code và contract version. | P0 | `physical = accepted + parsed_quarantined + parse_failed`; file-level parse failure vẫn đối soát bytes/checksum. |
| ING-008 | Phân biệt lỗi retryable và non-retryable. | P0 | Network/429 được retry có giới hạn; schema breaking/invalid payload không retry vô hạn. |
| ING-009 | Ghi audit file/row count, bytes, duration, status, error và timestamps. | P0 | 100% run/dataset có audit row và liên kết được với DAG run. |
| ING-010 | Không publish batch có critical source validation failure. | P0 | Downstream task ở trạng thái skipped/blocked, không có Gold version mới. |

### 9.2 Bronze, Silver và Gold

| ID | Yêu cầu | Ưu tiên | Tiêu chí nghiệm thu |
|---|---|---|---|
| DWH-001 | Load mỗi dataset vào đúng Bronze table bằng `COPY INTO` từ R2 S3-compatible external stage và metadata chuẩn. | P0 | Row reconciliation giữa R2 accepted rows và Bronze bằng 100%. |
| DWH-002 | Bronze immutable và replay-safe. | P0 | Service role không có UPDATE/DELETE; replay không sinh duplicate. |
| DWH-003 | Parse raw VARIANT thành typed Silver columns bằng dbt. | P0 | Model contract và dbt tests pass; timestamp offset/naive/DST, type và boolean normalization đúng fixture. |
| DWH-004 | Deduplicate deterministic theo business key, record hash và source version. | P0 | Reorder input không đổi current row được chọn. |
| DWH-005 | Xử lý orphan/late dimension bằng unknown key và DQ flag; không drop fact âm thầm. | P0 | Orphan xuất hiện trong audit; tỷ lệ vượt threshold chặn promotion. |
| DWH-006 | Xây đúng Gold dimensions/facts/marts và metric dictionary. | P0 | Kết quả đối soát với golden fixture và query tham chiếu. |
| DWH-007 | dbt tests chia critical/warning; critical failure chặn downstream. | P0 | Airflow nhận đúng exit status và không publish khi critical test fail. |
| DWH-008 | dbt docs/lineage/owner có cho mọi model public. | P0 | `dbt docs generate` thành công, không có model public thiếu description/owner/test khóa. |
| DWH-009 | Full refresh và incremental build cho kết quả tương đương. | P0 | Row/hash comparison trên test dataset bằng nhau. |
| DWH-010 | Hỗ trợ correction/tombstone ở Silver/Gold theo authoritative source semantics. | P0 | Correction không sửa lịch sử Bronze; current/release views phản ánh đúng tombstone sau complete snapshot. |
| DWH-011 | Hỗ trợ legal deletion/incident exception theo approved retention. | P0 trước dữ liệu thật | Purge hoặc restore-suppression/expiry được approval, audit và kiểm thử xuyên mọi store. |
| DWH-012 | Áp versioned restaurant population nhất quán từ Silver tới Gold/AI/RAG. | P0 | Non-restaurant/unknown fixtures không lọt product KPI/index; hybrid/in-scope fixtures đúng rule; coverage đối soát được. |
| DWH-013 | Mỗi processing run build/test Silver trong isolated versioned physical target. | P0 | Hai distinct release/backfill runs chạy xen kẽ không đọc/ghi chéo; AI/Gold lineage trỏ đúng `silver_physical_ref`. |

### 9.3 LLM enrichment

| ID | Yêu cầu | Ưu tiên | Tiêu chí nghiệm thu |
|---|---|---|---|
| AI-001 | Chỉ enrich review mới/thay đổi theo `source_record_hash + enrichment_version`. | P0 | Re-run review không đổi không gọi LLM và không tăng token usage. |
| AI-002 | Output theo versioned JSON Schema gồm sentiment, aspect, topics, summary, highlights và confidence. | P0 | Output sai enum/type/range bị reject. |
| AI-003 | Tách instruction khỏi review text và coi review là untrusted data. | P0 | Bộ prompt-injection test không làm model đổi task hoặc gọi tool. |
| AI-004 | Batching/concurrency/rate limit/backpressure cấu hình được. | P0 | Khi provider trả 429, job giảm tải/retry mà không mất checkpoint. |
| AI-005 | Retry exponential backoff có jitter, max attempt và error taxonomy. | P0 | Lỗi transient được retry; permanent schema/safety error vào error table sau giới hạn. |
| AI-006 | Validate cả schema và semantic rule/confidence. | P0 | JSON hợp lệ nhưng score/label mâu thuẫn hoặc confidence dưới threshold bị repair/retry có giới hạn rồi vào error table; không xuất hiện trong enriched/release map. |
| AI-007 | Lưu model, prompt, taxonomy, input hash, token, latency và cost metadata. | P0 | Một enriched row truy ngược được đúng version và batch. |
| AI-008 | Re-enrichment bằng version mới không tạo hai active records trong cùng release. | P0 | `AI.REVIEW_RELEASE_MAP` unique theo `data_release_id + review_id`; lịch sử composite-key vẫn immutable và rollback được. |
| AI-009 | Gold AI metrics chỉ dùng valid enrichment được active release map chọn. | P0 | Invalid/error rows không xuất hiện trong AI metric; coverage vẫn được hiển thị. |
| AI-010 | Có human-labeled golden set và regression gate. | P0 | Model/prompt mới không deploy nếu metric dưới threshold đã duyệt. |
| AI-011 | Durable invocation ledger/outbox kiểm soát lease, checkpoint, retry và commit của external calls. | P0 | Crash-injection trước/sau provider response tạo tối đa một committed result; ambiguous duplicate call được ghi nhận/costed. |

### 9.4 Embedding và vector index

Chunk/document artifact tối thiểu có:

```text
chunk_id, review_id, business_id, chunk_ordinal,
source_start_offset, source_end_offset, embedding_input_ref,
serving_safe_evidence_text, content_hash, source_record_hash,
chunking_version, source_release_id, stars, review_date, city,
categories, document_metadata_hash, policy_version,
embedding_model, embedding_version, index_version, created_at
```

Embedding input có thể kết hợp review gốc với summary/topics để tăng recall, nhưng phải qua transfer/DLP policy và nằm trong restricted path; vector search response/log không được trả raw input. `serving_safe_evidence_text` MUST là excerpt đã redacted từ review gốc. Summary/topic do AI sinh chỉ hỗ trợ retrieval, không tự nó được dùng làm evidence cho factual claim.

RAG đọc release-specific secure object `AI.RAG_DOCUMENT`, là security projection được tạo từ nguồn logic `AI_REVIEW_ENRICHED` trong sơ đồ; service không join trực tiếp Silver hay base AI table. Object này chứa `data_release_id`, serving-safe evidence, citation IDs, content hash, filter metadata và policy labels. Vector backend chỉ cần trả `chunk_id + score`; service fetch evidence từ `AI.RAG_DOCUMENT` và re-check authorization. Nếu backend bắt buộc lưu text, chỉ lưu serving-safe redacted text và cấm return field ngoài service contract.

Hai identity bắt buộc tách riêng:

```text
embedding_compute_key = SHA-256(content_hash + embedding_model + embedding_version)
vector_upsert_key = SHA-256(index_version + chunk_id + embedding_compute_key
                               + document_metadata_hash + policy_version)
```

Thay filter/citation/ACL/policy metadata phải upsert document vào index mới/hiện hành dù không gọi lại embedding provider. Rebuild index version luôn tạo vector upsert key mới; thay content/model mới tạo embedding compute key mới.

| ID | Yêu cầu | Ưu tiên | Tiêu chí nghiệm thu |
|---|---|---|---|
| EMB-001 | Xác định chunk từ review text, summary, topics và metadata; review ngắn mặc định một chunk. | P0 | Chunk tái tạo deterministic; không cắt mất citation mapping. |
| EMB-002 | Reuse embedding theo `embedding_compute_key`; metadata-only change không gọi provider lại. | P0 | Re-run/reindex reuse vector value, token/cost không tăng ngoài operation cần thiết. |
| EMB-003 | Upsert/delete/supersede vector theo `vector_upsert_key` và release map. | P0 | Index/metadata/policy change tạo upsert đúng; reconciliation ≥99.9%; stale vector được sửa/rebuild. |
| EMB-004 | Filter theo business, city/state, category, stars và date. | P0 | Retrieval test chứng minh filter không rò record ngoài phạm vi. |
| EMB-005 | Version hóa index và hỗ trợ rebuild/rollback. | P0 | Có thể chuyển alias từ index mới về index trước mà không sửa source data. |
| EMB-006 | Theo dõi embedding count, latency, error, age và cost. | P0 | Dashboard vận hành có đủ metric và alert index lag. |
| EMB-007 | Embedding compute và vector upsert dùng hai durable ledgers/idempotency keys tách biệt. | P0 | Crash/replay tạo tối đa một committed compute result và một document mỗi upsert key; duplicate provider cost quan sát được. |

Ràng buộc backend MVP: embedding được gọi qua OpenRouter adapter; ChromaDB local lưu collection theo `index_version` trên persistent volume. Snowflake giữ document metadata/release map authoritative, còn ChromaDB chỉ là retrieval index có thể rebuild. ChromaDB collection không được coi là system of record và không được chứa raw field ngoài schema `AI.RAG_DOCUMENT` đã cho phép.

### 9.5 RAG chatbot

| ID | Yêu cầu | Ưu tiên | Tiêu chí nghiệm thu |
|---|---|---|---|
| RAG-001 | Retrieve chỉ từ secure `AI.RAG_DOCUMENT` và vector index của active data release trong phạm vi quyền. | P0 | Không trả record candidate, quarantined hoặc bị policy loại. |
| RAG-002 | Trả answer chỉ dựa trên retrieved evidence. | P0 | Golden set đạt groundedness target; no-evidence question được từ chối đúng. |
| RAG-003 | Mọi factual claim phải có citation hợp lệ. | P0 | Citation resolve tới business, review ID, source release và excerpt thực. |
| RAG-004 | Không giả lập public Yelp URL khi dataset không có URL đáng tin cậy. | P0 | Link mặc định là internal evidence route; URL ngoài chỉ hiện khi contract bảo đảm. |
| RAG-005 | Hiển thị filter, data freshness, citation và disclaimer về user-generated content. | P0 | UI test xác nhận đủ thông tin cho mỗi answer. |
| RAG-006 | Chống prompt injection từ question và retrieved review. | P0 | Red-team prompt không thay đổi system policy, không lộ secret/prompt và không gọi tool ngoài scope. |
| RAG-007 | Log request/retrieval/latency/model/version/feedback theo privacy policy. | P0 | Trace từ request tới retrieved IDs được, nhưng log mặc định không chứa raw PII/secret. |
| RAG-008 | Hỗ trợ follow-up trong session mà không vượt quyền/filter ban đầu. | P1 | Session test không làm mất policy context. |
| RAG-009 | UI cho phép đánh dấu hữu ích/không hữu ích và optional reason đã được privacy-filter. | P1 | Feedback gắn request/release/model version, không chứa raw answer/question ngoài retention policy. |

### 9.6 Text-to-SQL

| ID | Yêu cầu | Ưu tiên | Tiêu chí nghiệm thu |
|---|---|---|---|
| SQL-001 | LLM chỉ nhận versioned semantic catalog của Gold allowlist. | P0 | Prompt/context không chứa Bronze, Silver, audit, PII hoặc object ngoài allowlist. |
| SQL-002 | Chỉ chấp nhận đúng một `SELECT` hoặc `WITH ... SELECT` qua AST parser. | P0 | 100% malicious corpus gồm multi-statement, DDL, DML, CALL, COPY, PUT/GET bị chặn. |
| SQL-003 | Allowlist table/view, column, join và function; chặn `INFORMATION_SCHEMA`, stage, external function và data-export path. | P0 | Query cố truy cập object/function ngoài policy bị từ chối trước execution. |
| SQL-004 | Thực thi bằng `TEXT_TO_SQL_ROLE` và warehouse riêng read-only. | P0 | Role test chứng minh không ghi được và không đọc ngoài curated semantic views. |
| SQL-005 | Enforce timeout, max rows (mặc định 1.000), concurrency và resource/credit limit ở execution layer. | P0 | Query quá giới hạn bị cancel/truncate có thông báo rõ. |
| SQL-006 | Chặn Cartesian join/quét quá rộng theo policy và yêu cầu làm rõ câu hỏi mơ hồ. | P0 | Adversarial/ambiguous eval không gây query runaway. |
| SQL-007 | Hiển thị question, generated SQL đã được chuẩn hóa, result table/chart, freshness và error thân thiện. | P0 | Người dùng có thể kiểm tra SQL thực tế; empty result không bị diễn giải thành zero sai. |
| SQL-008 | Audit requester, prompt template version, SQL candidate, validation decision, Snowflake query ID, duration và cost. | P0 | Security admin truy vết được mọi execution/denial. |
| SQL-009 | Không tự sửa và chạy lại vô hạn. | P0 | Số vòng repair cấu hình, mặc định tối đa 1; mỗi vòng đều được audit. |
| SQL-010 | Semantic accuracy được đánh giá trên bộ câu hỏi chuẩn, không chỉ execution success. | P0 | Release đạt target correctness và không có regression critical. |
| SQL-011 | Harden Snowflake session bằng fully-qualified object resolution, disabled secondary roles, approved normalized functions, query tag, statement timeout và resource monitor. | P0 | Negative tests chạy bằng đúng app service identity không bypass được AST/RBAC/session/cost controls. |
| SQL-012 | Server bind logical semantic names sang physical schema của pinned release; model/client không được cung cấp physical ref. | P0 | Concurrent pointer-swap test cho thấy query chỉ đọc một release; injected/current/candidate schema identifier bị reject. |

### 9.7 Analytics và dashboard

Các trang MVP:

1. **Executive Overview**: business count, review/check-in volume, average rating, sentiment mix, freshness.
2. **Business Detail**: rating/review trend, aspect sentiment, topic, highlights và source reviews.
3. **City & Category Trends**: comparison, ranking và trend theo thời gian.
4. **Review & Aspect Insights**: sentiment, aspect, topic, coverage và drill-down evidence.
5. **Data Quality & Pipeline Health**: latest batch, freshness, failures, quarantine và coverage.

Filter chung: date range, city/state, category, business, star range, sentiment, aspect và topic.

| ID | Yêu cầu | Ưu tiên | Tiêu chí nghiệm thu |
|---|---|---|---|
| BI-001 | KPI lấy từ release-bound Gold mart/semantic views, không query Bronze/Silver/current alias trên request path. | P0 | Kết quả dashboard pin một release và đối soát đúng query tham chiếu trong concurrent publish test. |
| BI-002 | Filter áp dụng nhất quán và hiển thị sample size/coverage. | P0 | Cross-page filter tests pass; ranking tuân minimum sample. |
| BI-003 | Hiển thị data refresh time, source release, timezone và batch status. | P0 | Người dùng phân biệt được current/stale data và biết run mới nhất có fail/partial hay không. |
| BI-004 | Drill-down metric AI tới review evidence trong phạm vi quyền. | P0 | Citation/detail route resolve đúng record. |
| BI-005 | Empty/loading/error/degraded/stale state rõ ràng. | P0 | UI không hiển thị zero thay cho unavailable/error. |
| BI-006 | Keyboard navigation, text label và color contrast cơ bản. | P0 | Core flow accessibility smoke test pass. |

#### 9.7.1 Contract logic cho ứng dụng online

Transport có thể là API riêng hoặc service layer bên trong Streamlit, nhưng các contract sau là bắt buộc và phải được versioned:

```text
RAG request:
  request_id, actor_id, question, filters, conversation_id?, locale?
RAG response:
  answer, citations[], applied_filters, data_release_id,
  model_version, latency_ms, refusal_reason?, trace_id

Text-to-SQL request:
  request_id, actor_id, question, filters?, locale?
Text-to-SQL response:
  normalized_question, executed_sql?, columns[], rows[], chart_spec?,
  data_release_id, query_id?, validation_decision, denial_reason?, trace_id

Evidence request:
  actor_id, review_id, data_release_id
Evidence response:
  business identity, permitted excerpt, source_release_id, metadata, trace_id
```

`actor_id` được service derive từ verified authentication context, không lấy giá trị do client tự khai làm nguồn quyền.

| ID | Yêu cầu ứng dụng | Ưu tiên | Tiêu chí nghiệm thu |
|---|---|---|---|
| APP-001 | Mọi request được authentication trước khi truy cập Snowflake/vector store. | P0 | Anonymous/expired identity bị từ chối; actor xuất hiện trong audit. |
| APP-002 | Authorization/filter policy được áp dụng ở server/service layer, không tin dữ liệu từ client. | P0 | Client sửa filter/role không mở rộng phạm vi dữ liệu. |
| APP-003 | Request/response có version, `request_id`, `data_release_id` và `trace_id`. | P0 | Một UI result truy vết được đúng data/model/index/query version. |
| APP-004 | Validate size/type/range của question, filter và pagination trước processing. | P0 | Oversized/malformed payload bị từ chối có error code, không tới LLM/warehouse. |
| APP-005 | Error contract không lộ stack trace, SQL credential, raw prompt hoặc internal object ngoài policy. | P0 | Security test không tìm thấy secret/sensitive diagnostic trong UI response. |
| APP-006 | Rate limit và bounded concurrency theo actor/feature. | P0 | Burst test bảo vệ LLM/warehouse và trả retry guidance rõ ràng. |
| APP-007 | Evidence/citation route kiểm tra lại quyền tại thời điểm mở link. | P0 | Copy link sang actor không có quyền không làm lộ excerpt. |
| APP-008 | Production dùng approved IdP hoặc authenticated reverse proxy; anonymous/shared identity bị cấm. | P0 | Mọi route/app websocket/API từ chối request không có identity hợp lệ. |
| APP-009 | Map identity/group → persona → feature/data permission và service role; operator pages tách khỏi business UI. | P0 | Negative authorization tests cho từng persona và page/action pass. |
| APP-010 | Session/cookie/token dùng secure defaults, expiry, logout/revocation và CSRF protection cho state-changing action. | P0 | Session expiry/revocation/CSRF tests fail closed và ghi audit theo actor. |

### 9.8 Airflow orchestration

DAG bắt buộc: `yelp_pipeline`.

| Thứ tự | Task | Input chính | Output/gate |
|---:|---|---|---|
| 1 | `validate_source` | Source release/manifest | Valid manifest + `processing_run_id` + candidate `data_release_id/event`, hoặc fail |
| 2 | `upload_to_r2` | Valid source files | R2 source archive + Parquet/raw + audit |
| 3 | `copy_to_bronze` | R2 paths/checksums | Bronze load + reconciliation |
| 4 | `dbt_build_silver` | Processing run + Bronze refs | Versioned `silver_physical_ref` |
| 5 | `dbt_test_silver` | Explicit Silver run schema | Critical quality gate |
| 6 | `enrich_reviews` | New/changed `SIL_REVIEW` từ explicit Silver ref | AI candidates/errors |
| 7 | `validate_enrichment` | AI candidates | Valid enriched history + release-map candidates |
| 8 | `build_embeddings` | Valid enrichment | Versioned vector index |
| 9 | `dbt_build_gold` | Explicit Silver ref + valid AI release map | Versioned Gold dimensions/facts/marts |
| 10 | `dbt_test_gold` | Gold models | Publish quality gate |
| 11 | `publish_metrics` | Run/task/dbt/AI metadata | Finalize audit/metrics/alert; publish release khi gate pass |

| ID | Yêu cầu orchestration | Ưu tiên | Tiêu chí nghiệm thu |
|---|---|---|---|
| ORCH-001 | DAG parameter hóa bởi `batch_id`, `source_release_id`, `ingestion_date`, environment và optional start task. | P0 | Manual run/backfill truyền đúng context xuyên tất cả task và audit. |
| ORCH-002 | Không có hai active runs cho cùng idempotency key. | P0 | Concurrent trigger thứ hai bị defer/reject mà không tạo side effect. |
| ORCH-003 | Retry, timeout, pool và concurrency cấu hình theo task; LLM có rate-limit pool riêng. | P0 | Failure/rate-limit test tuân đúng số retry và concurrency cap. |
| ORCH-004 | Resume từ task thành công gần nhất mà không phá idempotency. | P0 | Inject failure ở từng stage rồi resume cho kết quả bằng clean run. |
| ORCH-005 | Backfill date/source range không thay current version ngoài promotion rule. | P0 | Backfill tạo lineage riêng; pointer chỉ đổi sau explicit publish gate. |
| ORCH-006 | Silver critical failure chặn AI/Gold; AI failure vượt threshold chặn toàn bộ release mới. | P0 | Dependency tests tạo đúng `FAILED` hoặc `PARTIAL`, pointer vẫn ở release thành công gần nhất. |
| ORCH-007 | Alert nêu environment, DAG/run/task, batch, error class, retry state, owner và runbook link. | P0 | Test alert chứa đủ context và tới đúng owner/channel. |
| ORCH-008 | Scheduler không tạo batch giả khi không có release mới. | P0 | `NO_NEW_SOURCE` là success/no-op và không tạo data/object/vector mới. |
| ORCH-009 | `validate_source` cấp candidate ID; `publish_metrics` finalize immutable release definition/events và chuyển pointer có kiểm soát. | P0 | AI map có ID trước task 7; app không quan sát Gold/vector mixed-version trong publish/rollback test. |
| ORCH-010 | `publish_metrics` hoặc finalizer tương đương luôn ghi terminal state khi upstream success/fail. | P0 | Failure injection ở mỗi upstream task vẫn tạo đủ audit/metrics/notification; pointer chỉ đổi khi gate pass. |
| ORCH-011 | Distinct source/backfill processing runs dùng isolated Silver/Gold targets và explicit refs. | P0 | Concurrent interleaving test không gây cross-run row contamination hoặc lineage mismatch. |

Tên `publish_metrics` được giữ để khớp sơ đồ, nhưng trách nhiệm thực tế là `finalize_run + publish_release`. Implementation MAY dùng Airflow `all_done` finalizer/failure callback riêng; không được để upstream failure làm mất audit terminal state.

### 9.9 Audit, lineage, observability và cost

| ID | Yêu cầu | Ưu tiên | Tiêu chí nghiệm thu |
|---|---|---|---|
| OBS-001 | Ghi pipeline run/task status, duration, rows, bytes, retry và error. | P0 | 100% task có structured event và correlation IDs. |
| OBS-002 | Ghi table-level reconciliation và dbt test/freshness result. | P0 | Dashboard chỉ ra chính xác layer gây chênh lệch. |
| OBS-003 | Publish dbt lineage/docs và audit schema `AUDIT.*`. | P0 | Trace source → Bronze → Silver → AI → Gold được. |
| OBS-004 | Theo dõi quarantine/DLQ, replay state và poison record. | P0 | Operator có thể lọc lỗi, sửa nguyên nhân và replay có audit. |
| OBS-005 | Theo dõi LLM token/latency/error/cost, embedding cost, Snowflake credit/query/storage. | P0 | Cost xem được theo batch, review, feature và environment. |
| OBS-006 | Alert freshness, reconciliation, duplicate/orphan, schema drift, AI error, index lag, warehouse queue/credit và serving latency. | P0 | Alert threshold/owner/severity/runbook được cấu hình và test. |
| OBS-007 | Correlation end-to-end cho offline và online flow. | P0 | Nối được `data_release_id → DAG run → batch/checksum → dbt/model/prompt/index version`; online nối `request_id → data_release_id → retrieved IDs/query_id`. |
| OBS-008 | Budget alert tại 50%, 80% và 100% monthly budget được chốt ở M0. | P0 | Alert được test; hard cap/degrade behavior được ghi rõ. |

---

## 10. Security, privacy và governance

### 10.1 Snowflake RBAC

| Role | Quyền cho phép | Quyền không được có |
|---|---|---|
| `INGEST_ROLE` | USAGE storage integration/stage/file format; INSERT/COPY vào Bronze theo object cụ thể | UPDATE/DELETE Bronze; đọc Gold/user-facing data |
| `TRANSFORMER_ROLE` | USAGE transform warehouse; SELECT Bronze; CRUD qua dbt trên Silver | Write Bronze; AI provider/vector access; account administration |
| `AI_ENRICH_ROLE` | SELECT approved `SIL_REVIEW` view; write AI staging/enriched/error và invocation ledger qua scoped procedures/tables | Read unrelated Silver/user fields; Gold write; security administration |
| `VECTOR_INDEXER_ROLE` | SELECT approved release RAG documents; create/upsert selected vector index | Silver/Base AI joins; Gold write; serving as end user |
| `GOLD_BUILDER_ROLE` | SELECT approved Silver/AI release objects; CRUD versioned Gold build target qua dbt | Mutate published release; read raw PII ngoài build contract |
| `ANALYST_ROLE` | SELECT Gold approved views | Write; đọc Bronze/Silver/restricted AI |
| `TEXT_TO_SQL_ROLE` | SELECT curated Gold semantic views; warehouse riêng | Mọi write; raw schemas; information schema rộng; stage/external functions |
| `RAG_ROLE` | SELECT release-bound secure `AI.RAG_DOCUMENT` projection; ChromaDB access đi qua app service credential tách biệt | Join Silver/base AI; global current/candidate refs; user PII ngoài citation/filter allowlist; write source tables hoặc Chroma collection ngoài active version |

- App identity và service identity phải tách biệt.
- Không dùng shared human credentials cho service.
- Role grants được kiểm thử tự động bằng positive và negative permission tests.
- Row access/masking là P0 nếu sản phẩm không còn single-tenant nội bộ; không được để “optional” sau khi có tenant/user group khác quyền.

Năm role trong sơ đồ là ví dụ rút gọn; PRD tách thêm AI writer, vector indexer và Gold builder để thực hiện nguyên tắc role-per-layer/least privilege. Nếu platform gộp role, ADR và negative permission tests phải chứng minh không mở rộng blast radius trái yêu cầu.

### 10.2 Bảo vệ dữ liệu

- Encrypt in transit và at rest; R2 bucket private dùng TLS, provider-managed encryption, scoped bucket token và lifecycle policy phù hợp.
- Secrets nằm trong secrets manager/secret backend, không ở code, image, Airflow Variable plaintext hoặc log.
- Pseudonymize `user_id`; minimize/loại name, friends và trường user không phục vụ use case.
- Review text có thể chứa PII tự do. Trước external LLM/embedding transfer phải áp DLP/redaction/tokenization policy đã test hoặc có approval rõ ràng cho từng data class/provider; không được mặc định gửi nguyên văn.
- Không log raw prompt, raw review, full SQL result hoặc access token theo mặc định.
- User question, generated SQL, feedback và conversation metadata cũng là dữ liệu có thể nhạy cảm; phải redact/hash theo field, access-control và retention riêng.
- Retention phải định nghĩa riêng cho source, Bronze, curated, vector, cache, prompt/response metadata và audit.
- Deletion/correction hợp pháp phải propagate qua R2, Snowflake, ChromaDB index và cache; immutable source/backup dùng tombstone + restore filtering + expiry hoặc approved crypto-erasure theo runbook, dù Bronze thông thường immutable.
- Data provider setting về training/retention, region và cross-border transfer phải được Security/Legal duyệt.

### 10.3 Bảo vệ AI

- System instruction và retrieved content được tách bằng structured message/schema.
- Review text không được cấp tool hoặc quyền thay đổi dữ liệu.
- RAG answer có disclaimer rằng review là user-generated content, có thể sai hoặc mang tính chủ quan.
- Input/output moderation và report/correction workflow được bật theo risk assessment.
- Prompt/model/taxonomy change phải versioned, reviewed và regression-tested.
- SQL safety dựa trên defense in depth: prompt constraint + AST policy + RBAC + warehouse/resource limit + audit.

### 10.4 License và compliance gate

Chỉ được dùng synthetic fixtures trước khi có bằng chứng Security/Legal phê duyệt. Việc ingest dữ liệu Yelp thật vào dev/staging, gửi review thật tới LLM/embedding provider hoặc tạo vector thật cũng thuộc gate này, không chỉ production. Approval phải bao phủ:

- Quyền dùng dataset cho mục đích dự kiến.
- Quyền lưu/transform/re-distribute review text và metadata.
- Quyền gửi nội dung cho model/embedding provider.
- Attribution/citation bắt buộc.
- Data retention/deletion và privacy obligations.

M0 bundled Terms review (bản 2023-07-07) áp restrictive default: real Yelp Data không được upload lên managed R2/Snowflake, gửi tới OpenRouter/embedding hoặc public dưới dạng rows/review excerpts/derived metrics cho đến khi owner chứng minh academic eligibility và có mọi Yelp review/approval cần thiết. Trong thời gian đó, cloud integration và public portfolio demo chỉ dùng synthetic fixtures; source thật chỉ được profile local trong phạm vi agreement.

### 10.5 Security acceptance requirements

| ID | Yêu cầu | Ưu tiên | Tiêu chí nghiệm thu |
|---|---|---|---|
| SEC-001 | Least-privilege RBAC và service identity riêng cho ingestion, transform, enrichment, RAG, SQL và human analyst. | P0 | Positive/negative grants test pass; không service nào dùng admin role. |
| SEC-002 | Secret management, encryption, rotation và network/egress policy được cấu hình theo environment. | P0 | Secret scan sạch; rotation drill và unauthorized egress test pass. |
| SEC-003 | Data classification/minimization/pseudonymization áp dụng trước Gold, RAG và logs. | P0 | Restricted fields không xuất hiện trong approved views/index/log fixtures. |
| SEC-004 | App authentication và server-side authorization bảo vệ mọi online request/evidence route. | P0 | Auth bypass/IDOR tests fail closed và được audit. |
| SEC-005 | Prompt-injection, data-exfiltration và SQL-policy red-team suite chặn release khi fail. | P0 | 100% critical adversarial cases trong approved suite bị block/refuse an toàn. |
| SEC-006 | Retention và legal deletion/correction có owner, approval, release revocation guard và propagation runbook. | P0 trước production | Dry run purge/tombstone/rebuild đánh dấu old release `REVOKED`; rollback guard không thể reactivate nó. |
| SEC-007 | Log/audit chống sửa trái phép, access restricted và không chứa raw secret/PII mặc định. | P0 | Tamper/access/log-content tests pass theo retention policy. |
| SEC-008 | License, provider retention/training và data residency được duyệt bằng văn bản. | P0 gate | Production deploy bị chặn nếu approval artifact chưa tồn tại. |

SEC-003 test fixtures MUST seed tên, email, số điện thoại, địa chỉ, access token và prompt-like secret trong source review lẫn user question; test xác nhận provider payload, vector document, application log và telemetry không chứa chúng ngoài allowlist được phê duyệt.

---

## 11. Yêu cầu phi chức năng và SLO

| Nhóm | Baseline MVP | Cách đo |
|---|---|---|
| Completeness | 100% source file có checksum; mọi parsed row được accepted hoặc quarantined | Audit reconciliation mỗi dataset/batch |
| Idempotency | 0 duplicate business key/current record sau replay cùng input | dbt uniqueness + replay test |
| Referential quality | Orphan fact <0.1%; vượt ngưỡng chặn promotion | dbt relationship/audit |
| Freshness | 95% Gold và vector sẵn sàng ≤6 giờ sau khi nhận đủ source batch | `received_at` đến `published_at` |
| Source polling reliability | ≥99% scheduled polls hoàn tất/tháng | Airflow sensor/scheduler metrics; đo riêng `NO_NEW_SOURCE` |
| Eligible release reliability | ≥99% complete/valid source releases được publish thành công/tháng | Loại `NO_NEW_SOURCE`; invalid source báo riêng, không dùng để tăng denominator |
| AI schema validity | ≥99% output hợp lệ sau retry; 100% failure có error record | AI validation audit |
| Vector freshness | ≥99.9% enriched records được active release map chọn có vector đúng version | Reconciliation job |
| Serving availability | ≥99.5%/tháng cho MVP nội bộ | Synthetic checks |
| Dashboard latency | warm p95 <5 giây; cold p95 <10 giây với filter chuẩn | End-to-end app telemetry; không loại cold request, báo hai slice |
| RAG latency | end-to-end p95 <10 giây | Tách warm/cold/provider slice nhưng SLO dùng user-observed latency |
| Text-to-SQL latency | end-to-end p95 <15 giây | Generate + validate + execute, gồm warehouse resume nếu xảy ra |
| RAG quality | Citation correctness và groundedness ≥90% trên golden set; 100% factual answer có citation hoặc refusal | Versioned offline evaluation |
| Text-to-SQL quality | ≥90% semantic correctness trên supported eval set; 100% malicious write/exfiltration tests bị chặn | Offline + security evaluation |
| Accessibility | Core flow dùng được bằng keyboard và không chỉ dựa vào màu | Manual/automated smoke test |
| Recovery | Core analytics RPO ≤24h/RTO ≤4h; AI/vector RPO ≤24h/RTO ≤8h | Restore/rebuild drill hàng quý |
| Cost | Theo budget được duyệt; cảnh báo 50/80/100% | Cost dashboard/resource monitor |

### 11.1 Scalability và capacity

- Pipeline phải xử lý được full historical source package bằng chunk/batch mà không load toàn bộ file vào memory.
- Sizing test sử dụng source volume thật và ít nhất một run full-load trước production.
- LLM enrichment dùng checkpoint, bounded concurrency và resumable batches; không một Airflow task per review.
- Warehouse size, auto-suspend, cluster strategy và vector capacity được quyết định bằng benchmark, không hard-code trong business logic.
- Hệ thống phải degrade có kiểm soát khi LLM/vector store unavailable: analytics không bị mất; AI feature báo unavailable/stale rõ ràng.

Tại M0, owner MUST khóa capacity envelope dùng cho staging/load test: source release ID, compressed/uncompressed GB, row count từng dataset, max/p95 review length và token count, incremental/new/changed rows, concurrent users, dashboard/RAG/Text-to-SQL requests per second và selected warehouse/vector sizing. SLO chỉ được ký khi test chạy đúng hoặc cao hơn envelope này.

SLO được tính theo rolling 30 ngày, chỉ khi có tối thiểu sample size được owner chốt; planned maintenance được báo trước có thể tách riêng nhưng không được loại dependency cold start hoặc retry mà người dùng thật quan sát thấy.

### 11.2 Maintainability và reproducibility

- Python modules có type checking/lint/unit tests theo chuẩn repo được chọn.
- Config theo environment, không hard-code credential, bucket, database, warehouse, model hoặc threshold.
- Dependency và container image được pin/version/scanned.
- Mọi output AI có input hash, model, prompt, taxonomy và timestamp.
- Mọi deployment có artifact version và rollback procedure.

---

## 12. Data quality, testing và AI evaluation

### 12.1 Test matrix

| Lớp | Test bắt buộc |
|---|---|
| Source | File presence/completeness, checksum, encoding, parse, schema, type/range, empty/truncate, duplicate batch |
| Ingestion | Idempotency, partition/path, Parquet readability, row reconciliation, replay/backfill/late file |
| Bronze | COPY errors, metadata not-null, row count, duplicate load, raw parseability, immutable grant |
| Silver | Unique/not-null/accepted range/relationship, deterministic dedup, nested parse, timezone, orphan and DQ flags |
| AI enrichment | JSON Schema, enum/range, confidence, injection, language, sarcasm/mixed/short/emoji/long review, retry/error paths |
| Vector | Coverage, version, metadata filter, stale/missing vector, recall@k, index rollback |
| Gold | Grain, keys, relationships, formula fixtures, incremental-vs-full equivalence, freshness |
| RAG | Recall@k, groundedness, citation correctness, relevance, contradiction, no-evidence refusal, injection/security |
| Text-to-SQL | Semantic correctness, execution success, ambiguity, AST bypass, allowlist, cost/timeout/row limit, RBAC |
| UI/API | Auth, filter, empty/error/degraded/stale state, citations, SQL display, accessibility, concurrency |
| Operations | Alert delivery, restore, rollback, secret rotation, legal purge, runbook rehearsal |

### 12.2 Golden evaluation sets

Trước MVP release phải có versioned datasets:

1. **Enrichment set**: human-labeled sentiment/aspect/topic với review bình thường và edge cases.
2. **RAG set**: tối thiểu 50–100 câu hỏi gồm answerable, no-evidence, conflicting evidence, filter và prompt injection.
3. **Text-to-SQL set**: câu hỏi với expected SQL semantics/result, ambiguous questions và malicious/adversarial inputs.
4. **Metric fixtures**: dataset nhỏ có expected values cho tất cả Gold KPI.

Enrichment set baseline SHOULD có ít nhất 500 review, stratified theo stars, length, language, sarcasm/mixed sentiment và aspect coverage; mỗi sample có hai annotator độc lập và adjudication khi bất đồng. Labeling guide, annotator agreement và dataset version phải được lưu cùng report.

| AI quality metric | Baseline đề xuất |
|---|---|
| Overall sentiment | Macro-F1 ≥0.85 |
| Aspect extraction | Macro-F1 ≥0.75 trên supported aspects |
| Aspect sentiment | Macro-F1 ≥0.75 trên extracted/labeled aspects |
| Topic classification | Macro-F1 ≥0.75 nếu dùng closed taxonomy; nếu free-form phải có rubric/cluster stability riêng |
| Summary faithfulness | ≥90% sample không có unsupported claim theo human rubric |
| Low-confidence handling | 100% dưới threshold không được promote; coverage được báo theo slice |
| Regression tolerance | Không giảm >2 percentage points trên metric đã duyệt và không có critical safety regression |

RAG metric được tính ở claim level: retrieval Recall@k, citation correctness, groundedness, answer relevance và no-evidence refusal precision/recall. Text-to-SQL dùng result/semantic equivalence trên cùng fixture, không so chuỗi SQL thuần túy. Security corpus yêu cầu zero successful bypass trong version đã duyệt.

Mỗi model/prompt/semantic catalog/index change phải chạy regression set. Metric giảm dưới baseline hoặc security test fail sẽ chặn deploy.

### 12.3 CI quality gates

GitHub Actions tối thiểu chạy:

1. Lint, type check và unit tests.
2. Contract/schema validation.
3. dbt parse/compile và tests trên isolated CI schema.
4. SQL guardrail/security tests.
5. AI prompt/eval smoke test không chứa production data.
6. Dependency/secret/container scan.
7. Build và push immutable Docker image khi các gate pass.
8. Deploy dev/staging; production cần approval và rollback reference.

Không merge/deploy khi critical unit, dbt, contract hoặc security test fail.

---

## 13. Error handling và edge cases bắt buộc

| Tình huống | Hành vi yêu cầu |
|---|---|
| File rỗng hợp lệ so với bị truncate | Dựa trên contract/manifest; empty hợp lệ ghi 0 rows, truncate fail validation |
| Upload chưa hoàn tất | Dùng completion marker/atomic manifest; không ingest partial object |
| Cùng batch replay | No-op hoặc resume; không duplicate |
| Cùng tên file nhưng nội dung đổi | Checksum tạo version mới và audit superseded relationship |
| Review tham chiếu business/user chưa có | Giữ fact với unknown key + orphan flag; reconcile lại khi dimension đến |
| Nested attributes/category/check-in bất thường | Quarantine phần không parse được, giữ raw reference; không gây row explosion không giới hạn |
| Unicode, emoji, review rất dài hoặc chỉ whitespace | Preserve Unicode; áp size/token policy; invalid/low-signal được flag có lý do |
| Review non-English/mixed language | Ghi `language_code`; không âm thầm đánh giá theo taxonomy chưa được validated |
| Review chứa prompt injection/profanity/spam | Coi là data, không instruction; moderation/flag theo policy |
| LLM 429/timeout | Bounded exponential retry, checkpoint và backpressure |
| LLM invalid JSON/safety refusal/confidence thấp | Validate, retry khi phù hợp, sau giới hạn đưa error/DLQ; không promote |
| Model/prompt đổi giữa batch | Tách enrichment version; release map chọn đúng một version mỗi review/release |
| Gold đã build nhưng vector chưa đồng bộ | Candidate release chưa `ACTIVE`; UI tiếp tục dùng active release gần nhất và báo freshness |
| RAG không có hoặc có evidence mâu thuẫn | Refuse/nêu rõ bất đồng và cite từng nguồn; không hợp nhất thành fact chắc chắn |
| Citation không resolve | Không trả answer đó; ghi error metric và fallback an toàn |
| SQL hỏi metric/timezone mơ hồ | Yêu cầu làm rõ, không tự chọn gây hiểu nhầm |
| SQL yêu cầu PII/object cấm | Từ chối trước execution và audit policy reason |
| SQL Cartesian/scan quá lớn | Chặn hoặc yêu cầu filter; không chỉ dựa vào auto `LIMIT` |
| Query không có row | Hiển thị “không có dữ liệu trong phạm vi”, không diễn giải thành giá trị 0 |
| Kỳ trước bằng 0/sample quá nhỏ | Growth là null; ranking/insight hiển thị insufficient sample |
| LLM/vector/Snowflake unavailable | Feature báo unavailable/stale; không hiển thị dữ liệu giả; retry theo runbook |
| Legal deletion/correction | Approval + purge/tombstone xuyên live stores; sanitized rebuild/`REVOKED` event; rollback guard; restore filtering/expiry cho immutable backup + audit |

### 13.1 Error taxonomy tối thiểu

- `SOURCE_MISSING`
- `SOURCE_INCOMPLETE`
- `SOURCE_RELEASE_CONFLICT`
- `CHECKSUM_DUPLICATE`
- `SCHEMA_BREAKING`
- `MALFORMED_RECORD`
- `DQ_CRITICAL`
- `RELATIONSHIP_ORPHAN`
- `RESTAURANT_SCOPE_UNKNOWN`
- `LLM_RATE_LIMIT`
- `LLM_TIMEOUT`
- `LLM_INVALID_OUTPUT`
- `LLM_SAFETY_REFUSAL`
- `AI_LOW_CONFIDENCE`
- `EMBEDDING_FAILURE`
- `VECTOR_SYNC_LAG`
- `VECTOR_METADATA_STALE`
- `SQL_POLICY_DENIED`
- `SQL_TIMEOUT`
- `SERVING_DEPENDENCY_UNAVAILABLE`

Mỗi error code phải chỉ rõ retryable/non-retryable, severity, owner, retry count, DLQ behavior và runbook.

---

## 14. Configuration, environments và deployment

### 14.1 Environment

- `dev`: sample/synthetic data, chi phí thấp, developer self-service.
- `staging`: production-like topology, masked/approved data, full regression/evaluation.
- `prod`: controlled access, approval, monitoring, backups và on-call.

Config versioned nhưng không chứa secret:

- R2 bucket/prefix/endpoint/stage, Snowflake database/schema/warehouse/role và ChromaDB persistence path/collection.
- Source contracts và schema versions.
- DQ thresholds và publish gates.
- OpenRouter chat model slug/endpoint, prompt/taxonomy version, timeout, retry, concurrency và token cap.
- OpenRouter embedding model/version/dimension, ChromaDB collection/index version, top-k và filters.
- SQL allowlist, row/time/cost limits.
- SLO, alerts, owner/channel và retention.

### 14.2 Deployment flow

```text
Pull request
→ GitHub Actions tests/security gates
→ Build & push immutable Docker image
→ Deploy dev
→ Integration + dbt + AI regression tests
→ Deploy staging
→ Approval
→ Deploy Airflow/apps production
→ Smoke test + monitor
```

Mọi production release phải có migration plan, backward compatibility assessment, artifact digest, rollback version và owner.

### 14.3 Foundation và ranh giới công cụ

| Công cụ trong sơ đồ | Trách nhiệm trong MVP |
|---|---|
| Python | Validation, ingestion adapters, AI/serving logic và operational utilities |
| Pandas | Transform cục bộ trên bounded chunks/test fixtures; không đọc toàn bộ source lớn vào memory |
| Cloudflare R2 Standard | Private source archive, Parquet landing, manifest và quarantine qua S3-compatible API |
| Snowflake | Bronze/Silver/AI/Gold/Audit storage, SQL compute và serving views |
| dbt | Duy nhất quản lý transformation/test/docs Silver và Gold |
| OpenRouter | OpenAI-compatible provider gateway qua adapter/config cho enrichment, embedding, RAG answer và SQL generation |
| ChromaDB | Local persistent vector index cho MVP; rebuild được từ authoritative Snowflake documents/metadata |
| Apache Airflow | Schedule/control/retry/backfill/alert; không làm data warehouse |
| Streamlit | UI MVP cho dashboard, RAG và Text-to-SQL |
| Docker | Immutable runtime image cho pipeline/app components phù hợp |
| GitHub/GitHub Actions | Source control, review, CI quality gates, build và deployment workflow |

Infrastructure, IAM/RBAC, network, storage lifecycle, Snowflake objects và monitoring SHOULD được quản lý bằng Infrastructure as Code phù hợp với platform được chọn. Thay đổi production thủ công phải là break-glass, có approval và audit.

### 14.4 Cross-cutting requirements cho backlog

| ID | Yêu cầu | Ưu tiên | Verification |
|---|---|---|---|
| CON-001 | Mỗi dataset có versioned schema contract, fixture, key, PII, timestamp và evolution policy. | P0 | Contract tests và owner approval trước M2 |
| CON-002 | Source release/object, batch, dataset run, attempt và processing run có identity/cardinality không nhập nhằng. | P0 | Duplicate/reprocess/lineage tests theo mục 7.2 |
| CON-003 | Manifest, record metadata, R2 source/raw/quarantine layout, private access, scoped token và lifecycle đúng mục 7. | P0 | Schema/path/security/reconciliation tests |
| CON-004 | State machine và audit contract tách theo release/batch/file/record/invocation. | P0 | Transition, lease-expiry và crash-recovery tests |
| CON-005 | Snapshot absence/tombstone và timestamp offset/naive/DST tuân contract đã duyệt. | P0 | Full-vs-partial snapshot và time fixtures |
| REL-001 | Gold build là immutable/release-addressable và không mutate serving target. | P0 | Concurrent build/read isolation test |
| REL-002 | AI release map và vector index version định danh artifact immutable của release. | P0 | Cross-store reconciliation test |
| REL-003 | Pointer chỉ chuyển sau toàn bộ gate; fail/partial giữ active release cũ. | P0 | Failure injection ở từng promotion step |
| REL-004 | Online request pin một `data_release_id` và explicit physical refs suốt request. | P0 | Concurrent publish/request consistency test |
| REL-005 | Release retention đủ rollback window/RTO; rollback phục hồi Gold/AI/vector đồng bộ. | P0 | Quarterly rollback drill |
| REL-006 | Silver/Gold candidate artifacts isolated theo processing/data release, không dùng shared mutable input. | P0 | Concurrent source/backfill interleaving test |
| REL-007 | Invalidated/revoked/purged release không thể được active hoặc rollback tới. | P0 | CAS activation guard + legal/security revocation drill |
| NFR-001 | Đạt completeness, idempotency, DQ, freshness và reliability SLO mục 11. | P0 | Rolling SLO report trên approved workload |
| NFR-002 | Đạt warm/cold end-to-end latency và availability SLO mục 11. | P0 | Load/synthetic monitoring report |
| NFR-003 | Đạt core/AI RPO-RTO và controlled degradation. | P0 | Restore/rebuild/dependency-failure drill |
| NFR-004 | Capacity envelope được khóa và scale test không vượt budget/SLO. | P0 | `E2E-SCALE-001` report |
| CFG-001 | Dev/staging/prod có config, credentials, database/schema/warehouse/index tách biệt. | P0 | Environment isolation tests |
| CFG-002 | Threshold/model/prompt/taxonomy/semantic catalog/index đều versioned và không hard-code. | P0 | Config validation + lineage tests |
| DEP-001 | CI chạy gates mục 12.3 và tạo immutable/scanned artifact. | P0 | CI evidence + artifact digest |
| DEP-002 | Staged deployment có migration, approval, smoke test và rollback. | P0 | Staging/prod deployment rehearsal |
| COMP-001 | License/external-transfer approval có trước mọi dữ liệu thật. | P0 gate | Approval artifact + synthetic-only enforcement |
| COMP-002 | Retention, DLP, user telemetry privacy và deletion/restore suppression được thực thi. | P0 gate | Seeded-PII, lifecycle và legal-deletion drills |

---

## 15. Milestone và deliverable

| Milestone | Deliverable chính | Exit criteria |
|---|---|---|
| M0 — Product/Architecture decisions | Approved PRD, ADRs, source manifest/schema, metric dictionary, threat/license review, budget/SLO | Không còn open question P0 chặn DDL hoặc deployment |
| M1 — Foundation | Repo structure, environments, CI, Docker, secrets/config, R2/Snowflake/ChromaDB baseline và RBAC | CI pass; R2→Snowflake connectivity và negative permission tests pass |
| M2 — Ingestion & Bronze | Validation, manifest, R2 source archive/Parquet, audit, quarantine, Bronze COPY | Full source batch load và replay không duplicate |
| M3 — Silver & core Gold | dbt models/tests/docs, dimensions/facts/marts, KPI fixtures | Full/incremental equivalence; critical dbt tests pass |
| M4 — AI enrichment | Structured output, batch/rate control, validation, errors, version/cost tracking | Golden enrichment set đạt threshold; retry/replay pass |
| M5 — Embedding & RAG | OpenRouter embeddings, versioned ChromaDB collections, index sync, retrieval, chatbot/citations, RAG eval | Citation/groundedness/security targets pass |
| M6 — Text-to-SQL | Semantic views/catalog, generation, AST guardrails, read-only execution, table/chart | Semantic/security eval và role tests pass |
| M7 — Dashboard & integration | Streamlit pages, filters, freshness, DQ view, RAG/SQL tabs | Business UAT và reconciliation pass |
| M8 — Production hardening | Airflow SLO/alerts, cost, backups, load/security tests, runbooks, deploy/rollback | Launch checklist, restore drill và owner sign-off |

Mỗi milestone chỉ hoàn tất khi code, automated tests, monitoring, documentation, ownership và operational runbook tương ứng đều có đủ.

---

## 16. Acceptance criteria cấp hệ thống

MVP được chấp nhận khi đồng thời đạt tất cả điều kiện sau:

Hai gate end-to-end bắt buộc:

- `E2E-FIXTURE-001`: deterministic fixture nhỏ chứa valid, malformed, duplicate, late-arriving, correction, deletion/tombstone, AI failure và adversarial question; chạy trong CI/staging.
- `E2E-SCALE-001`: named full source release với byte/row/token/concurrency envelope đã khóa; chạy staging trước production.

1. **AC-SYS-01** — Hai gate trên chạy từ source JSON/JSONL đến dashboard, RAG và Text-to-SQL theo phạm vi phù hợp.
2. **AC-SYS-02** — Replay không tạo duplicate committed R2/Bronze/Silver/Gold/AI/ChromaDB effect. Operation đã commit không gọi provider lại; ambiguous crash call được ledger ghi nhận/costed.
3. **AC-SYS-03** — File thiếu, partial-upload, empty bất thường, wrong schema, malformed record và duplicate batch được phát hiện đúng.
4. **AC-SYS-04** — Mọi physical record được đối soát thành accepted, parsed-quarantined hoặc parse-failed với error/raw/offset reference.
5. **AC-SYS-05** — Bronze immutable qua role thông thường và đủ để rebuild Silver.
6. **AC-SYS-06** — Silver/Gold pass danh sách critical dbt tests đã versioned; metric fixtures cho kết quả expected.
7. **AC-SYS-07** — Review mới/thay đổi được enrich; committed review không đổi không gọi lại model; crash semantics đúng invocation ledger.
8. **AC-SYS-08** — AI output invalid/low-confidence đi đúng error path và không lọt enriched/release map.
9. **AC-SYS-09** — Vector index khớp enrichment map của release theo SLO và rollback/rebuild được.
10. **AC-SYS-10** — RAG chỉ trả grounded answer, citation resolve đúng và từ chối khi không đủ evidence.
11. **AC-SYS-11** — Text-to-SQL chặn DDL/DML/multi-statement/object/function ngoài allowlist và chỉ chạy bằng hardened read-only identity/session.
12. **AC-SYS-12** — Dashboard đối soát với Gold, có filter/freshness/coverage/degraded/stale state rõ ràng.
13. **AC-SYS-13** — Airflow có bounded retry, terminal-state finalizer, alert, audit, backfill, resume và atomic release pointer gate.
14. **AC-SYS-14** — CI chặn merge/deploy khi critical tests hoặc security gates fail.
15. **AC-SYS-15** — Không có secret trong repo/image/log; role/identity không thể thực hiện hành vi ngoài quyền.
16. **AC-SYS-16** — Cost/usage, data quality và offline/online correlation quan sát được.
17. **AC-SYS-17** — README, data dictionary, dbt docs, ADR, deployment guide, recovery/backfill/DLQ/legal purge runbook hoàn tất.
18. **AC-SYS-18** — Solo developer hoàn tất launch self-review theo từng responsibility hat; nếu public/production hoặc policy yêu cầu, các external Security/Legal/Operations approver ký phần tương ứng.

---

## 17. Rủi ro và phương án giảm thiểu

| Rủi ro | Mức | Giảm thiểu |
|---|---|---|
| Nguồn là snapshot chứ không có daily increment thật | Cao | Fingerprint release, snapshot diff/hash, no-op scheduler, xác nhận cadence ở M0 |
| Append-only gây duplicate khi reload snapshot | Cao | File checksum, record hash, deterministic merge/current-version logic và replay tests |
| `attributes.json` không tồn tại độc lập | Trung bình | Contract adapter tách attributes từ `business.json` |
| Business ngoài restaurant làm nhiễu mart/RAG | Cao | Versioned restaurant taxonomy/scope, unknown quarantine khỏi serving và scope coverage tests |
| Raw Parquet làm mất byte gốc | Cao | Lưu source archive bất biến và checksum; Parquet là landing tối ưu |
| Hai Airflow runs cùng load một R2 object | Cao | Manifest/checksum idempotency, lease theo source object và COPY load history; một active run cho mỗi idempotency key |
| Schema drift/nested data gây vỡ pipeline | Cao | Versioned contracts, compatibility policy, quarantine và representative fixtures |
| LLM chậm, đắt hoặc rate-limited | Cao | Incremental hash cache, batch, bounded concurrency, token cap, checkpoint và budget alert |
| AI output schema-valid nhưng sai nghĩa | Cao | Human golden set, semantic validation, confidence/publish gate và versioned taxonomy |
| Prompt injection/PII trong review | Cao | Treat-as-data, no tools, DLP/redaction, restricted logs, red-team evaluation |
| Vector index lệch source | Cao | Versioned index, reconciliation, publish alias và rebuild/rollback |
| RAG dùng cho câu hỏi định lượng | Cao | Tách Ask Reviews/Ask Data; route định lượng sang SQL |
| Citation public không tồn tại | Trung bình | Citation bền vững bằng internal review/business/source IDs và excerpt |
| SELECT-only vẫn exfiltrate/consume cost | Cao | AST allowlist, block functions/objects, read-only role, warehouse/time/scan/row limits |
| Cross-cloud latency/egress | Trung bình | Chọn cùng/near region, benchmark và cost review trước M1 |
| KPI không nhất quán | Cao | Metric dictionary, semantic views, golden fixtures và owner |
| License/privacy không cho phép use case | Critical | Legal/security gate trước production; data minimization và provider review |

---

## 18. Open questions và decision log

### 18.1 Câu hỏi P0 — phải chốt ở M0

| ID | Câu hỏi | Owner | Deadline |
|---|---|---|---|
| OQ-01 | Source là snapshot upload thủ công, scheduled release hay feed incremental? Source release ID nằm ở đâu? | Product/Data | M0 |
| OQ-02 | Package thật có những file nào? `attributes.json` độc lập hay nested trong `business.json`? | Data | M0 |
| OQ-03 | Chỉ cần photo metadata hay phải lưu binary image? | Product/Legal | M0 |
| OQ-04 | License có cho phép gửi review tới external LLM, tạo embedding và hiển thị citation không? | Legal/Security | M0 |
| OQ-05 | Ứng dụng internal hay public; ai đăng nhập; có SSO, tenant/RLS/masking không? | Product/Security | M0 |
| OQ-06 | ChromaDB persistent volume/backup path, collection naming và retention theo environment là gì? | Architecture | M0 |
| OQ-07 | SCD strategy cho business/user và correction/deletion semantics là gì? | Data Architecture | M0 |
| OQ-08 | Metric/grain/timezone/sample threshold nào là authoritative? | Product/Analytics | M0 |
| OQ-09 | Chọn OpenRouter chat/embedding model slug nào, provider routing/retention/training setting và token budget bao nhiêu? | AI/Security/Finance | M0 |
| OQ-10 | Airflow, Streamlit, registry và secrets manager chạy ở đâu? | Platform | M0 |
| OQ-11 | Monthly budget, hard cap và hành vi degrade ở 80/100% là gì? | Product/Finance | M0 |
| OQ-12 | Retention cho source, Bronze, prompt/response metadata, SQL audit, vector và backups? | Security/Data | M0 |
| OQ-13 | Ngôn ngữ chính của UI/query/evaluation là English, Vietnamese hay song ngữ? | Product | M0 |
| OQ-14 | BI chính ngoài Streamlit là Snowsight, Power BI hay Tableau? | Analytics | M0 |
| OQ-15 | SLO baseline trong mục 11 có được phê duyệt không? | Product/Operations | M0 |
| OQ-16 | Restaurant population/category inclusion, unknown và hybrid-business rule chính thức là gì? | Product/Analytics | M0 |

### 18.2 Decision log template

| Decision ID | Ngày | Quyết định | Lý do | Người duyệt | Tài liệu/ADR |
|---|---|---|---|---|---|
| DEC-001 | 2026-08-04 | Scheduler có thể daily nhưng ingest theo complete source release/snapshot diff | Không giả định nguồn có daily CDC; chống duplicate snapshot | Chờ duyệt | ADR-SOURCE-SEMANTICS ở M0 |
| DEC-002 | 2026-08-04 | MVP dùng Airflow-managed batch `COPY INTO` từ R2 external stage; không dùng auto-refresh/Snowpipe | Một owner cho load/idempotency và phù hợp giới hạn S3-compatible stage | Solo Developer | ADR-INGESTION ở M0 |
| DEC-003 | 2026-08-04 | Bronze immutable trong vận hành; legal/incident deletion là controlled exception | Cân bằng lineage với compliance | Chờ Security/Legal | ADR-RETENTION ở M0 |
| DEC-004 | 2026-08-04 | Lưu byte nguồn ở `source/`, Parquet/Snappy ở `raw/` | Giải quyết mâu thuẫn raw JSON VARIANT và landing Parquet trong sơ đồ | Chờ duyệt | ADR-STORAGE ở M0 |
| DEC-005 | 2026-08-04 | Run fail/partial không publish; tiếp tục phục vụ full release gần nhất | Giữ DAG tuyến tính và tránh mixed-version | Chờ duyệt | ADR-RELEASE ở M0 |
| DEC-006 | 2026-08-04 | Cloudflare R2 Standard thay AWS S3 | Giảm chi phí portfolio, vẫn dùng S3-compatible integration với Snowflake | Solo Developer | ADR-STORAGE ở M0 |
| DEC-007 | 2026-08-04 | Snowflake là warehouse duy nhất từ development; không dùng DuckDB fallback | Giữ implementation và portfolio tập trung vào Snowflake | Solo Developer | ADR-WAREHOUSE ở M0 |
| DEC-008 | 2026-08-04 | OpenRouter cho chat và embedding; ChromaDB local là vector store MVP | Dùng API key hiện có, giảm cloud dependency và chi phí vector serving | Solo Developer | ADR-AI-VECTOR ở M0 |
| DEC-009 | 2026-08-04 | Real Yelp Data bị chặn khỏi R2/Snowflake/OpenRouter và public demo đến khi academic eligibility/Yelp approval được xác nhận | Bundled Terms hạn chế third-party sharing/public display và yêu cầu review trước publication | Solo Developer | M0 Security/Privacy baseline |

---

## 19. Definition of Done cho từng feature

Một feature chỉ được coi là Done khi:

- Requirement ID và acceptance criteria tương ứng đã pass.
- Code review và automated tests pass.
- Data contract/schema/metric/prompt thay đổi đã versioned.
- Security/privacy/cost impact đã được xem xét.
- Logs, metrics, alert và correlation IDs cần thiết đã có.
- Documentation, owner và runbook được cập nhật.
- Đã deploy/test trên staging và có rollback path.
- Không tạo open critical defect hoặc data discrepancy chưa giải thích.

---

## 20. Ma trận truy vết với sơ đồ gốc

| Khối trong sơ đồ | Phần PRD tương ứng |
|---|---|
| 1. Data Sources | Mục 5, 7 |
| 2. Ingestion & Validation | Mục 7, 9.1 |
| 3. Data Lake (Cloudflare R2) | Mục 7.4 |
| 4. Snowflake Medallion Warehouse | Mục 8, 9.2 |
| AI Enrichment between Silver and Gold | Mục 8.4, 9.3 |
| 5. Orchestration (Airflow) | Mục 9.8 |
| 6.1 RAG Pipeline | Mục 6.2, 9.4, 9.5 |
| 6.2 Text-to-SQL Pipeline | Mục 6.3, 9.6 |
| 7. Analytics/Chatbot/Text-to-SQL | Mục 6, 9.5–9.7 |
| 8. Quality/Observability/Governance | Mục 9.9–13 |
| 9. Foundation & Tools | Mục 1, 14 |
| 10. RBAC | Mục 10.1 |
| 11. CI/CD & DevOps | Mục 12.3, 14.2 |
| Legend: data/control/AI/consumption/metadata flows | Mục 6, 8.7, 9.4–9.9 |
| Architecture notes 1–4 ở cuối sơ đồ | Mục 2.3, 8.2, 9.3, 9.8 |

---

## 21. Ma trận truy vết delivery

| Goal | User story | Requirement/Policy | Test/evidence chính | Milestone | Owner role | Blocked by |
|---|---|---|---|---|---|---|
| G-01 | US-01, US-02 | CON-001…005, ING-001…010, DWH-001…002, ORCH-001…005 | Source/ingestion replay, reconciliation, quarantine và backfill tests | M2 | Data Engineering | OQ-01/02, ADR-SOURCE/STORAGE |
| G-02 | US-02, US-03 | DWH-001…013, OBS-002…004 | dbt critical tests, full-vs-incremental, concurrent isolation, lineage, restaurant-scope và permission tests | M3 | Analytics Engineering | OQ-07/08/16, ADR-SCD/RETENTION |
| G-03 | US-08 | AI-001…011, ORCH-003/006 | Enrichment golden set, retry/idempotency, publish-gate tests | M4 | AI Engineering | OQ-04/09/11/12 |
| G-04 | US-03, US-04, US-06 | DWH-006…009, BI-001…006, SQL-001 | Metric fixtures, mart reconciliation và business UAT | M3, M7 | Analytics/Product | OQ-08/13/16 |
| G-05 | US-05 | EMB-001…007, RAG-001…007, APP-001…010 | Retrieval/RAG golden set, citation, no-evidence và injection tests | M5 | AI/Product | OQ-04/05/06/09 |
| G-06 | US-06, US-07 | SQL-001…012, APP-001…010, SEC-001/004/005 | Semantic eval, malicious SQL corpus, release-pinning, RBAC và resource-limit tests | M6 | AI/Security | OQ-05/08/10 |
| G-07 | US-02, US-08 | OBS-001…008, REL-001…007, NFR-001…004 | Monitoring/alert/cost dashboards, synthetic checks và restore/revocation drill | M8 | Platform/Operations | OQ-10/11/12/15 |
| G-08 | US-07, US-08 | ORCH-001…011, SEC-001…008, CFG-001…002, DEP-001…002, COMP-001…002 | CI evidence, secret/security scans, deploy/rollback và launch checklist | M1, M8 | Platform/Security | OQ-04/05/10/12 |
| G-05 P1 | US-05 | RAG-008…009 | Session-policy tests và privacy-safe feedback telemetry | Sau M5 | AI/Product | MVP RAG stable + privacy approval |

### 21.1 System acceptance trace

| System AC | Requirement/policy chính | Evidence |
|---|---|---|
| AC-SYS-01 | Toàn bộ P0 + CON/REL/NFR | `E2E-FIXTURE-001`, `E2E-SCALE-001` |
| AC-SYS-02 | ING-003/005, DWH-002/004/009, AI-001/008/011, EMB-002/003/007 | Replay + crash-injection report |
| AC-SYS-03 | ING-001/002/005/006/010 | Source validation fixture report |
| AC-SYS-04 | ING-007/009, CON-003/004, OBS-002 | Row/byte reconciliation report |
| AC-SYS-05 | DWH-001/002, SEC-001 | Rebuild + negative grant tests |
| AC-SYS-06 | DWH-003…009/012/013 | dbt test artifact + metric/scope/concurrency fixtures |
| AC-SYS-07 | AI-001/004/005/008/011 | Incremental/retry/ledger tests |
| AC-SYS-08 | AI-002/006/009/010 | Enrichment schema/semantic evaluation |
| AC-SYS-09 | EMB-001…007, REL-002/005 | Vector reconciliation + rollback report |
| AC-SYS-10 | RAG-001…007 | RAG golden/security evaluation |
| AC-SYS-11 | SQL-001…012, SEC-005 | Semantic/adversarial/RBAC session report |
| AC-SYS-12 | BI-001…006, APP-003 | Dashboard UAT/reconciliation/accessibility |
| AC-SYS-13 | ORCH-001…011, REL-001…007 | Failure injection, concurrency isolation, resume và pointer tests |
| AC-SYS-14 | DEP-001/002 và mục 12.3 | CI/deployment evidence |
| AC-SYS-15 | APP-001…010, SEC-001…008 | Secret/auth/authz/DLP negative tests |
| AC-SYS-16 | OBS-001…008 | Monitoring/cost/correlation dashboard evidence |
| AC-SYS-17 | CFG-001/002 và Definition of Done | Documentation/runbook review checklist |
| AC-SYS-18 | COMP-001/002, OQ gates | Solo launch evidence; external approval artifacts khi public/policy yêu cầu |

Ký hiệu `001…NNN` nghĩa là toàn bộ ID liên tục trong range được nêu. Khi tạo issue/backlog, mỗi ticket MUST ghi Goal, User Story, Requirement ID, test evidence, milestone và owner tương ứng; không đóng ticket chỉ dựa trên mô tả triển khai.

---

## Phụ lục A — Deliverable kỹ thuật tối thiểu phát sinh từ PRD

PRD này yêu cầu các artifact sau trong quá trình implementation:

- Source data contracts và fixtures.
- Metric dictionary machine-readable.
- ADR cho source semantics, SCD, Snowflake-only warehouse, R2 storage, ChromaDB deployment và OpenRouter model policy.
- R2 naming/private-access/scoped-token/lifecycle policy và Snowflake S3-compatible stage DDL.
- Snowflake DDL/RBAC grants và negative permission tests.
- dbt project với models, tests, snapshots/incremental strategy, docs và exposures.
- Airflow DAG, task config, pools, alerts và backfill/recovery runbook.
- Versioned enrichment JSON Schema, taxonomy và prompt templates.
- Vector index schema, reconciliation và rebuild/rollback job.
- RAG và Text-to-SQL service contracts.
- Streamlit UX spec/wireframe và analytics acceptance queries.
- AI/security evaluation datasets và reports.
- CI/CD pipeline, environment config examples, deployment/rollback guide.
- Monitoring dashboards, alert catalog, data retention và incident runbooks.

## Phụ lục B — Điều kiện để bắt đầu implementation

Solo developer có thể bắt đầu M1 sau khi:

1. Product Owner duyệt phạm vi P0/P1/P2 và persona chính.
2. Có sample source package thực để khóa data contract.
3. OQ-01 đến OQ-13, OQ-15 và OQ-16 có quyết định/ADR được đúng owner phê duyệt; OQ-14 không chặn nếu BI ngoài Streamlit vẫn ở P1.
4. License, authentication, privacy/external transfer, correction/deletion và retention không được thay bằng temporary default. Security/Legal phải xác nhận rõ environment nào được dùng dữ liệu thật; trước đó chỉ dùng synthetic fixtures.
5. Có cloud accounts/projects, budget guardrail và owner cho từng môi trường.
