# M1 — Foundation, Single-local Configuration and Developer Platform

Mục tiêu M1 là tạo nền móng có thể bootstrap, test và chạy trong một local runtime lặp lại bằng synthetic Olist-shaped fixtures. Repo dùng đúng một `config/config.toml` không chứa secret; credential chỉ đến từ process environment hoặc ignored `.env`. Olist là active real-data source, nhưng M1 không upload raw snapshot: raw CSV/review/embedding/row-level artifacts luôn ngoài Git; private R2/Snowflake processing bắt đầu ở M2 sau manifest/privacy gate và external AI chỉ nhận minimized DLP-approved projection.

| Artifact | Mục đích |
|---|---|
| [M1 checklist](./M1_CHECKLIST.md) | Trạng thái 20 implementation work items và evidence |
| [M1 test cases](./M1_TEST_CASES.md) | Test matrix, command, result và live/deferred gates |
| Foundation runbook — planned in `IMP-M1-019` | Bootstrap, local services, credentials, cost-stop và recovery |
| [Credential rotation runbook](../../runbooks/M1_CREDENTIAL_ROTATION.md) | Dedicated runtime identities, activation, rotation, revocation và recovery |
| [dbt foundation](../../../dbt/README.md) | Snowflake-only single-local profile, nine Bronze sources, contracts, macros và verification commands |
| [Airflow scaffold](../../../airflow/README.md) | Airflow 3 `olist_pipeline`, fail-closed task graph, resource pools và offline verification |
| [Snowflake foundation](../../../infra/snowflake/README.md) | Foundation/RBAC/identity contracts và versioned append-only audit migrations |
| [Observability logging](../../../src/reviewlens/observability/logging.py) | JSONL events, context-local correlation IDs và recursive secret/PII/restricted-text redaction |
| [Authenticated app shell](../../../src/reviewlens/app/streamlit_app.py) | Loopback-only Streamlit entrypoint, local token gate và provider-free configuration readiness |
| [Foundation CI](../../../.github/workflows/ci.yml) | Locked quality, dbt, repository-policy, dependency-audit và status gates |
| [Repository policy](../../../src/reviewlens/ci/policy.py) | Fail-closed scan cho secret, raw row artifacts và pre-container guard |
| [Final entry inputs](../M0/M0_USER_INPUTS.md) | Deployment, budget, models, account và license facts |

Phase status hiện tại: `IN_PROGRESS`.
