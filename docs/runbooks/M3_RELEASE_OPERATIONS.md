# M3 release operations

Runbook này là gate vận hành cho M3 candidate và equivalence. Nó chỉ áp dụng cho
local portfolio runtime, Snowflake `REVIEWLENS_WH` X-Small/60 giây và private
Olist snapshot. Không đưa raw CSV, review text, row-level output, candidate
physical names, embeddings, private key, `.env` hoặc report chi tiết vào Git.

## 1. Trạng thái hiện tại

Ngày 2026-08-16, các migration prerequisite `004_audit_ledgers.sql`,
`006_processing_candidates.sql` và `007_atomic_release.sql` đã được áp dụng từ
owner session. Một smoke `ACTIVATE_RELEASE_V1` với release ID không tồn tại trả
`RELEASE_DENIED`; pointer vẫn `__UNINITIALIZED__` ở version `0`. Đây chỉ là
evidence fail-closed, không phải activation của dữ liệu Olist.

Bronze source contract có 138/138 test pass. Freshness là policy
`immutable_snapshot_90d`: cảnh báo sau 30 ngày và error sau 90 ngày. Đây là SLA
cho tuổi của private snapshot được ingest, không phải khẳng định Olist có feed
streaming hằng ngày.

`IMP-M3-020` vẫn **partial**: engine so sánh aggregate-only đã có. Với private
Olist snapshot bất biến, DWH-006 được định nghĩa là full refresh rồi
deterministic replay từ cùng candidate/source/batch/semantic contract. Graph dbt
intentionally materialize bằng `table`; không được gọi replay là incremental.
TC-M3-028 chỉ có thể PASS sau private same-candidate drill thật.

## 2. Guardrails và chi phí

- Owner phải xác nhận mỗi lần chạy live full-refresh/deterministic-replay drill.
- Chỉ dùng `REVIEWLENS_WH`; không gọi R2, OpenRouter hoặc Chroma trong drill.
- Dùng **cùng candidate ID** trên hai observation, cùng immutable source release,
  ingestion batch và semantic contract. Candidate namespace vẫn private; không
  đọc/ghi active pointer khi chưa có tested release.
- Giới hạn phiên dưới 1 Snowflake credit; dừng khi thấy bất thường, và suspend
  warehouse trong `finally`.
- Lưu dbt logs, query IDs, aggregate row counts/hash report ở thư mục local bị
  ignore hoặc Snowflake `AUDIT`; không publish report có số liệu row-level.

## 3. Preflight bắt buộc

Từ root repository, chỉ output safe config summary:

```powershell
uv run dotenv -f .env run -- uv run reviewlens-config
```

Chạy Bronze contract trước mỗi candidate build:

```powershell
uv run dotenv -f .env run -- uv run dbt test --project-dir dbt --profiles-dir dbt --selector m3_bronze_contract --no-partial-parse
uv run dotenv -f .env run -- uv run dbt source freshness --project-dir dbt --profiles-dir dbt --selector m3_bronze_contract --no-partial-parse
```

Nếu một command fail, không build candidate. Xem `target/run_results.json` tại
local để debug và không commit nó.

## 4. Điều kiện để thực hiện TC-M3-028

Sau preflight pass, planner phải chọn một immutable candidate identity và giữ
nguyên identity đó trên cả hai observation. Hai run đều đọc đúng source release,
ingestion batch và semantic contract đã ghi trong processing lineage:

1. `FULL_REFRESH`: chạy toàn bộ M3 Silver và Gold từ immutable Bronze
   source/batch, ghi snapshot aggregate-only đầu tiên.
2. `DETERMINISTIC_REPLAY`: chạy lại chính selector/model variables với **cùng
   candidate ID** và không đổi input/config; ghi snapshot aggregate-only thứ hai.

Mỗi run phải pass Silver critical gate và complete Gold selector. Candidate fail
phải được đánh dấu failed/cleaned theo lifecycle, không được activate. Đây là
idempotency/reproducibility evidence cho static snapshot, không phải bằng chứng
incremental ingestion hay merge/backfill semantics.

## 5. Equivalence evidence

Mỗi run phải thu đúng 28 aggregate-only fingerprints: 10 Silver và 18 Gold
logical relations. Mỗi fingerprint gồm layer, logical name, `row_count` và
canonical `content_sha256`; không chứa physical relation, key kinh doanh hay
source row. `CandidateEquivalenceSnapshot` chỉ nhận đúng universe này và
`compare_full_refresh_to_deterministic_replay` fail-closed khi candidate ID,
source/batch/semantic contract hoặc build mode không khớp.

TC-M3-028 chỉ PASS khi report deterministic không có mismatch row count hoặc
content hash, logs cho thấy cùng candidate ID được replay, DQ/reconciliation pass
và warehouse được suspend. Nếu có mismatch, giữ report local/AUDIT, không
activate, triage theo logical relation và chạy lại từ immutable source.

## 6. Cleanup và handoff

Sau mọi live command, suspend warehouse:

```powershell
uv run dotenv -f .env run -- uv run python -c "from reviewlens.config import load_settings; from reviewlens.providers.snowflake import SnowflakeClient; settings=load_settings(); client=SnowflakeClient.connect_bootstrap(settings.snowflake); client.suspend_warehouse(settings.snowflake.warehouse); client.close()"
```

Trước khi kết thúc phiên, chạy static suite, repository policy và status
validator. Cập nhật [M3 checklist](../phases/M3/M3_CHECKLIST.md),
[M3 test cases](../phases/M3/M3_TEST_CASES.md) và
[project status](../PROJECT_STATUS.md) với kết quả thực tế; không chuyển
`IMP-M3-020`/`TC-M3-028` sang `DONE`/`PASS` khi chưa có private same-candidate
full-refresh/deterministic-replay drill.
