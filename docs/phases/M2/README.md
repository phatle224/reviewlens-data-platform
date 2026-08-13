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

Phase status hiện tại: `IN_PROGRESS`. `IMP-M2-001…012` đã hoàn tất. Source gốc
được lưu create-only trong private R2; pipeline local hiện có thể tạo typed
raw/quarantine Parquet, phân loại replay/duplicate, giải thích lỗi dòng/file và
ghi audit append-only có lease. Bundle kế tiếp là nine-table Bronze DDL, R2 stage
contract và Airflow-managed `COPY INTO` (`IMP-M2-013…015`).
