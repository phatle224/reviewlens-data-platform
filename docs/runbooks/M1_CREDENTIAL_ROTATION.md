# M1 — Hướng dẫn tạo, cấu hình và xoay vòng credential

Tài liệu này dành cho project portfolio chạy local trên Windows/PowerShell. Làm
lần lượt từ trên xuống; không cần gửi bất kỳ key, token, password hoặc nội dung
`.env` nào cho Codex.

> Quy tắc quan trọng: chỉ public key Snowflake được dán vào Snowsight. Private
> key, passphrase, R2 Secret Access Key và OpenRouter key chỉ được lưu cục bộ.

## 1. Hiện tại bạn đã có gì và còn thiếu gì?

Kết quả kiểm tra an toàn ngày 2026-08-05:

| Credential | Trạng thái | Có cần làm ngay? |
|---|---|---|
| Snowflake bootstrap (`SNOWFLAKE_*`) | Đã có; private-key path hợp lệ | Không tạo lại |
| R2 bootstrap (`R2_*`) | Đã có | Không tạo lại |
| OpenRouter (`OPENROUTER_API_KEY`) | Đã có | Không tạo lại |
| App (`APP_AUTH_TOKEN`) | Đã có | Không tạo lại |
| 8 Snowflake runtime key pairs | Đã cấu hình; live JWT auth pass | Không tạo lại |
| R2 ingestion credential | Đã cấu hình; write/read/delete smoke pass | Không tạo lại |
| R2 Snowflake-stage credential | Đã cấu hình; read-only + COPY smoke pass | Không tạo lại |
| Chroma local token | Đã cấu hình | Chroma adapter/service được nối ở `IMP-M1-011/017` |

Các biến bootstrap hiện tại dùng để người vận hành provision/test hạ tầng. Các
biến runtime mới dùng cho application và không được dùng chung admin identity.

## 2. Checklist nhanh

- [x] Tạo thư mục key bên ngoài repository.
- [x] Tạo 8 Snowflake private/public key pairs.
- [x] Dán 8 public keys vào Snowflake và enable 8 service users.
- [x] Điền 8 private-key paths vào `.env`.
- [x] Tạo R2 token `reviewlens-ingest-local` — Object Read & Write.
- [x] Tạo R2 token `reviewlens-stage-local` — Object Read Only.
- [x] Điền 4 giá trị R2 runtime vào `.env`.
- [x] Tạo `CHROMA_AUTH_TOKEN` cục bộ.
- [x] Chạy readiness check; không gửi output chứa secret.
- [x] Báo cho Codex và hoàn tất initial live smoke tests.

## 3. Chuẩn bị PowerShell

Mở PowerShell tại repository:

```powershell
Set-Location 'D:\project\reviewlens-data-platform'
Test-Path -LiteralPath '.env'
git check-ignore -v .env
```

Kết quả đúng:

- `Test-Path` trả về `True`.
- `git check-ignore` cho biết `.env` được ignore bởi `.gitignore`.

Máy hiện có OpenSSL đi kèm Git for Windows tại đường dẫn dưới đây. Kiểm tra:

```powershell
$reviewlensOpenSsl = 'C:\Program Files\Git\usr\bin\openssl.exe'
Test-Path -LiteralPath $reviewlensOpenSsl
& $reviewlensOpenSsl version
```

Nếu `Test-Path` trả về `False`, dừng tại đây và báo lại lỗi; không tải OpenSSL
từ website không rõ nguồn gốc.

## 4. Tạo 8 Snowflake key pairs

### 4.1 Tại sao cần 8 key pairs?

Mỗi thành phần runtime có một Snowflake user và role riêng. Nếu một key bị lộ,
quyền truy cập chỉ nằm trong đúng service đó.

