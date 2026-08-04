# M1 — Foundation, Single-local Configuration and Developer Platform

Mục tiêu M1 là tạo nền móng có thể bootstrap, test và chạy trong một local runtime lặp lại bằng synthetic fixtures. Repo dùng đúng một `config/config.toml` không chứa secret; credential chỉ đến từ process environment hoặc ignored `.env`. Managed provider connectivity chỉ dùng synthetic payload; Yelp data thật không được đưa vào R2, Snowflake, OpenRouter, ChromaDB hoặc GitHub.

| Artifact | Mục đích |
|---|---|
| [M1 checklist](./M1_CHECKLIST.md) | Trạng thái 19 implementation work items và evidence |
| [M1 test cases](./M1_TEST_CASES.md) | Test matrix, command, result và live/deferred gates |
| [Foundation runbook](../../runbooks/M1_FOUNDATION.md) | Bootstrap, local services, credentials, cost-stop và recovery |
| [Final entry inputs](../M0/M0_USER_INPUTS.md) | Deployment, budget, models, account và license facts |

Phase status hiện tại: `IN_PROGRESS`.
