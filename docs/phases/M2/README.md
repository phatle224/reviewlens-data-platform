# M2 — Olist ingestion, R2 and immutable Bronze

M2 xây pipeline từ một snapshot Olist đủ chín file đến private R2 và immutable
Snowflake Bronze, kèm audit, quarantine và reconciliation. Phase bắt đầu bằng
synthetic fixtures; raw Olist chỉ được đọc/upload sau `IMP-M2-008` manifest,
license và privacy preflight.

| Artifact | Mục đích |
|---|---|
| [M2 checklist](./M2_CHECKLIST.md) | Trạng thái 18 work items và evidence |
| [M2 test cases](./M2_TEST_CASES.md) | Test matrix, result thực tế và live gates |
| [Implementation plan](../../IMPLEMENTATION_PLAN.md) | Dependency và acceptance của M2 |
| [Olist source manifest](../../data/OLIST_SOURCE_MANIFEST.md) | Metadata-only identity của snapshot thật |
| [Security/privacy baseline](../M0/M0_SECURITY_PRIVACY.md) | Data classification và external-transfer boundary |

Phase status hiện tại: `IN_PROGRESS`. `IMP-M2-001…009` đã hoàn tất; approved
Olist snapshot hiện được lưu create-only trong private R2 và live replay đã được
xác minh không overwrite. Bundle kế tiếp là typed raw/quarantine Parquet, audit
state machine và quarantine/replay selector (`IMP-M2-010…012`).