| Tên file | Snowflake user | Role | Biến path trong `.env` |
|---|---|---|---|
| `ingest.p8` | `REVIEWLENS_INGEST_SVC` | `INGEST_ROLE` | `SNOWFLAKE_INGEST_PRIVATE_KEY_PATH` |
| `transform.p8` | `REVIEWLENS_TRANSFORM_SVC` | `TRANSFORMER_ROLE` | `SNOWFLAKE_TRANSFORM_PRIVATE_KEY_PATH` |
| `ai_enrich.p8` | `REVIEWLENS_AI_ENRICH_SVC` | `AI_ENRICH_ROLE` | `SNOWFLAKE_AI_ENRICH_PRIVATE_KEY_PATH` |
| `vector_indexer.p8` | `REVIEWLENS_VECTOR_INDEXER_SVC` | `VECTOR_INDEXER_ROLE` | `SNOWFLAKE_VECTOR_INDEXER_PRIVATE_KEY_PATH` |
| `gold_builder.p8` | `REVIEWLENS_GOLD_BUILDER_SVC` | `GOLD_BUILDER_ROLE` | `SNOWFLAKE_GOLD_BUILDER_PRIVATE_KEY_PATH` |
| `analytics.p8` | `REVIEWLENS_ANALYTICS_SVC` | `ANALYST_ROLE` | `SNOWFLAKE_ANALYTICS_PRIVATE_KEY_PATH` |
| `text_to_sql.p8` | `REVIEWLENS_TEXT_TO_SQL_SVC` | `TEXT_TO_SQL_ROLE` | `SNOWFLAKE_TEXT_TO_SQL_PRIVATE_KEY_PATH` |
| `rag.p8` | `REVIEWLENS_RAG_SVC` | `RAG_ROLE` | `SNOWFLAKE_RAG_PRIVATE_KEY_PATH` |

