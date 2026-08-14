# M1 — Foundation operations runbook

Tài liệu này là quy trình vận hành local duy nhất cho solo developer. Nó bao phủ
bootstrap, kiểm tra credential an toàn, build/start/stop, test, kiểm soát chi phí,
khôi phục và break-glass. M1 không upload dữ liệu Olist thật, không trigger DAG và
không gọi Snowflake, R2, OpenRouter hoặc Chroma trong quy trình mặc định.

> Không gửi `.env`, private key, token, output có credential hoặc log thô cho
> Codex/GitHub. Chỉ dùng synthetic fixtures cho test và portfolio evidence.

## 1. Phạm vi và trạng thái mong đợi

Local stack hiện có ba service:

| Service | URL local | Mục đích | Credential boundary |
|---|---|---|---|
| App | `http://127.0.0.1:8501` | Authenticated foundation shell | Đọc `.env` để hiển thị boolean readiness; không gọi provider |
| Metrics | `http://127.0.0.1:9108` | `/healthz` và `/metrics` | Đọc `.env` để tạo boolean metrics; không gọi provider |
| Airflow | `http://127.0.0.1:8080` | Paused fail-closed DAG scaffold | Không nhận provider/app credential từ Compose |

Chroma không nằm trong M1 Compose vì package/server 1.5.9 chưa có bản vá cho
critical unauthenticated code-injection advisory `GHSA-f4j7-r4q5-qw2c`/
`CVE-2026-45829` tại lần review 2026-08-11. Không tự thêm Chroma image để làm
checklist chuyển xanh: [machine-readable security policy](../../deploy/chroma-security-policy.json)
và `reviewlens-policy` sẽ fail closed nếu service/dependency/lock entry xuất hiện.
Snowflake `AI.RAG_DOCUMENT` vẫn là nguồn thẩm quyền và M5 sẽ re-audit rồi mới
provision một release đã vá.

Trạng thái đúng sau khi start:

- app, metrics và Airflow đều `healthy`;
- `/healthz` có `provider_calls_performed=false`;
- `olist_pipeline` tồn tại nhưng paused; không trigger DAG trong M1;
- bốn pool `reviewlens_control`, `reviewlens_r2`, `reviewlens_snowflake` và
  `reviewlens_ai` đều có một slot;
- tất cả port chỉ bind `127.0.0.1`.

## 2. Prerequisites cho máy Windows sạch

Cài và xác minh:

- Git for Windows;
- Python 3.13;
- uv;
- Docker Desktop với Linux containers và Docker Compose;
- PowerShell 7 hoặc Windows PowerShell 5.1.

```powershell
git --version
uv --version
python --version
docker version
docker compose version
```

Nếu `docker version` chỉ có Client hoặc không có Server, mở Docker Desktop và
chờ Engine running trước khi tiếp tục. Không chạy terminal bằng tài khoản admin
nếu Docker Desktop của user hiện tại đã hoạt động.

## 3. Bootstrap clean clone

Thay URL clone bằng repository chính thức nếu remote thay đổi:

```powershell
git clone https://github.com/phatle224/reviewlens-data-platform.git
Set-Location reviewlens-data-platform
uv sync --locked --group airflow --group dbt --cache-dir .uv-cache
```

Xác minh working tree và lockfile trước khi cấu hình secret:

```powershell
git status --short
uv lock --check --cache-dir .uv-cache
.venv\Scripts\reviewlens-policy.exe --root .
```

Kết quả mong đợi: working tree sạch, lock check pass và repository policy có
`0 findings`.

## 4. Cấu hình local và credential readiness

Project chỉ có `config/config.toml`. File này không chứa secret. Tạo `.env` một
lần và không ghi đè file đã điền:

```powershell
if (-not (Test-Path -LiteralPath '.env')) {
    Copy-Item -LiteralPath '.env.example' -Destination '.env'
}
git check-ignore -v .env
```

Điền credential trực tiếp trên máy theo
[M1 credential rotation runbook](./M1_CREDENTIAL_ROTATION.md). Private key phải
nằm ngoài repository. Không paste giá trị vào command history.

