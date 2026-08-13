# M2 private ingestion operations

Runbook này dành cho local portfolio demo: dữ liệu Olist, review text và Parquet
chỉ tồn tại trong `archive/`, private R2, Snowflake và Docker volume cục bộ. Không
đưa raw data, log có row value, XCom export hay screenshot chứa review text lên GitHub.

## 1. Khi nào được chạy

Chỉ chạy DAG thật khi cả checklist sau đều đạt:

- `archive/` có đúng chín CSV Olist và `manifest.json`; không có file thừa.
- `.env` có R2 ingestion credential, Snowflake ingestion/transform identities và
  hai đường dẫn private key trên host. Không dán giá trị secret vào command/log.
- R2 bucket vẫn private và lifecycle policy đã áp dụng.
- Snowflake warehouse có auto-suspend; trial/budget còn trong giới hạn cá nhân.
- `REVIEWLENS_ENABLE_OLIST_PIPELINE=1` chỉ bật cho phiên chạy chủ động này.

Kiểm tra offline trước khi phát sinh provider usage:

```powershell
.venv\Scripts\pytest.exe tests\test_ingestion_orchestration.py tests\test_ingestion_scenarios.py tests\test_ingestion_operations.py -q -p no:cacheprovider
.venv\Scripts\reviewlens-policy.exe --root .
.venv\Scripts\reviewlens-artifacts.exe --check
```

Nếu bất kỳ lệnh nào fail, không trigger DAG.

## 2. Build và khởi động Airflow

Sau khi source code thay đổi, refresh immutable tag rồi build:

```powershell
.venv\Scripts\reviewlens-artifacts.exe --write
$env:REVIEWLENS_ARTIFACT_TAG = & .venv\Scripts\reviewlens-artifacts.exe --print-tag
docker compose build airflow
docker compose up -d --wait --wait-timeout 180 airflow
docker compose logs --no-color --tail 100 airflow
```

Airflow chạy tại `http://127.0.0.1:8080`. `airflow standalone` in credential đăng
nhập tạm trong log local; không chụp hoặc commit credential đó.

## 3. Chạy normal ingestion

Trigger duy nhất một run; DAG đã giới hạn `max_active_runs=1` và các pool chỉ có
một slot:

```powershell
docker compose exec airflow airflow dags trigger olist_pipeline
docker compose exec airflow airflow dags list-runs -d olist_pipeline
```

Ba task M2 phải chạy tuần tự:

1. `validate_source`: kiểm tra exact file set, manifest, bytes, SHA-256 và header;
   không gọi provider, không đưa path/row text vào XCom.
2. `upload_to_r2`: chạy privacy/license preflight, upload immutable source, tạo
   raw/quarantine Parquet rồi upload create-only.
3. `copy_to_bronze`: `COPY INTO` exact object, đối chiếu source → R2 → Bronze,
   ghi load history, suspend warehouse và publish operations artifacts.

Các task M3 trở đi cố ý skip fail-closed cho đến khi milestone tương ứng được
implement. Vì vậy ở M2, ba task đầu phải success; guard đầu tiên và toàn bộ task
phía sau phải `SKIPPED`. DAG run có thể kết thúc success mà không thực thi future work.

## 4. Evidence thành công

Không export XCom hoặc raw logs. Ghi lại metadata an toàn sau:

- Airflow run ID, trạng thái và thời lượng của ba task M2.
- Mỗi dataset: source/accepted/quarantined/parse-failed/Bronze counts.
- COPY status/query ID; chỉ ID và count, không query text chứa data.
- Xác nhận reconciliation bằng `RECONCILED` và alert list rỗng.
- Xác nhận warehouse đã suspend.

Runtime ghi hai file metadata-only trong Docker volume:

```powershell
docker compose exec airflow sh -c "cat /opt/airflow/runtime/data/operations/ingestion-alerts.json"
docker compose exec airflow sh -c "grep '^reviewlens_ingestion_' /opt/airflow/runtime/data/operations/ingestion.prom"
```