Snowflake yêu cầu tối thiểu RSA 2048-bit và hỗ trợ PKCS#8. Tham khảo
[Snowflake key-pair authentication](https://docs.snowflake.com/en/user-guide/key-pair-auth).

### 4.2 Tạo thư mục bên ngoài repository

Chạy nguyên khối sau:

```powershell
$reviewlensKeyDir = Join-Path $env:USERPROFILE '.reviewlens\keys\runtime'
New-Item -ItemType Directory -Force -Path $reviewlensKeyDir | Out-Null
$reviewlensKeyDir
```

Không tạo key bên trong `D:\project\reviewlens-data-platform`.

### 4.3 Tạo private/public keys

Với local portfolio, hướng dẫn mặc định dùng private key PKCS#8 không có
passphrase và khóa thư mục bằng Windows ACL. Cách này giảm lỗi nhập 8 passphrase;
không dùng lựa chọn này cho production hoặc máy dùng chung.

Chạy nguyên khối:

```powershell
$reviewlensOpenSsl = 'C:\Program Files\Git\usr\bin\openssl.exe'
$reviewlensKeyDir = Join-Path $env:USERPROFILE '.reviewlens\keys\runtime'
$reviewlensServices = @(
    'ingest',
    'transform',
    'ai_enrich',
    'vector_indexer',
    'gold_builder',
    'analytics',
    'text_to_sql',
    'rag'
)

foreach ($reviewlensService in $reviewlensServices) {
    $reviewlensPrivateKey = Join-Path $reviewlensKeyDir "$reviewlensService.p8"
    $reviewlensPublicKey = Join-Path $reviewlensKeyDir "$reviewlensService.pub"

    if ((Test-Path -LiteralPath $reviewlensPrivateKey) -or
        (Test-Path -LiteralPath $reviewlensPublicKey)) {
        throw "Key file already exists for $reviewlensService. Stop to avoid overwriting it."
    }

    & $reviewlensOpenSsl genrsa 2048 |
        & $reviewlensOpenSsl pkcs8 -topk8 -inform PEM -out $reviewlensPrivateKey -nocrypt
    if ($LASTEXITCODE -ne 0) { throw "Private-key generation failed: $reviewlensService" }

    & $reviewlensOpenSsl rsa -in $reviewlensPrivateKey -pubout -out $reviewlensPublicKey
    if ($LASTEXITCODE -ne 0) { throw "Public-key generation failed: $reviewlensService" }
}

$reviewlensPrincipal = "$env:USERDOMAIN\$env:USERNAME"
icacls $reviewlensKeyDir /inheritance:r
icacls $reviewlensKeyDir /grant:r "${reviewlensPrincipal}:(OI)(CI)F"
```

Xác minh chỉ bằng tên file, không mở hoặc gửi nội dung private key:

```powershell
Get-ChildItem -LiteralPath $reviewlensKeyDir -File |
    Select-Object Name, Length
```

Kết quả phải có 16 file: 8 file `.p8` và 8 file `.pub`.

Nếu muốn dùng key mã hóa, tạo từng key bằng lệnh chính thức dưới đây và điền
passphrase tương ứng vào `.env`. Không để passphrase trên command line:

```powershell
& $reviewlensOpenSsl genrsa 2048 |
    & $reviewlensOpenSsl pkcs8 -topk8 -v2 des3 -inform PEM -out 'C:\path\service.p8'
```

## 5. Đăng ký 8 public keys trong Snowflake

### 5.1 Tạo SQL từ các `.pub` files

Đoạn PowerShell sau chỉ đọc **public keys**, tạo SQL và copy SQL vào clipboard.
Nó không đọc private keys.

```powershell
$reviewlensKeyDir = Join-Path $env:USERPROFILE '.reviewlens\keys\runtime'
$reviewlensMappings = @(
    @{ Slug='ingest';        User='REVIEWLENS_INGEST_SVC';         Role='INGEST_ROLE' },
    @{ Slug='transform';     User='REVIEWLENS_TRANSFORM_SVC';      Role='TRANSFORMER_ROLE' },
    @{ Slug='ai_enrich';     User='REVIEWLENS_AI_ENRICH_SVC';      Role='AI_ENRICH_ROLE' },
    @{ Slug='vector_indexer';User='REVIEWLENS_VECTOR_INDEXER_SVC'; Role='VECTOR_INDEXER_ROLE' },
    @{ Slug='gold_builder';  User='REVIEWLENS_GOLD_BUILDER_SVC';   Role='GOLD_BUILDER_ROLE' },
    @{ Slug='analytics';     User='REVIEWLENS_ANALYTICS_SVC';      Role='ANALYST_ROLE' },
    @{ Slug='text_to_sql';   User='REVIEWLENS_TEXT_TO_SQL_SVC';    Role='TEXT_TO_SQL_ROLE' },
    @{ Slug='rag';           User='REVIEWLENS_RAG_SVC';            Role='RAG_ROLE' }
)

$reviewlensSql = foreach ($reviewlensMapping in $reviewlensMappings) {
    $reviewlensPublicPath = Join-Path $reviewlensKeyDir "$($reviewlensMapping.Slug).pub"
    if (-not (Test-Path -LiteralPath $reviewlensPublicPath)) {
        throw "Missing public key: $($reviewlensMapping.Slug).pub"
    }

    $reviewlensPublicBody = (Get-Content -Raw -LiteralPath $reviewlensPublicPath) `
        -replace '-----BEGIN PUBLIC KEY-----', '' `
        -replace '-----END PUBLIC KEY-----', '' `
        -replace '\s', ''

    @"
ALTER USER $($reviewlensMapping.User) ADD KEY PAIR REVIEWLENS_RUNTIME
  PUBLIC_KEY = '$reviewlensPublicBody'
  ROLE_RESTRICTION = '$($reviewlensMapping.Role)'
  DAYS_TO_EXPIRY = 90
  COMMENT = 'ReviewLens local runtime key';
ALTER USER $($reviewlensMapping.User) SET DISABLED = FALSE;
SHOW USER KEY PAIRS FOR USER $($reviewlensMapping.User);
"@
}

($reviewlensSql -join "`r`n") | Set-Clipboard
Write-Host 'Registration SQL copied to clipboard.'
```

`ROLE_RESTRICTION` khóa key vào đúng role; nó không tự cấp role. Các role đã được
`002_roles.sql`/`003_service_identities.sql` cấp trước đó. Snowflake chỉ lưu public
key, không lưu private key. Xem cú pháp chính thức tại
[ALTER USER … ADD KEY PAIR](https://docs.snowflake.com/en/sql-reference/sql/alter-user-add-key-pair).

Ví dụ sau khi PowerShell resolve mapping ingestion, SQL phải có đúng dạng này
(script sẽ thay placeholder bằng public-key body thật):

```sql
ALTER USER REVIEWLENS_INGEST_SVC ADD KEY PAIR REVIEWLENS_RUNTIME
  PUBLIC_KEY = '<PUBLIC_KEY_BODY>'
  ROLE_RESTRICTION = 'INGEST_ROLE'
  DAYS_TO_EXPIRY = 90
  COMMENT = 'ReviewLens local runtime key';