Chạy summary đã loại secret:

```powershell
.venv\Scripts\reviewlens-config.exe
```

Chỉ kiểm tra các trường `credentials_configured`/`token_configured`. Không chụp
toàn bộ terminal nếu cửa sổ đang chứa command hoặc output nhạy cảm khác.

Nếu chỉ dry run trên máy sạch và chưa có provider credential, app/metrics có thể
ở `degraded`; đây là fail-closed đúng. Để đăng nhập UI cần một `APP_AUTH_TOKEN`
local riêng, không tái sử dụng OpenRouter/R2/Snowflake credential.

## 5. Artifact tag và image lifecycle

Mỗi build dùng tag sinh từ SHA-256 của Dockerfiles, package/source/config, DAG,
Compose và lockfile. Không dùng `latest`.

```powershell
.venv\Scripts\reviewlens-artifacts.exe --check
$env:REVIEWLENS_ARTIFACT_TAG = & .venv\Scripts\reviewlens-artifacts.exe --print-tag
docker compose config --quiet
docker compose build app airflow
```

Nếu `--check` báo stale sau một thay đổi source có chủ đích, review diff trước,
sau đó mới cập nhật manifest và build lại:

```powershell
git diff --check
.venv\Scripts\reviewlens-artifacts.exe --write
$env:REVIEWLENS_ARTIFACT_TAG = & .venv\Scripts\reviewlens-artifacts.exe --print-tag
docker compose build app airflow
```

### 5.1 Dọn image ReviewLens cũ, giữ final tag

Lệnh mặc định chỉ in kế hoạch JSON, không xóa. Nó chỉ xét hai repository
`reviewlens/app` và `reviewlens/airflow`, luôn giữ tag trong
`deploy/artifacts.lock.json`, image mới nhất hiện có của mỗi repository và mọi
image đang được container sử dụng:

```powershell
.venv\Scripts\reviewlens-images.exe
```

Review trường `stale`. Chỉ khi đúng các tag cũ của project mới apply. Lệnh dùng
exact reference, không dùng force và không đụng volume/build cache/image khác:

```powershell
.venv\Scripts\reviewlens-images.exe --apply
docker image ls reviewlens/app
docker image ls reviewlens/airflow
```

Không dùng `docker system prune`, `docker image prune -a` hoặc xóa base images
theo wildcard vì máy có thể chứa image của project khác. Chạy dry-run/apply sau
mỗi final image smoke thành công; không build image ở các bundle chỉ thay đổi
dbt/docs/tests và không cần container runtime.

## 6. Start và verify local stack

```powershell
$env:REVIEWLENS_ARTIFACT_TAG = & .venv\Scripts\reviewlens-artifacts.exe --print-tag
docker compose up -d --wait --wait-timeout 180 app metrics airflow
docker compose ps
```

Kiểm tra health payload mà không in credential:

```powershell
$reviewlensHealth = Invoke-RestMethod -Uri 'http://127.0.0.1:9108/healthz' -TimeoutSec 5
[pscustomobject]@{
    State = $reviewlensHealth.state
    DataMode = $reviewlensHealth.data_mode
    ProviderCalls = $reviewlensHealth.provider_calls_performed
}
```

Kiểm tra metric bắt buộc:

```powershell
$reviewlensMetrics = & curl.exe --silent --fail 'http://127.0.0.1:9108/metrics'
$reviewlensMetrics | Select-String 'reviewlens_foundation_ready'
$reviewlensMetrics | Select-String 'reviewlens_service_errors_total'
```

Kiểm tra Airflow scaffold nhưng không trigger DAG:

```powershell
docker compose exec -T airflow airflow pools list --output table
docker compose exec -T airflow airflow dags list --output table
```

Mở app tại `http://127.0.0.1:8501`. Airflow local ở port 8080; credential UI do
`airflow standalone` tạo trong local metadata volume, không dùng `APP_AUTH_TOKEN`.
Không public hai URL bằng tunnel hoặc port-forward trong giai đoạn portfolio local.

## 7. Test tiers

### 7.1 Fast offline gate trước mỗi commit

