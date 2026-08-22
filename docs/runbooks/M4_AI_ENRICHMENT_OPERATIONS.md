# M4 — AI enrichment recovery operations

Runbook này dành cho local portfolio runtime. Nó điều khiển trạng thái vận hành
của enrichment, không phải là cách để xem, export hay xoá dữ liệu review. Review
text, DLP-approved text, prompt, provider response, embedding, natural ID,
credential và row-level result luôn private; không đưa vào terminal capture,
issue, screenshot hay Git.

Hiện tại M4 mới có contract offline. Không có pilot OpenRouter private đang chạy
và không có automation purge được mở. Vì vậy TC-M4-020 là tabletop drill có kiểm
soát: dùng fixture synthetic và không gọi OpenRouter, Snowflake, R2 hoặc Docker
runtime.

## 1. Guardrails và bằng chứng được phép lưu

- Chỉ owner local mới được pause/resume. Giữ `max_active_runs=1` và pool một
  slot; không tạo worker song song để “chạy cho nhanh”.
- Không có retry thủ công cho `SUCCEEDED` hoặc `QUARANTINED`. Chỉ trạng thái
  `RETRYABLE` được resume, với cùng work ID và tối đa ba attempts.
- Reservation trong budget ledger vẫn được tính sau interruption. Trước khi
  resume phải đối chiếu committed/reserved USD với hard cap 5 USD và warning
  daily 0.50 USD; không xóa ledger để vượt budget.
- Bằng chứng an toàn gồm timestamp, trạng thái, attempt/repair count, aggregate
  token/USD/latency/error-code/coverage và fingerprint. Không lưu opaque ID vào
  public evidence dù nó là hash.
- Khi có lỗi, dashboard/base facts vẫn hoạt động độc lập; missing AI enrichment
  không được làm mất `FACT_REVIEW_BASE`.

## 2. Pause và triage

Khi thấy cost bất thường, DLP/schema error tăng, provider không ổn định hoặc
operator không chắc chắn về trạng thái, pause trước rồi mới điều tra. Nếu M4 được
gắn vào DAG local `olist_pipeline`, dùng Airflow CLI trong container:

```powershell
docker compose exec airflow airflow dags pause olist_pipeline
docker compose exec airflow airflow dags list-runs olist_pipeline
```

Không cancel một request provider đang in-flight và không clear task thành công.
Ghi lại chỉ run/task state, stable error code, aggregate counters và dashboard
fingerprint. Không copy log chứa prompt/review hay provider body. Nếu có khả năng
credential lộ, giữ DAG paused và theo [credential rotation runbook](./M1_CREDENTIAL_ROTATION.md)
trước khi resume.

| Tín hiệu | Hành động bắt buộc |
|---|---|
| `AI_ENRICHMENT_BUDGET_EXHAUSTED` hoặc budget mismatch | Giữ paused; không gửi request mới; đối chiếu reservation/committed aggregate ledger. |
| `AI_ENRICHMENT_SCHEMA_INVALID` hoặc quarantine tăng | Giữ output quarantine; không sửa tay result; kiểm tra schema/taxonomy/prompt version bằng synthetic suite. |
| `OPENROUTER_TRANSIENT` | Giữ cùng work ID ở `RETRYABLE`; chỉ resume sau khi provider ổn định. |
| DLP/minimization fail | Không retry bằng raw text; giữ quarantine và sửa policy/code trước. |
| Không rõ state/version | Không resume; so khớp ledger, coverage và dashboard fingerprint trước. |

## 3. Resume an toàn

Chỉ resume sau khi nguyên nhân có một quyết định rõ ràng và toàn bộ điều kiện sau
đạt:

1. DAG vẫn paused trong lúc kiểm tra; không có operator thứ hai chạy cùng batch.
2. `enrichment_version`, source/input hashes và `work_id` giữ nguyên. Selector
   chỉ được gửi `NEW` hoặc `CHANGED`; `REUSED` không được dispatch lại.
3. Budget ledger hợp lệ, còn cap, và observability snapshot không báo
   budget/version/coverage mismatch.
4. Không có terminal `QUARANTINED` bị clear. Một lỗi transient resume đúng
   executor sẽ tăng attempt count và quarantine tại bounded max, thay vì loop vô
   hạn.

Sau đó mới unpause và trigger đúng một run local, nếu M4 đã được wiring vào DAG:

```powershell
docker compose exec airflow airflow dags unpause olist_pipeline
docker compose exec airflow airflow dags trigger olist_pipeline
```

Sau run, pause lại nếu đây là drill. Chỉ giữ metadata aggregate như mục 1. Với
pilot thật trong tương lai, lệnh trigger cần một owner approval riêng cho chi phí
và không thuộc runbook/tabletop này.

## 4. Model, prompt, schema hoặc taxonomy change