```

### 5.2 Chạy SQL trong Snowsight

1. Mở Snowsight.
2. Chuyển role ở góc worksheet sang `ACCOUNTADMIN`.
3. Tạo worksheet mới, đặt tên `reviewlens-register-runtime-keys`.
4. Nhấn `Ctrl+V`; bạn sẽ thấy 8 nhóm `ALTER USER ... ADD KEY PAIR`.
5. Chọn **Run All**.
6. Mỗi `SHOW USER KEY PAIRS` phải có:
   - `name`: `REVIEWLENS_RUNTIME`;
   - `role_scope`: đúng role trong bảng mapping;
   - `status`: `ACTIVE`;
   - `expires_at`: khoảng 90 ngày sau ngày tạo.

Nếu gặp lỗi `key pair already exists`, không chạy lại `ADD KEY PAIR` và không xóa
key ngay. Chụp phần error message không chứa public-key body rồi báo cho Codex.

### 5.3 Kiểm tra fingerprint

Ví dụ với ingestion:

```powershell
$reviewlensOpenSsl = 'C:\Program Files\Git\usr\bin\openssl.exe'
$reviewlensKeyDir = Join-Path $env:USERPROFILE '.reviewlens\keys\runtime'
& $reviewlensOpenSsl rsa -pubin `
    -in (Join-Path $reviewlensKeyDir 'ingest.pub') `
    -outform DER |
    & $reviewlensOpenSsl dgst -sha256 -binary |
    & $reviewlensOpenSsl enc -base64
