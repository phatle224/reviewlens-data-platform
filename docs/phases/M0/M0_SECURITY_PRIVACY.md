# M0 Security, Privacy and Retention Baseline

## 1. Terms decision và deployment assumption

Engineering review đã đọc cả documentation/Terms PDF last updated 2023-07-07 và `Dataset_User_Agreement.pdf` 2021 đi kèm source. Dùng bản 2023 mới hơn làm controlling baseline. Kết luận an toàn:

- Chỉ dùng cho academic project theo định nghĩa của agreement; general commercial use không được phép.
- Không public display/distribute Yelp Data, đặc biệt review/user-generated content.
- Không chia sẻ/make available Data cho third party. Vì vậy gửi raw/redacted/derived review content tới OpenRouter được coi là `DENY` cho đến khi Yelp hoặc review phù hợp cho phép rõ ràng.
- Cùng restrictive interpretation áp dụng cho upload real Yelp Data lên managed R2/Snowflake. M1 connectivity dùng synthetic object/table cho đến khi eligibility/approval được xác nhận.
- Public presentation/publication của findings liên quan Data/Yelp brand cần Yelp review/approval theo agreement.
- Agreement nêu term 12 tháng từ effective access date và yêu cầu xóa mọi copy khi termination/expiry; ngày access phải được user xác nhận và theo dõi bằng `license_expires_at`.

Đây là compliance engineering interpretation, không phải tư vấn pháp lý. Khi mơ hồ, system fail closed và dùng synthetic data.

MVP là portfolio local/private của một developer. Public repository chỉ chứa code, contracts, synthetic fixtures và kiến trúc; không chứa Yelp Data hoặc derived metrics. Không có anonymous public endpoint, multi-tenancy hoặc real customer data.

Nếu Streamlit/API được đưa lên Internet, trạng thái release tự động chuyển thành `PUBLIC_CANDIDATE` và bị chặn cho đến khi có authentication, authorization, rate limit, secret backend, DLP test, dependency scan và external Terms review.

## 2. Data classification

| Data | Class | Cho vào Gold | Cho OpenRouter | Cho ChromaDB | Log |
|---|---|---|---|---|---|
| Business public attributes | Internal/public-source | Selected fields | Khi cần context | Filter metadata | IDs/counts |
| Review text | Restricted UGC | Private/local serving-safe excerpt only | `DENY` cho real Yelp text nếu chưa có Yelp approval | Real Yelp-derived vector `DENY` nếu storage/processing tạo third-party sharing; synthetic allowed | Không raw |
| User ID | Pseudonymous | Hash only | Không cần | Không cần | Hash nếu cần |
| User name/friends | Restricted | No | No | No | No |
| Query/prompt | Restricted telemetry | No raw mart | Cần cho request | No | Hash/redacted summary |
| LLM output | Internal AI artifact | Validated fields | N/A | Summary chỉ hỗ trợ retrieval | Metadata, không full payload mặc định |
| Credentials/tokens | Secret | No | Auth header only | Service boundary only | Never |

## 3. Provider and secret rules

- R2 dùng bucket-scoped Object Read & Write token cho ingestion; Snowflake stage credential không được dùng cho app/browser.
- `OPENROUTER_API_KEY` chỉ ở environment/secret backend; code chỉ kiểm tra presence, không print value.
- ChromaDB writer và reader boundary tách logic; collection candidate không được route tới serving.
- Snowflake service users không dùng `ACCOUNTADMIN`; secondary roles disabled cho Text-to-SQL session.
- Secret rotation/revocation runbook phải có trước public demo.

## 4. Retention baseline

| Artifact | Default | Ghi chú |
|---|---|---|
| Local source archive | Tối đa license term; ngoài Git | Xóa ngay khi termination/expiry hoặc Terms yêu cầu |
| R2 `source/` | 90 ngày nhưng không vượt `license_expires_at` | Private; không public URL |
| R2 raw/manifest/quarantine | 30 ngày | Quarantine restricted access |
| Snowflake Bronze/Silver/Gold | Trong thời gian project/account active | Cleanup script và release retention bắt buộc |
| OpenRouter request/response body | Không lưu raw theo mặc định | Chỉ hash, token, latency, model, status |
| AI error payload | 14 ngày, encrypted/restricted | Redact trước lưu |
| ChromaDB candidate collections | Xóa sau 7 ngày nếu không active | Giữ active + một rollback version |
| App/query audit | 30 ngày local | Không lưu raw question nếu không cần |

Các mốc trên là engineering default, không thay thế Terms/legal requirement. Real Yelp data external transfer và public data/metric display vẫn `BLOCKED` cho đến explicit Yelp approval hoặc qualified independent review.

## 5. Threat priorities

| Threat | Control bắt buộc |
|---|---|
| Prompt injection trong review | Delimit untrusted content, no tools, structured output, injection corpus |
| SQL exfiltration/write | AST parse, allowlist, read-only role, timeout/row cap, no external functions |
| Candidate data leak | Versioned collection/schema, active pointer, negative tests |
| Secret leak | Secret scan, redacting logger, no `.env` commit |
| Public R2 exposure | Private bucket policy and denied anonymous probe |
| Cost runaway | Snowflake monitor/auto-suspend, OpenRouter caps, bounded sample/concurrency |
| Restore deleted/revoked data | Tombstone/denylist reapplied during restore and rebuild |