Không sửa model slug/prompt/schema/taxonomy “in place”. Bất kỳ thay đổi nào đều
tạo `enrichment_version` mới và không thay kết quả version cũ.

1. Pause new dispatch theo mục 2; giữ prior committed results và base facts.
2. Snapshot catalog public, xác minh policy data-collection deny/no fallback,
   context/structured-output và prompt/completion price cho model mới.
3. Cập nhật version key qua source code; chạy schema, DLP, injection, validation,
   retry, budget và observability tests bằng synthetic fixture.
4. Tạo/re-run private human-reviewed golden evaluation với holdout blind tối thiểu
   20%; M0 gate yêu cầu ít nhất 200 labels trước khi cho phép pilot thật.
5. Quality gate phải PASS cho đúng `enrichment_version`; candidate mismatch hoặc
   metric dưới ngưỡng không được publish và không được gọi release pointer.
6. Chỉ sau owner approval cho bounded cost mới cho selector xử lý `NEW`/`CHANGED`
   của version mới. Version cũ vẫn có thể phục vụ coverage/audit cho đến khi một
   retention decision được ghi rõ.

Xem [ADR-003](../ADR/ADR-003-openrouter-ai-provider.md) và
[ADR-016](../ADR/ADR-016-m4-enrichment-contract-and-dlp-projection.md) để biết
contract bất biến và điều kiện model change.

## 5. Purge và retention

M4 hiện **không** có lệnh purge tự động. Không dùng `Remove-Item -Recurse`,
`docker compose down --volumes`, SQL `DELETE`/`TRUNCATE`, hay R2 overwrite để
“dọn nhanh” enrichment. Những thao tác đó có thể xóa evidence cần cho retry,
coverage, golden evaluation hoặc audit.

Một yêu cầu purge hợp lệ phải là ticket owner riêng, ghi rõ phạm vi private và
retention reason, rồi pass các gate sau trước khi có code migration riêng:

1. Pause dispatch, snapshot aggregate fingerprint/counters và xác nhận warehouse
   suspend sau mọi kiểm tra cần thiết.
2. Chứng minh `FACT_REVIEW_BASE`, raw immutable source và active/rollback release
   không nằm trong phạm vi purge.
3. Chỉ cho phép derived artifact private đã hết retention và không còn được
   referenced bởi committed result map, golden evaluation, active candidate hay
   audit lineage.
4. Tạo kế hoạch delete chính xác, dry-run bằng metadata/hashes, owner confirm và
   test failure/replay trước mutation.
5. Sau mutation, đối chiếu aggregate coverage/audit và lưu evidence aggregate;
   không public danh sách object, review hay identifier.

Nếu mục tiêu chỉ là giải phóng Docker runtime local, dùng `docker compose down`
không kèm `--volumes`; named volume/evidence private vẫn được giữ. Việc xóa volume
chỉ được xem xét sau khi có restore/rebuild drill ở M5/M8.

## 6. TC-M4-020 tabletop drill đã thực hiện offline

| Bước | Synthetic tình huống | Kỳ vọng/pass condition |
|---|---|---|
| Pause | Một invocation lỗi transient được phát hiện trước retry | Dispatch mới dừng; chỉ state/error code aggregate được ghi; base fact không đổi. |
| Resume | Cùng work ID `RETRYABLE` được executor chạy lại | Attempt tăng có giới hạn; thành công commit một validated result hoặc terminally quarantine; không duplicate commit. |
| Model change | Model/prompt version đổi | Version key mới, catalog+price+golden+quality gates bắt buộc; version cũ không bị mutate và candidate không tự publish. |
| Purge request | Owner muốn dọn derived artifact | Không có direct delete; scope phải loại trừ base/raw/release/audit và cần approved migration/drill sau này. |

Thực thi contract/tabletop test offline từ repository root:

```powershell
uv run pytest tests\test_m4_operations.py tests\test_m4_execution.py tests\test_m4_budget.py tests\test_m4_commit.py tests\test_m4_quality.py tests\test_m4_observability.py -q -p no:cacheprovider --basetemp .tmp\pytest-m4-015-focused
uv run reviewlens-policy --root .
python .agents\skills\reviewlens-dev-workflow\scripts\validate_project_status.py --root .
```

## 7. Closeout

Sau bất kỳ drill/pilot nào: pause DAG nếu không còn nhu cầu, xác nhận không có
provider request mới, kiểm tra warehouse đã suspend nếu nó được dùng, và cập nhật
[M4 checklist](../phases/M4/M4_CHECKLIST.md),
[M4 test cases](../phases/M4/M4_TEST_CASES.md) và
[project status](../PROJECT_STATUS.md) bằng evidence thực tế. Không đánh dấu
provider smoke, human golden evaluation hoặc live release wiring là PASS chỉ từ
tabletop drill này.
