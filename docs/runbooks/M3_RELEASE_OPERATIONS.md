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

`IMP-M3-020` và `TC-M3-028` đã **PASS** ngày 2026-08-19: full refresh và
deterministic replay của cùng candidate pair dùng đúng chín Bronze inputs, tạo
28 aggregate fingerprints mỗi observation và trả `equivalent=true`. Warehouse
được suspend, active pointer không bị thay đổi. Graph dbt materialize bằng
`table`; không được gọi replay là incremental.

`IMP-M3-018` vẫn partial chỉ vì rollback live cần release thứ hai. Registration
prerequisite và initial activation đã hoàn tất ngày 2026-08-20. `008_release_activation_integrity.sql`
đã được re-apply idempotent, bắt procedure buộc đủ 28 expected object refs,
evidence `TEST_PASSED` mới nhất và `CREATED` event khớp definition trước
activation/rollback, đồng thời restore exact procedure `USAGE` grant sau
`CREATE OR REPLACE`. `reviewlens-m3-register-release` đã đăng ký đúng một
definition private với 28 refs; guarded `CALL` đã chuyển active pointer từ v0
sang v1 với đúng một `ACTIVATED` event. Warehouse được suspend.

## 2. Guardrails và chi phí

- Owner phải xác nhận mỗi lần chạy live full-refresh/deterministic-replay drill.
- Chỉ dùng `REVIEWLENS_WH`; không gọi R2, OpenRouter hoặc Chroma trong drill.
- Dùng **cùng cặp candidate Silver/Gold** trên hai observation, cùng immutable
  source release, ingestion batch và semantic contract. Candidate namespace vẫn
  private; không đọc/ghi active pointer khi chưa có tested release.
- Giới hạn phiên dưới 1 Snowflake credit; dừng khi thấy bất thường, và suspend
  warehouse trong `finally`.
- Lưu dbt logs, query IDs, aggregate row counts/hash report ở thư mục local bị
  ignore hoặc Snowflake `AUDIT`; không publish report có số liệu row-level.

## 3. Preflight bắt buộc

Từ root repository, chỉ output safe config summary:

```powershell
uv run dotenv -f .env run -- uv run reviewlens-config
```

The safe summary must show `data_mode=olist` for this private Olist drill. If it
shows `synthetic`, stop here: do not issue any candidate-build, grant or
fingerprint command against private data.

Chạy Bronze contract trước mỗi candidate build:

```powershell
uv run dotenv -f .env run -- uv run dbt test --project-dir dbt --profiles-dir dbt --selector m3_bronze_contract --no-partial-parse
uv run dotenv -f .env run -- uv run dbt source freshness --project-dir dbt --profiles-dir dbt --selector m3_bronze_contract --no-partial-parse
```

Nếu một command fail, không build candidate. Xem `target/run_results.json` tại
local để debug và không commit nó.

Tạo no-provider plan từ committed approved snapshot trước khi chạy live. Command
này chỉ in source/batch ID, hai candidate ID, selector và số relation; nó không
in physical namespace, không chạy dbt và không kết nối Snowflake:

```powershell
uv run reviewlens-m3-drill --print-plan
```

## 4. Điều kiện để thực hiện TC-M3-028

Sau preflight pass, planner phải chọn một immutable Silver/Gold candidate pair
và giữ nguyên pair đó trên cả hai observation. Hai run đều đọc đúng source
release, ingestion batch và semantic contract đã ghi trong processing lineage:

1. `FULL_REFRESH`: chạy toàn bộ M3 Silver và Gold từ immutable Bronze
   source/batch, ghi snapshot aggregate-only đầu tiên.
2. `DETERMINISTIC_REPLAY`: chạy lại chính selector/model variables với **cùng
   cặp candidate Silver/Gold** và không đổi input/config; ghi snapshot
   aggregate-only thứ hai.

Mỗi run phải pass Silver critical gate và complete Gold selector. Candidate fail
phải được đánh dấu failed/cleaned theo lifecycle, không được activate. Đây là
idempotency/reproducibility evidence cho static snapshot, không phải bằng chứng
incremental ingestion hay merge/backfill semantics.

Silver luôn dùng identity `REVIEWLENS_TRANSFORM_SVC`/`TRANSFORMER_ROLE`; Gold
phải dùng `REVIEWLENS_GOLD_BUILDER_SVC`/`GOLD_BUILDER_ROLE`. dbt vẫn có đúng một
local target: chỉ set override trong process hiện tại trước từng command, không
ghi credential hoặc role override vào `.env`:

