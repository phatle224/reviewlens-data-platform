# M0 — Product, Data and Architecture Decisions

| Artifact | Mục đích |
|---|---|
| [M0 checklist](./M0_CHECKLIST.md) | Trạng thái 19 implementation work items và exit gate |
| [M0 test cases](./M0_TEST_CASES.md) | Test matrix, expected result, current result và M1 automation mapping |
| [Decision register](./M0_DECISION_REGISTER.md) | Accepted decisions và user inputs còn cần xác minh |
| [Source profile](./M0_SOURCE_PROFILE.md) | Local archive fingerprint, source set và snapshot semantics |
| [Product/data baseline](./M0_PRODUCT_DATA_BASELINE.md) | Portfolio scope, restaurant taxonomy, SCD/time và metrics |
| [Security/privacy](./M0_SECURITY_PRIVACY.md) | Classification, transfer, retention và threat controls |
| [SLO/budget](./M0_SLO_BUDGET.md) | Capacity, cost caps, SLO và degradation behavior |
| [AI evaluation](./M0_AI_EVALUATION_PLAN.md) | Model candidates, versions, golden sets và release gates |
| [User inputs](./M0_USER_INPUTS.md) | Các xác nhận không nhạy cảm cần có để đóng M0 |

ADRs nằm tại [`docs/ADR`](../../ADR/). Phase status hiện là `COMPLETE`; live R2/Snowflake/OpenRouter smokes được chuyển sang M1 và chỉ dùng synthetic data cho đến khi Terms eligibility/approval thay đổi.