```

So sánh kết quả với cột `fingerprint` của:

```sql
SHOW USER KEY PAIRS FOR USER REVIEWLENS_INGEST_SVC;
```

Nếu Snowflake hiển thị tiền tố `SHA256:`, chỉ so sánh phần phía sau. Làm tương tự
cho 7 user còn lại. Không tiếp tục nếu fingerprint không khớp.

## 6. Điền Snowflake runtime paths vào `.env`

Chạy đoạn sau để tạo đúng 8 dòng path bằng đường dẫn thật trên máy:

```powershell
$reviewlensKeyDir = Join-Path $env:USERPROFILE '.reviewlens\keys\runtime'
@(
    "SNOWFLAKE_INGEST_PRIVATE_KEY_PATH=$(Join-Path $reviewlensKeyDir 'ingest.p8')",
    "SNOWFLAKE_TRANSFORM_PRIVATE_KEY_PATH=$(Join-Path $reviewlensKeyDir 'transform.p8')",
    "SNOWFLAKE_AI_ENRICH_PRIVATE_KEY_PATH=$(Join-Path $reviewlensKeyDir 'ai_enrich.p8')",
    "SNOWFLAKE_VECTOR_INDEXER_PRIVATE_KEY_PATH=$(Join-Path $reviewlensKeyDir 'vector_indexer.p8')",
    "SNOWFLAKE_GOLD_BUILDER_PRIVATE_KEY_PATH=$(Join-Path $reviewlensKeyDir 'gold_builder.p8')",
    "SNOWFLAKE_ANALYTICS_PRIVATE_KEY_PATH=$(Join-Path $reviewlensKeyDir 'analytics.p8')",
    "SNOWFLAKE_TEXT_TO_SQL_PRIVATE_KEY_PATH=$(Join-Path $reviewlensKeyDir 'text_to_sql.p8')",
    "SNOWFLAKE_RAG_PRIVATE_KEY_PATH=$(Join-Path $reviewlensKeyDir 'rag.p8')"
)
```

Copy 8 dòng output và thay 8 dòng cùng tên trong `.env`. Không copy ký hiệu ví dụ
như `<path>`; output đã là absolute path thật.

Với workflow không passphrase ở mục 4.3, để trống các biến
`SNOWFLAKE_*_PRIVATE_KEY_PASSPHRASE`. Nếu bạn chọn key mã hóa, điền đúng passphrase
của từng key.

## 7. Tạo hai R2 runtime credentials

Cloudflare gọi credential S3-compatible là `Access Key ID` và
`Secret Access Key`. Secret chỉ được hiển thị một lần. Hướng dẫn chính thức:
[Cloudflare R2 API tokens](https://developers.cloudflare.com/r2/api/tokens/).

### 7.1 Token cho ingestion

1. Vào Cloudflare Dashboard → **R2 Object Storage** → **Overview**.
2. Trong **Account Details**, tại **API Tokens**, chọn **Manage**.
3. Chọn **Create Account API token**.
4. Name: `reviewlens-ingest-local`.
5. Permissions: **Object Read & Write**.
6. Specify bucket: chỉ chọn `reviewlens-data-dev`.
7. Tạo token.
8. Copy hai giá trị được hiển thị một lần vào `.env`:

```dotenv
R2_INGEST_ACCESS_KEY_ID=giá_trị_Access_Key_ID
R2_INGEST_SECRET_ACCESS_KEY=giá_trị_Secret_Access_Key
```

Không copy nguyên chữ `giá_trị_...`; thay chúng bằng hai giá trị Cloudflare vừa
hiển thị. Không dán hai giá trị đó vào chat hoặc screenshot.

Không chọn `Admin Read & Write` và không chọn tất cả buckets.

### 7.2 Token read-only cho Snowflake external stage

Lặp lại quy trình trên với:

- Name: `reviewlens-stage-local`.
- Permissions: **Object Read only**.
- Bucket: chỉ `reviewlens-data-dev`.
- Điền vào:

```dotenv
R2_STAGE_ACCESS_KEY_ID=giá_trị_Access_Key_ID
R2_STAGE_SECRET_ACCESS_KEY=giá_trị_Secret_Access_Key
```

Tương tự, thay `giá_trị_...` bằng credential của token stage vừa tạo.

Hai token phải khác nhau. Giữ các biến bootstrap `R2_ACCOUNT_ID`,
`R2_ACCESS_KEY_ID` và `R2_SECRET_ACCESS_KEY` hiện có; chưa xóa chúng.

Hai cặp runtime đã được nối vào adapter: ingestion upload/cleanup object và
Snowflake external stage dùng stage token read-only. Bộ `R2_*` cũ chỉ còn cho
bootstrap smoke riêng; runtime path không fallback sang bộ này.

## 8. OpenRouter

`OPENROUTER_API_KEY` hiện đã được cấu hình nên không cần tạo lại.

Nếu sau này cần rotate bằng giao diện:

1. Vào OpenRouter → **API Keys**.
2. Tạo key mới tên có ngày, ví dụ `reviewlens-local-2026-11`.
3. Đặt credit limit không vượt quá `5 USD`; mức `3 USD` hiện tại là phù hợp.
4. Thay `OPENROUTER_API_KEY` trong `.env`.
5. Test key mới bằng synthetic input.
6. Kiểm tra Activity/Usage đã chuyển sang key mới rồi mới disable/delete key cũ.

Thứ tự chuẩn là create → update/test → delete old. Xem
[OpenRouter API key rotation](https://openrouter.ai/docs/cookbook/administration/api-key-rotation).
Management API key chỉ dùng quản trị, không đặt vào `OPENROUTER_API_KEY`.

## 9. Tạo Chroma token cục bộ

`CHROMA_AUTH_TOKEN` không lấy từ website. Đây là token do bạn tự tạo cho local
service boundary.

Chạy PowerShell:

```powershell
$reviewlensBytes = New-Object byte[] 32
$reviewlensRng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$reviewlensRng.GetBytes($reviewlensBytes)
$reviewlensRng.Dispose()
$reviewlensChromaToken = [Convert]::ToBase64String($reviewlensBytes).Replace('+','-').Replace('/','_').TrimEnd('=')
$reviewlensChromaToken | Set-Clipboard
Remove-Variable reviewlensChromaToken, reviewlensBytes
Write-Host 'Chroma token copied to clipboard.'
```

Mở `.env`, tìm dòng `CHROMA_AUTH_TOKEN=` và paste clipboard ngay sau dấu `=`.
Không dùng lại `APP_AUTH_TOKEN` hoặc OpenRouter key.

Chroma chưa được provision/index ở M1 hiện tại. Token sẽ được app/Compose sử dụng
khi hoàn thành `IMP-M1-011` và `IMP-M1-017`.

## 10. Kiểm tra `.env` mà không in secret

Đóng các process local đang chạy để chúng không giữ config cũ, sau đó chạy:

```powershell
.venv\Scripts\python.exe -c "from reviewlens.config import load_settings; from reviewlens.security.credentials import inspect_credential_readiness; print(inspect_credential_readiness(load_settings()).model_dump_json(indent=2))"
```

Kết quả mong đợi: mọi trường boolean là `true`. Output không chứa credential.

Kiểm tra key files tồn tại mà không in path hoặc nội dung:

```powershell
.venv\Scripts\python.exe -c "import os; from reviewlens.config import load_environment_values,load_settings; s=load_settings(); v=load_environment_values(); print({i.service.value: os.path.isfile(v.get(i.private_key_path_env,'')) for i in s.identities.snowflake_services})"
```

Kết quả mong đợi: cả 8 service đều là `True`.

Sau đó chỉ cần nhắn cho Codex:

> Đã tạo và đăng ký 8 Snowflake runtime keys, enable users, tạo hai R2 runtime
> tokens và Chroma token; hãy chạy readiness và live smoke tests.

Không paste `.env`, private key, passphrase hoặc screenshot có secret.

## 11. Lỗi thường gặp

### `openssl` không được nhận diện

Dùng đúng biến `$reviewlensOpenSsl` trỏ đến OpenSSL của Git for Windows, không
chỉ gõ `openssl`.

### `Key file already exists`

Script cố ý dừng để không ghi đè private key. Không xóa file ngay. Kiểm tra key đó
đã được đăng ký trong Snowflake chưa rồi mới quyết định rotate hoặc tạo lại.

### `key pair already exists` trong Snowflake

Key name `REVIEWLENS_RUNTIME` đã tồn tại. Chạy:

```sql
SHOW USER KEY PAIRS FOR USER REVIEWLENS_INGEST_SVC;
```

Không dùng `ADD` lần nữa. Nếu cần thay key, dùng quy trình rotation ở mục 12.

### Authentication failed sau khi enable user

Kiểm tra theo thứ tự:

1. `.env` trỏ đúng file `.p8`, không phải `.pub`.
2. User/role đúng mapping.
3. Fingerprint local khớp Snowflake.
4. Key chưa hết hạn và status là `ACTIVE`.
5. Nếu key mã hóa, passphrase đúng biến của service.

### Readiness vẫn là `false`

Readiness kiểm tra đúng tên biến mới. Các biến bootstrap `SNOWFLAKE_PRIVATE_KEY_PATH`
và `R2_ACCESS_KEY_ID` không thay thế 8 Snowflake paths hoặc hai cặp `R2_INGEST_*`/
`R2_STAGE_*`.

## 12. Rotation và revocation

Phần này chỉ dùng sau khi initial setup đã pass.

### 12.1 Snowflake zero-downtime rotation

Tạo key pair mới với filename khác, xác minh public key rồi chạy:

```sql
ALTER USER REVIEWLENS_INGEST_SVC ROTATE KEY PAIR REVIEWLENS_RUNTIME
  PUBLIC_KEY = '<NEW_PUBLIC_KEY_BODY>'
  EXPIRE_ROTATED_KEY_PAIR_AFTER_HOURS = 24;
