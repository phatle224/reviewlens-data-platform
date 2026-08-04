# User Inputs Before M1 Live Setup

Không paste password, API key, access key, secret key hoặc session token vào tài liệu/chat. Secrets sẽ được đặt local ở M1.

M0 đã đóng bằng safe defaults. Các giá trị không nhạy cảm dưới đây được theo dõi như M1 entry inputs; nếu chưa có, M1 vẫn có thể scaffold code/config và dùng synthetic fixtures.

| ID | Trạng thái | Giá trị đã xác nhận / default còn chờ |
|---|---|---|
| UI-01 | `RESOLVED_RESTRICTIVE` | Project cá nhân phục vụ học tập/portfolio của sinh viên, không thuộc khóa học/chương trình academic chính thức và không có Yelp written approval. Vì vậy real Yelp Data vẫn local-only; R2/Snowflake/OpenRouter/public demo chỉ dùng synthetic data. Attribution và no-endorsement không tự mở cloud/third-party/publication gate. |
| UI-02 | `RESOLVED` | Snowflake Standard Edition trên AWS, Asia Pacific (Singapore), region `AWS_AP_SOUTHEAST_1`; trial hết hạn `2026-09-03`; balance hiển thị `US$400` tại ngày xác nhận `2026-08-04`. |
| UI-03 | `RESOLVED` | R2 bucket `reviewlens-data-dev`, location hint Asia-Pacific/`apac`, Standard storage, public access disabled. |
| UI-04 | `RESOLVED` | Local demo kèm video/screenshots; chưa có public live URL. GitHub chỉ chứa source code, synthetic fixtures và safe artifacts; không chứa Yelp data/review text/embeddings/kết quả dẫn xuất. |
| UI-05 | `RESOLVED` | Chấp nhận private/local defaults và OpenRouter hard budget tối đa 5 USD/project; Snowflake/R2/Chroma guardrails giữ như M0. |
| UI-06 | `RESOLVED` | Chấp nhận model evaluation set hiện tại: Gemini 2.5 Flash Lite, Gemini 3.5 Flash và Qwen3 Embedding 8B; model vẫn phải qua catalog/evaluation gate trước release. |
| UI-07 | `RESOLVED` | `accessed_at=2026-08-04`, `license_expires_at=2027-08-04`, `term_months=12`, `status=active`. Cleanup/revocation gate dùng ngày này nhưng không thay restriction về managed cloud/external AI/publication. |

## Topology interpretation

- Snowflake `Cloud: AWS` mô tả nơi Snowflake account/compute chạy; không bắt buộc object storage phải là AWS S3.
- Snowflake AWS Singapore truy cập R2 APAC qua HTTPS S3-compatible endpoint. External stage dùng `s3compat://reviewlens-data-dev/<prefix>/` và endpoint `<R2_ACCOUNT_ID>.r2.cloudflarestorage.com`.
- R2 public access tiếp tục disabled. Snowflake xác thực bằng direct bucket-scoped credentials được inject ngoài Git; không cần anonymous/public bucket.
- Với R2 SDK, region là `auto`; không dùng `AWS_AP_SOUTHEAST_1` làm R2 region. `AWS_AP_SOUTHEAST_1` chỉ là Snowflake deployment region.
- Cloudflare khuyến nghị R2 location hint `apac` cho Snowflake AWS `ap-southeast-1`, đúng với bucket hiện tại.

Local environment check tại M0 cho thấy các biến `OPENROUTER_API_KEY`, `SNOWFLAKE_*` và `R2_*` chưa được đặt trong shell hiện tại. Đây không phải lỗi; live tests `TC-M0-019`…`021` đang `DEFERRED` sang M1 secret setup và chỉ dùng synthetic payload.