```powershell
# Silver command: default transform identity from .env.
$env:DBT_SNOWFLAKE_USER = 'REVIEWLENS_TRANSFORM_SVC'
$env:DBT_SNOWFLAKE_ROLE = 'TRANSFORMER_ROLE'
$env:DBT_SNOWFLAKE_PRIVATE_KEY_PATH = $env:SNOWFLAKE_TRANSFORM_PRIVATE_KEY_PATH
$env:DBT_SNOWFLAKE_QUERY_TAG = 'reviewlens:m3:silver:full-refresh'

# Gold command: switch only the child dbt process to its least-privilege identity.
$env:DBT_SNOWFLAKE_USER = 'REVIEWLENS_GOLD_BUILDER_SVC'
$env:DBT_SNOWFLAKE_ROLE = 'GOLD_BUILDER_ROLE'
$env:DBT_SNOWFLAKE_PRIVATE_KEY_PATH = $env:SNOWFLAKE_GOLD_BUILDER_PRIVATE_KEY_PATH
$env:DBT_SNOWFLAKE_QUERY_TAG = 'reviewlens:m3:gold:full-refresh'
```

Trước Gold command, `TRANSFORMER_ROLE` phải grant `SELECT` riêng cho đúng 10
Silver relation của candidate hiện tại đến `GOLD_BUILDER_ROLE`; không tạo
schema-wide/future grant. Sau session, xóa các `DBT_SNOWFLAKE_*` override khỏi
PowerShell process.

## 5. Equivalence evidence

Mỗi run phải thu đúng 28 aggregate-only fingerprints: 10 Silver và 18 Gold
logical relations. Mỗi fingerprint gồm layer, logical name, `row_count` và
canonical `content_sha256`; không chứa physical relation, key kinh doanh hay
source row. `CandidateEquivalenceSnapshot` chỉ nhận đúng universe này và
`compare_full_refresh_to_deterministic_replay` fail-closed khi candidate pair,
source/batch/semantic contract hoặc build mode không khớp.

TC-M3-028 chỉ PASS khi report deterministic không có mismatch row count hoặc
content hash, logs cho thấy cùng candidate pair được replay, DQ/reconciliation
pass và warehouse được suspend. Nếu có mismatch, giữ report local/AUDIT, không
activate, triage theo logical relation và chạy lại từ immutable source.

## 6. Immutable release registration and transition (TC-M3-031: initial activation pass; rollback pending)

Đây là một write có kiểm soát vào Snowflake `AUDIT`, nhưng **không** gọi
`ACTIVATE_RELEASE_V1`, `ROLLBACK_RELEASE_V1` hay thay active pointer. Gate này
đã được owner xác nhận và pass ngày 2026-08-20; các command bên dưới được giữ để
phục vụ replay/handover, không chạy lại trừ khi có mục đích idempotency rõ ràng.

Trước hết apply integrity migration từ owner/bootstrap session. Nó chỉ tạo
view aggregate-only và thay hai guarded procedures; không thay pointer. Vì
`CREATE OR REPLACE PROCEDURE` bỏ grant cũ, migration này phải luôn re-grant exact
`USAGE` cho `GOLD_BUILDER_ROLE` sau khi thay procedure:

```powershell
uv run dotenv -f .env run -- uv run python -c "from pathlib import Path; from reviewlens.config import load_settings; from reviewlens.providers.snowflake import SnowflakeClient; settings=load_settings(); client=SnowflakeClient.connect_bootstrap(settings.snowflake); client.apply_sql_file(Path('infra/snowflake/008_release_activation_integrity.sql'), operation='M3 release activation integrity migration'); client.suspend_warehouse(settings.snowflake.warehouse); client.close()"
```

Sau đó, trong PowerShell mới, registration kiểm tra latest lifecycle state của
toàn bộ 10 Silver + 18 Gold refs, idempotently ghi header, 28 refs và `CREATED`
event, rồi đọc lại chính xác nội dung đã ghi. Output chỉ có release hash/count;
không in physical names hay row-level data:

```powershell
$env:REVIEWLENS_REGISTER_M3_RELEASE = 'CONFIRMED'
uv run dotenv -f .env run -- uv run reviewlens-m3-register-release --execute
Remove-Item Env:REVIEWLENS_REGISTER_M3_RELEASE
```