```

Sau đó:

1. Cập nhật path/passphrase trong `.env` sang private key mới.
2. Restart service và chạy positive/negative permission smoke.
3. Xác minh query tag/user/role đúng.
4. Sau grace period, xác minh **old key fails**.
5. Chỉ xóa private key cũ sau khi key mới pass.

### 12.2 M1 isolated rotation smoke

Đây là bước còn lại để đóng `TC-M1-037`. Test dùng `REVIEWLENS_ANALYTICS_SVC`
(read-only) và named key tạm `REVIEWLENS_ROTATION_SMOKE`; **không rotate hoặc sửa
`REVIEWLENS_RUNTIME`** đang được app sử dụng.

Test thực hiện theo thứ tự:

1. xác minh runtime key hiện tại vẫn đăng nhập đúng `ANALYST_ROLE`;
2. preflight từ chối chạy nếu canary key cùng tên đã tồn tại;
3. tạo hai RSA key tạm trong Windows temp, đăng ký old canary key;
4. xác minh old canary key đăng nhập đúng role;
5. rotate sang new canary key với grace `0`;
6. chứng minh old canary key bị từ chối và new canary key đăng nhập được;
7. xóa active canary key trong `finally`, xóa file tạm và suspend warehouse;
8. xác minh runtime key ban đầu vẫn đăng nhập được sau cleanup.

Không gửi thêm credential cho Codex. Khi owner xác nhận đây là maintenance window,
chạy đúng lệnh sau tại root repository:

```powershell
$env:REVIEWLENS_RUN_LIVE_SNOWFLAKE_ROTATION='1'
$env:REVIEWLENS_SNOWFLAKE_ROTATION_CONFIRM='ROTATE_REVIEWLENS_ANALYTICS_SVC_REVIEWLENS_ROTATION_SMOKE'
.venv\Scripts\pytest.exe tests\live\test_snowflake_rotation_live.py -q -rs -p no:cacheprovider
Remove-Item Env:REVIEWLENS_RUN_LIVE_SNOWFLAKE_ROTATION
Remove-Item Env:REVIEWLENS_SNOWFLAKE_ROTATION_CONFIRM
```

Expected: `1 passed`. Evidence không được chứa public/private key body, path tạm hoặc
giá trị credential. Nếu cleanup báo lỗi, dừng retry và kiểm tra metadata trước:

```sql
SHOW USER KEY PAIRS FOR USER REVIEWLENS_ANALYTICS_SVC;
```

Chỉ khi exact active key `REVIEWLENS_ROTATION_SMOKE` còn tồn tại mới chạy:

```sql
ALTER USER IF EXISTS REVIEWLENS_ANALYTICS_SVC
  REMOVE KEY PAIR REVIEWLENS_ROTATION_SMOKE;
