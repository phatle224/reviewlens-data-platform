# User Inputs Before M1 Live Setup

Không paste password, API key, access key, secret key hoặc session token vào tài liệu/chat. Secrets sẽ được đặt local ở M1.

M0 đã đóng bằng safe defaults. Trước khi M1 chạy live connectivity, hãy trả lời các giá trị không nhạy cảm sau; nếu chưa có, M1 vẫn có thể scaffold code/config và dùng synthetic fixtures.

| ID | Câu hỏi | Default nếu bạn đồng ý |
|---|---|---|
| UI-01 | Project có thuộc một ongoing academic course/educational institution, hoặc bạn có Yelp written approval không? | Nếu không: synthetic-only cho cloud/AI/public demo |
| UI-02 | Snowflake account đã tạo chưa; cloud/region/edition, expiry date và remaining credit hiển thị là gì? | Standard, region gần R2, X-SMALL |
| UI-03 | Cloudflare R2 đã bật chưa; muốn dùng location hint nào? | `apac`, private Standard bucket |
| UI-04 | Bạn cần public live URL hay chỉ local demo + video/screenshots? | Local demo + synthetic public screenshots |
| UI-05 | Chấp nhận budget mặc định không? | OpenRouter 5 USD project, 0.50 USD/day; Snowflake 10 credits/month; R2 15 GB cap |
| UI-06 | Chấp nhận model candidates không? | Gemini 2.5 Flash Lite (enrichment/RAG), Gemini 3.5 Flash (SQL), Qwen3 Embedding 8B |

Environment check tại M0 cho thấy các biến `OPENROUTER_API_KEY`, `SNOWFLAKE_*` và `R2_*` chưa được đặt trong shell hiện tại. Đây không phải lỗi; live tests `TC-M0-019`…`021` vẫn `PENDING` cho đến M1 secret setup.