Nếu candidate evidence thiếu, không phải `TEST_PASSED`, header/ref đọc lại lệch
hoặc config không phải `data_mode=olist`, command fail closed trước/hoặc sau
write và `finally` luôn suspend warehouse. Không tự sửa audit row thủ công.

Sau khi registration pass, transition client chỉ gọi một owner procedure bằng
`CALL` với
**expected pointer version được truyền tường minh**, sau đó đọc lại pointer. Nó
không có SQL `UPDATE` trực tiếp và không tự retry với version mới nếu CAS bị từ
chối. Chỉ chạy sau một xác nhận mutation riêng:

```powershell
$env:REVIEWLENS_TRANSITION_M3_RELEASE = 'CONFIRMED'
uv run dotenv -f .env run -- uv run reviewlens-m3-transition-release --execute --action activate --target-release-id '<release-id-from-registration>' --expected-pointer-version 0
Remove-Item Env:REVIEWLENS_TRANSITION_M3_RELEASE
```

Thay `<release-id-from-registration>` bằng hash output của registration; không
ghi hash này vào Git. Với rollback, dùng `--action rollback`, target là prior
activated release và version hiện tại của pointer. Procedure sẽ từ chối target
sentinel/unseen/stale/incomplete thay vì tự chọn release hoặc pointer version.

Initial activation từ pointer v0 có thể được kiểm tra với release đầu tiên,
nhưng rollback server-side không thể quay về sentinel `__UNINITIALIZED__`.
Một rollback live thực cần một release immutable trước đó và một release thứ hai
khác đã được activate. Do snapshot Olist/static contract tạo candidate ID quyết
định, không tạo candidate thứ hai chỉ để diễn demo khi chưa có quyết định owner
về cost/semantic change. Giữ TC-M3-031 `PENDING` cho đến khi owner chọn gate
này hoặc chính thức điều chỉnh acceptance criteria.

### Rollback-proof release thứ hai

Sau khi owner chấp thuận, dùng duy nhất revision private `rollback-proof-v1`
theo [ADR-015](../ADR/ADR-015-m3-rollback-proof-release.md). Gate này đã pass
ngày 2026-08-20: release 2 activate từ v1→v2 và rollback về release 1 từ v2→v3;
warehouse được suspend. Revision giữ nguyên
chín source inputs, ingestion batch, semantic catalog và dbt selectors; nó chỉ
tạo processing/candidate IDs mới để chứng minh CAS rollback. Không thay raw data,
metric, semantic view, R2 object, OpenRouter hay Chroma.

Chạy private full-refresh/replay cho candidate pair mới, sau đó registration:

```powershell
$env:REVIEWLENS_RUN_M3_DRILL = 'CONFIRMED'
uv run dotenv -f .env run -- uv run reviewlens-m3-live-drill --execute --rollback-proof
Remove-Item Env:REVIEWLENS_RUN_M3_DRILL

$env:REVIEWLENS_REGISTER_M3_RELEASE = 'CONFIRMED'
uv run dotenv -f .env run -- uv run reviewlens-m3-register-release --execute --rollback-proof
Remove-Item Env:REVIEWLENS_REGISTER_M3_RELEASE
```

Sau successful registration, activate release 2 với expected pointer version 1,
rồi rollback về release 1 với expected pointer version 2. Hai target hash phải
lấy từ aggregate-only registration/pointer evidence trong cùng operator session;
không ghi hash hoặc physical identifiers vào Git. Stop ngay khi một gate fail và
suspend warehouse.

## 7. Cleanup và handoff

Sau mọi live command, suspend warehouse:

```powershell
uv run dotenv -f .env run -- uv run python -c "from reviewlens.config import load_settings; from reviewlens.providers.snowflake import SnowflakeClient; settings=load_settings(); client=SnowflakeClient.connect_bootstrap(settings.snowflake); client.suspend_warehouse(settings.snowflake.warehouse); client.close()"
```

Trước khi kết thúc phiên, chạy static suite, repository policy và status
validator. Cập nhật [M3 checklist](../phases/M3/M3_CHECKLIST.md),
[M3 test cases](../phases/M3/M3_TEST_CASES.md) và
[project status](../PROJECT_STATUS.md) với kết quả thực tế; không chuyển
`IMP-M3-018`/`TC-M3-031` sang `DONE`/`PASS` khi chưa có evidence live tương
ứng. Không public candidate/release physical names hoặc report row-level.