```

Không xóa `REVIEWLENS_RUNTIME`. Rotated-out tombstone có hậu tố
`_ROTATED_<epoch_ms>` phải ở trạng thái disable/expire nếu còn hiển thị; với grace `0`,
Snowflake có thể loại nó ngay trước lần `SHOW` kế tiếp.

### 12.3 Snowflake emergency revoke

```sql
ALTER USER REVIEWLENS_INGEST_SVC SET DISABLED = TRUE;
ALTER USER REVIEWLENS_INGEST_SVC REMOVE KEY PAIR REVIEWLENS_RUNTIME;
REVOKE ROLE INGEST_ROLE FROM USER REVIEWLENS_INGEST_SVC;
```

`REMOVE KEY PAIR` không thể undo; chỉ dùng khi key bị lộ hoặc service bị retire.

### 12.4 R2 rotation

1. Tạo token thay thế cùng bucket và minimum permission.
2. Cập nhật đúng consumer trong `.env`.
3. Chạy synthetic smoke.
4. Chỉ revoke token cũ sau khi smoke pass.

### 12.5 OpenRouter/Chroma/app rotation

- OpenRouter: tạo key mới → update/test → kiểm tra usage → xóa key cũ.
- Chroma/app: tạo token mới độc lập → restart → authenticated/anonymous tests →
  xác nhận token cũ bị từ chối.

## 13. Completion gate của `IMP-M1-008`

`IMP-M1-008` chỉ chuyển từ `PARTIAL` sang `DONE` khi có evidence:

- 8 Snowflake named keys `ACTIVE`, role restriction đúng và user đã enable;
- 8 service connections dùng đúng role, warehouse và secondary roles off;
- forbidden cross-layer operations vẫn bị từ chối;
- rotation smoke chứng minh new key pass và old key fails;
- R2 ingestion/stage dùng hai token riêng, bucket-scoped;
- OpenRouter/Chroma/app không lộ token trong log/test output.