```powershell
.venv\Scripts\ruff.exe format --check src tests airflow
.venv\Scripts\ruff.exe check src tests airflow
.venv\Scripts\ruff.exe check airflow --select AIR301,AIR302,AIR303
.venv\Scripts\mypy.exe src tests
.venv\Scripts\pytest.exe -q -p no:cacheprovider
.venv\Scripts\reviewlens-policy.exe --root .
.venv\Scripts\reviewlens-artifacts.exe --check
.venv\Scripts\python.exe .agents\skills\reviewlens-dev-workflow\scripts\validate_project_status.py --root .
```

### 7.2 dbt offline gate

Các lệnh dưới parse/compile mà không introspect hay execute query:

```powershell
.venv\Scripts\dbt.exe --no-use-colors --warn-error parse `
    --project-dir dbt --profiles-dir dbt --no-partial-parse
.venv\Scripts\dbt.exe --no-use-colors --warn-error --no-populate-cache compile `
    --project-dir dbt --profiles-dir dbt --no-introspect `
    --select source_contract_registry
```

### 7.3 Dependency audit

```powershell
uv export --locked --all-groups --all-extras --no-emit-project --no-annotate `
    --cache-dir .uv-cache --output-file .uv-cache\audit-hashed-requirements.txt
.venv\Scripts\pip-audit.exe `
    --requirement .uv-cache\audit-hashed-requirements.txt `
    --strict --require-hashes --disable-pip --progress-spinner=off
```

### 7.4 Live tests

Live tests là opt-in, chỉ dùng synthetic payload và chỉ chạy khi test matrix yêu
cầu. Trước khi bật flag, đọc scenario tương ứng trong
[M1 test cases](../phases/M1/M1_TEST_CASES.md), xác nhận cleanup và maintenance
window. Không chạy hàng loạt live tests từ runbook này và không dùng Olist rows.

## 8. Stop, restart và update source

Stop local services nhưng giữ images và Airflow metadata volume:

```powershell
$env:REVIEWLENS_ARTIFACT_TAG = & .venv\Scripts\reviewlens-artifacts.exe --print-tag
docker compose down
Remove-Item Env:\REVIEWLENS_ARTIFACT_TAG -ErrorAction SilentlyContinue
```

Restart dùng lại quy trình ở mục 6. Khi pull source mới:

```powershell
git status --short
git pull --ff-only
uv sync --locked --group airflow --group dbt --cache-dir .uv-cache
.venv\Scripts\reviewlens-artifacts.exe --check
```

Nếu artifact manifest thay đổi hợp lệ, build image mới rồi dùng mục 5.1 để dọn
tag cũ. Không xóa image hiện hành trước khi image mới build và smoke pass.

## 9. Cost stop

Local M1 stack không tự gọi provider, nhưng dùng checklist này khi thấy chi phí
bất thường hoặc trước khi rời máy lâu:

1. Chạy `docker compose down` theo mục 8 để dừng orchestration/app.
2. Trong Snowsight bằng owner role, suspend cả hai warehouse:

```sql
ALTER WAREHOUSE IF EXISTS REVIEWLENS_WH SUSPEND;
ALTER WAREHOUSE IF EXISTS REVIEWLENS_SQL_WH SUSPEND;
SHOW WAREHOUSES LIKE 'REVIEWLENS%';
```

3. Xác minh OpenRouter project usage/budget. Nếu có request không rõ nguồn, disable
   project key trong OpenRouter UI rồi xử lý theo credential runbook.
4. Xác minh R2 metrics. Không xóa bucket hoặc Olist objects để xử lý chi phí; dừng
   producer trước và revoke token chỉ khi có dấu hiệu credential compromise.
5. Ghi timestamp, dịch vụ, hành động và kết quả đã sanitize vào incident note local.

Không chạy SQL cost-stop trong test offline; đây là owner-operated emergency action.

## 10. Recovery và troubleshooting

### 10.1 Artifact metadata stale

- Nếu source vừa thay đổi có chủ đích: review diff, chạy `--write`, build và smoke.
- Nếu source không nên thay đổi: dừng, xem `git status --short`; không tự ghi đè
  manifest để che một thay đổi chưa hiểu.