Metrics chỉ dùng label `dataset`/`outcome`; source release ID, batch ID, path,
credential và row value không được xuất ra.

## 5. Replay và retry

### Retry sau lỗi tạm thời

- Không đổi attempt number trong cùng một Airflow retry.
- `validate_source` tạo lại cùng lineage ID.
- R2 object cùng key/cùng hash được verify thay vì overwrite.
- Snowflake `COPY` dùng `FORCE=FALSE`; load history trả replay/skip và không tạo
  duplicate committed effect.
- Chỉ clear task lỗi và downstream của nó; không clear task đang chạy.

Nếu cùng key nhưng khác bytes/metadata, dừng với conflict. Không xóa hoặc overwrite
object để “sửa nhanh”.

### Backfill có chủ đích

Đặt `REVIEWLENS_BACKFILL_ATTEMPT_NUMBER=2` trong `.env`, recreate Airflow service,
rồi trigger một run. Release/batch/dataset-run IDs phải giữ nguyên; attempt IDs
phải đổi. Sau drill, trả giá trị về `1`.

### Concurrent same-key

Không tăng `max_active_runs` hoặc pool slots. Nếu thấy
`INGESTION_LEASE_UNAVAILABLE`, giữ run thắng, để run còn lại retry sau khi lease
hết hoặc run thắng kết thúc. Không chạy hai owner bằng credential dùng chung để
né lease.

## 6. Late, changed và no-new-source

- Thiếu file hoặc thiếu `manifest.json`: giữ source ngoài pipeline cho đến khi bộ
  chín file hoàn tất; không tự tạo marker giả.
- Cùng filename nhưng bytes/hash thay đổi: đó là release candidate mới. Approved
  snapshot hiện tại sẽ fail preflight; review provenance/license/manifest rồi mới
  cập nhật package-owned approval bằng một code change có test.
- Không có source mới: trigger lại release cũ chỉ là replay verification; expected
  upload count bằng 0, verified replay bằng 10 và COPY không load thêm row.

## 7. Quarantine và alert response

Stable alerts:

| Code | Ý nghĩa | Xử lý |
|---|---|---|
| `INGESTION_RECONCILIATION_FAILED` | Accepted và Bronze count/hash không khớp | Dừng publish; đối chiếu manifest, R2 hash, COPY history; không sửa Bronze thủ công |
| `INGESTION_QUARANTINE_RATE_HIGH` | Tỷ lệ rejected/parse-failed vượt 5% | Kiểm tra error-code partitions và source contract; không đọc row text vào log |
| `INGESTION_TASK_ERRORS_PRESENT` | Airflow ghi nhận task error | Retry theo mục 5 sau khi xác định lỗi tạm thời; lỗi contract phải sửa source/code |
| `INGESTION_WAREHOUSE_CLEANUP_REQUIRED` | Chưa xác nhận suspend | Suspend warehouse ngay và kiểm tra auto-suspend/cost |

Quarantine artifact là private restricted data. Chỉ kiểm tra count, error code,
hash và lineage; không copy review text vào issue, screenshot hoặc Markdown.

## 8. Failure recovery và shutdown

1. Pause DAG, không trigger run mới.
2. Ghi stable error code, run/task ID và count; bỏ row values/provider response.
3. Với R2 conflict hoặc reconciliation failure, giữ nguyên object để điều tra.
4. Với lỗi credential, rotate theo `M1_CREDENTIAL_ROTATION.md`, recreate container,
   rồi retry; không in `.env`.
5. Xác nhận Snowflake warehouse suspend.
6. Tắt local service khi xong:

```powershell
docker compose down
Remove-Item Env:REVIEWLENS_ARTIFACT_TAG -ErrorAction SilentlyContinue
```

`docker compose down` không xóa named Airflow volume và không xóa private R2/Snowflake
data. Chỉ dùng `docker compose down --volumes` khi đã xác nhận muốn xóa local runtime
evidence có thể tái tạo.