### 10.2 App hoặc metrics unhealthy

```powershell
$env:REVIEWLENS_ARTIFACT_TAG = & .venv\Scripts\reviewlens-artifacts.exe --print-tag
docker compose ps
docker compose logs --no-color --tail 100 app metrics
```

Không paste log nguyên bản lên issue. Chỉ chia sẻ error code/message đã kiểm tra
không chứa path key, token, review text hoặc provider response.

### 10.3 Port bị chiếm

```powershell
Get-NetTCPConnection -LocalPort 8501,8080,9108 -ErrorAction SilentlyContinue |
    Select-Object LocalAddress,LocalPort,State,OwningProcess
```

Stop process/container mình sở hữu; không đổi Compose sang `0.0.0.0` và không
disable app authentication để né lỗi port.

### 10.4 Airflow metadata local hỏng

Trước tiên stop/start bình thường và đọc log đã sanitize. Nếu metadata volume
thật sự không thể migrate và không chứa run evidence cần giữ, break-glass reset
chỉ xóa local Airflow metadata; R2, Snowflake, source data và images không bị xóa:

```powershell
$env:REVIEWLENS_ARTIFACT_TAG = & .venv\Scripts\reviewlens-artifacts.exe --print-tag
docker compose down
$airflowResetConfirmation = Read-Host 'Type DELETE_LOCAL_AIRFLOW_METADATA to continue'
if ($airflowResetConfirmation -ceq 'DELETE_LOCAL_AIRFLOW_METADATA') {
    docker volume rm reviewlens-local-airflow-runtime
}
```

Sau reset, start lại mục 6; entrypoint sẽ migrate database và import pool manifest.

## 11. Break-glass security response

Thứ tự xử lý khi nghi ngờ credential leak hoặc request trái phép:

1. Dừng local stack bằng `docker compose down`.
2. Suspend Snowflake warehouses theo mục 9.
3. Disable/revoke đúng credential bị ảnh hưởng; không rotate tất cả mù quáng.
4. Dùng [credential rotation runbook](./M1_CREDENTIAL_ROTATION.md) để cutover,
   verify credential mới, rồi revoke credential cũ.
5. Không trigger pipeline để “kiểm tra nhanh”. Chỉ chạy synthetic negative/live
   test có phạm vi sau khi owner xác nhận maintenance window.
6. Giữ evidence đã sanitize: timestamp, service, identity name, error code,
   action và result. Không lưu token, private key, raw review hoặc response body.
7. Chỉ start lại khi repository policy, credential readiness và đúng live
   identity smoke đều pass.

Break-glass không cho phép xóa bucket/database, public R2, dùng admin credential
cho runtime, disable RBAC hoặc bỏ qua data/privacy gate.

## 12. Clean-machine solo dry-run checklist

Chạy checklist này trên clone/path mới hoặc VM mới; không dùng working directory
đang phát triển:

- [ ] Prerequisite commands ở mục 2 pass.
- [ ] Clean clone, locked sync và repository policy pass.
- [ ] `.env` ignored; private keys nằm ngoài clone.
- [ ] Secret-safe config summary chạy được; missing credential chỉ tạo degraded state.
- [ ] Artifact check, Compose config và two-image build pass.
- [ ] Final image UID là 10001 và 50000; dependency checks sạch.
- [ ] App/metrics/Airflow healthy trên 127.0.0.1.
- [ ] Health payload ghi `provider_calls_performed=false`.
- [ ] Airflow có four one-slot pools và paused `olist_pipeline`.
- [ ] Fast offline, dbt offline, dependency audit và status validator pass.
- [ ] `docker compose down` cleanup container/network; named volume/images được giữ.
- [ ] Không có cloud call, Olist upload, paid AI call hoặc secret trong evidence.

Ghi ngày, OS/Python/uv/Docker versions, commit SHA, artifact tag, kết quả từng mục
và lỗi đã sanitize vào M1 test evidence. Chỉ đánh dấu TC-M1-027 `PASS` sau một
clean-machine dry run thực tế; review tài liệu trên máy phát triển chưa đủ.
