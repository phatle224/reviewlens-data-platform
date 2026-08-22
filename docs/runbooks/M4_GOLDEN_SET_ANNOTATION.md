# M4 — Hướng dẫn gán nhãn golden set (làm từng bước)

## Mục tiêu của việc này

Bạn sẽ đọc **200 review Olist private** và tạo nhãn chuẩn để về sau so sánh
kết quả AI. Đây là cách biết AI có thực sự tốt hay không, thay vì chỉ tin vào
câu trả lời của model.

Bạn **không cần** Snowflake, R2, OpenRouter hay API key cho bước này. Mọi thứ
chạy local. Thời gian hợp lý là chia nhỏ, ví dụ 20–30 review mỗi lần; không cần
làm 200 review trong một buổi.

> Quan trọng: review text là dữ liệu private. Không commit, không upload lên
> GitHub/R2/Snowflake/OpenRouter, không copy vào ChatGPT, và không chụp màn hình
> có nội dung review. Thư mục `private_evaluation/` đã bị Git bỏ qua.

## Bạn sẽ làm với 3 file nào?

Tất cả nằm trong thư mục:

```text
private_evaluation\m4_enrichment_v1\
```

| File | Bạn dùng để làm gì? | Có được sửa? |
|---|---|---|
| `annotation_queue.jsonl` | Đọc review text để tự đánh giá ý nghĩa của review. | Không sửa. |
| `labels.machine_assisted.jsonl` | Gợi ý sơ bộ do máy tạo từ điểm sao và tình trạng giao hàng. Có thể sai. | Không sửa. |
| `labels.jsonl` | File nhãn chính thức của bạn. | **Chỉ sửa file này.** |
| `METADATA.json` | Thông tin tổng hợp về pack. | Không sửa. |

Mỗi dòng trong các file là một JSON object tương ứng với **một review** (pack 200+ rows này được khởi tạo bằng `uv run reviewlens-golden-pack generate`). Các
file được ghép với nhau bằng trường `opaque_example_id` — chuỗi 64 ký tự. Đừng
sửa chuỗi này.

## Bước 0 — Mở đúng thư mục và tạo bản sao dự phòng

Mở PowerShell tại root project (prompt phải bắt đầu bằng
`PS D:\project\reviewlens-data-platform>`), rồi chạy lệnh sau **một lần**:

```powershell
Copy-Item private_evaluation\m4_enrichment_v1\labels.jsonl private_evaluation\m4_enrichment_v1\labels.before_manual_review.jsonl
```

Đây là bản sao dự phòng local; cũng không bị Git theo dõi. Nếu bạn đã tạo file
dự phòng rồi thì không cần chạy lại.

Sau đó mở folder bằng VS Code. Cách đơn giản nhất là gõ lệnh này nếu máy đã có
lệnh `code`:

```powershell
code .
```

Nếu PowerShell báo không có `code`, mở VS Code bình thường, chọn **File → Open
Folder**, rồi chọn `D:\project\reviewlens-data-platform`.

Trong VS Code, mở ba file sau ở ba tab:

```text
private_evaluation\m4_enrichment_v1\annotation_queue.jsonl
private_evaluation\m4_enrichment_v1\labels.machine_assisted.jsonl
private_evaluation\m4_enrichment_v1\labels.jsonl
```

## Bước 1 — Hiểu nhãn trước khi sửa

Trong `labels.jsonl`, mỗi dòng ban đầu trông gần giống như sau (ID ví dụ đã
được rút gọn):

```json
{"annotation_status":"pending","aspect_sentiments":null,"category_bucket":"category_...","delivery_outcome":"on_time","length_bucket":"medium","opaque_example_id":"...","review_score":4,"sentiment":null,"topics":null}
```

Bạn chỉ được thay đổi bốn trường sau:

| Trường | Bạn điền gì? |
|---|---|
| `annotation_status` | Đổi từ `pending` thành `approved` khi đã tự đọc và quyết định nhãn. |
| `sentiment` | Một trong: `positive`, `neutral`, `negative`, `mixed`. |
| `aspect_sentiments` | Danh sách các khía cạnh được review nhắc đến; không nhắc đến thì dùng `[]`. |
| `topics` | Danh sách chủ đề liên quan; không có chủ đề rõ ràng thì dùng `[]`. |

Không sửa hoặc xóa các trường khác: `opaque_example_id`, `review_score`,
`length_bucket`, `category_bucket`, `delivery_outcome`.

Bạn không cần thêm `summary`, `highlights`, review text, tên người gán nhãn hay
ghi chú tự do vào file. Những nội dung đó không thuộc golden-label format.

### Giá trị hợp lệ

**Sentiment tổng thể**

| Giá trị | Khi nào dùng? |
|---|---|
| `positive` | Review chủ yếu khen/hài lòng. |
| `neutral` | Chủ yếu mô tả, rất ngắn, hoặc không thể hiện khen/chê rõ ràng. |
| `negative` | Review chủ yếu phàn nàn/không hài lòng. |
| `mixed` | Có cả điểm khen và chê có ý nghĩa. |

**Aspect** — chỉ thêm aspect khi review thật sự đề cập đến nó:

```text
product_quality, delivery, packaging, customer_service,
price_value, product_description, payment, other
```

**Topic** — chỉ thêm topic khi có bằng chứng trong review:

```text
delivery_speed, delivery_condition, product_quality, product_match,
packaging, customer_service, price_value, payment_experience, other
```

Ví dụ cách phân biệt:

- Review nói “giao chậm” → aspect `delivery`, topic `delivery_speed`.
- Review nói hàng hỏng/khác mô tả → aspect `product_quality` hoặc
  `product_description`, topic `product_quality` hoặc `product_match`.
- Review chỉ nói “rất tốt” → `sentiment: positive`, `aspect_sentiments: []`,
  `topics: []`. Đừng đoán sản phẩm hay giao hàng tốt chỉ từ điểm sao.
- `delivery_outcome: delayed` là metadata đơn hàng, **không tự chứng minh**
  review đang phàn nàn về giao hàng.

Mỗi phần tử trong `aspect_sentiments` phải có đúng ba field:

```json
{"aspect":"delivery","sentiment":"negative","confidence":1.0}
```

`confidence` là số từ `0` đến `1`. Dùng `1.0` khi bạn chắc chắn; có thể dùng
`0.7` nếu review mơ hồ nhưng bạn vẫn phải ra quyết định. Không thêm cùng một
aspect hai lần trong một review.

## Bước 2 — Cách review một dòng (lặp lại 200 lần)

Làm theo đúng thứ tự này cho **mỗi** review:

1. Trong `labels.jsonl`, đặt con trỏ ở một dòng còn
   `"annotation_status":"pending"`.
2. Copy giá trị đầy đủ của `opaque_example_id` ở dòng đó.
3. Mở tab `annotation_queue.jsonl`, nhấn `Ctrl+F`, dán ID vừa copy, rồi đọc
   trường `review_text` trên dòng tìm được. Đây là nội dung duy nhất bạn dùng
   để quyết định nhãn.
4. (Tùy chọn) Mở tab `labels.machine_assisted.jsonl`, tìm cùng ID để xem gợi ý.
   Gợi ý chỉ dựa trên điểm sao/giao hàng nên có thể sai; hãy ưu tiên review text
   của bạn.
5. Quay về đúng dòng trong `labels.jsonl`; thay bốn trường được phép sửa theo
   đánh giá của bạn, lưu file bằng `Ctrl+S`.
6. Chuyển sang dòng `pending` kế tiếp.

### Một ví dụ hoàn chỉnh

Nếu sau khi đọc review bạn kết luận: khách hàng khen chất lượng sản phẩm và
không nói gì về giao hàng, dòng nhãn cuối cùng có cấu trúc như sau. Hãy **giữ
nguyên** các giá trị ID/bucket/score của dòng thực tế của bạn.

```json
{"annotation_status":"approved","aspect_sentiments":[{"aspect":"product_quality","sentiment":"positive","confidence":1.0}],"category_bucket":"category_...","delivery_outcome":"on_time","length_bucket":"medium","opaque_example_id":"...","review_score":5,"sentiment":"positive","topics":["product_quality"]}
```

Ví dụ một review chỉ nói chung chung là hài lòng:

```json
{"annotation_status":"approved","aspect_sentiments":[],"category_bucket":"category_...","delivery_outcome":"unknown","length_bucket":"short","opaque_example_id":"...","review_score":4,"sentiment":"positive","topics":[]}
```

## Bước 3 — Dùng gợi ý máy đúng cách

`labels.machine_assisted.jsonl` **không phải** file để nộp và không tự động
được tính là “human-reviewed”. Nó chỉ áp dụng quy tắc đơn giản:

- 1–2 sao → gợi ý `negative`; 3 sao → `neutral`; 4–5 sao → `positive`.
- Nếu metadata nói giao trễ → gợi ý aspect `delivery`/`negative`.
- Nếu giao đúng hạn và 4–5 sao → có thể gợi ý `delivery`/`positive`.

Vì vậy, bạn có thể dùng nó để tiết kiệm thời gian nhập liệu, nhưng với mỗi dòng
vẫn phải đọc `review_text`, sửa nếu cần, rồi tự đặt `approved` trong
`labels.jsonl`. Không rename suggestion file thành `labels.jsonl`, không copy
hàng loạt, và không đổi hàng loạt `machine_assisted` thành `approved`.

## Bước 4 — Kiểm tra tiến độ khi đang làm

Trong PowerShell tại root project, chạy lệnh này bất kỳ lúc nào. Nó chỉ đếm
trạng thái, không in review text và không sửa file:

```powershell
Get-Content private_evaluation\m4_enrichment_v1\labels.jsonl | ForEach-Object { ($_ | ConvertFrom-Json).annotation_status } | Group-Object | Select-Object Name, Count
```

Khi làm xong, kết quả phải chỉ có một dòng `approved` với `Count` bằng `200`.
Nếu vẫn còn `pending`, hãy tiếp tục review trước khi sang bước sau.

## Bước 5 — Validate sau khi đủ 200 nhãn

Chỉ chạy lệnh này khi cả 200 dòng đã là `approved`:

```powershell
uv run reviewlens-golden-pack validate --labels-path private_evaluation\m4_enrichment_v1\labels.jsonl --split-seed m4-eval-holdout-v1
```

Kết quả thành công sẽ là JSON aggregate có các ý chính sau:

```text
"label_count": 200
"holdout_count": 40
"status": "ready_for_private_predictions"
```

Lệnh này **không gọi AI**, không dùng OpenRouter budget và không đưa dữ liệu lên
mạng. Nó chỉ kiểm tra format rồi tạo split deterministic 80% train / ít nhất
20% blind holdout. Đừng commit output/hash hoặc copy nội dung labels/queue lên
GitHub.

Sau khi lệnh pass, nhắn mình: **“Golden set đã validate pass”**. Khi đó mình sẽ
tiếp tục bước đánh giá private tiếp theo; bạn chưa cần tự chạy bất kỳ lệnh AI
nào.

## Bước 6 — Bước kế tiếp do Codex thực hiện

Golden set hiện đã sẵn sàng, nhưng **chưa có prediction AI** nên chưa thể tính
điểm F1. Ở phiên phát triển kế tiếp, Codex sẽ tạo prediction private cho đúng 40
holdout items sau khi bạn chấp thuận một bounded OpenRouter pilot và DLP gate.
Bạn không cần tự tạo file prediction hay tự chạy lệnh AI.

Khi prediction private đã có, evaluator local dùng lệnh sau và chỉ ghi report
aggregate; cả prediction và report phải ở trong `private_evaluation/`:

```powershell
uv run reviewlens-golden-pack evaluate --labels-path private_evaluation\m4_enrichment_v1\labels.jsonl --split-seed m4-eval-holdout-v1 --predictions-path private_evaluation\m4_enrichment_v1\holdout_predictions.jsonl --enrichment-version <64-ky-tu-sha256> --report-path private_evaluation\m4_enrichment_v1\evaluation_report.json
```

Không chạy lệnh trên khi chưa có prediction file; nó sẽ fail-closed. Lệnh này
không gọi OpenRouter: nó chỉ từ chối prediction thiếu/thừa ID, ID thuộc tập train,
JSON/schema không hợp lệ hoặc output không an toàn, rồi tính metric cho đúng blind
holdout.

## Nếu gặp lỗi thì xử lý thế nào?

| Thông báo / tình huống | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `AI_EVALUATION_ANNOTATION_LABELS_INCOMPLETE` | Còn `pending`, có `machine_assisted`, hoặc ít hơn 200 dòng approved. | Chạy lệnh đếm ở Bước 4; hoàn tất/correct nhãn còn thiếu trong `labels.jsonl`. |
| `AI_EVALUATION_ANNOTATION_LABEL_INVALID` | JSON sai dấu phẩy/ngoặc, sentiment/topic/aspect không nằm trong danh sách, hoặc aspect bị trùng. | Undo dòng vừa sửa (`Ctrl+Z`) rồi sửa theo ví dụ ở Bước 2. |
| Không tìm thấy ID trong queue | Đã copy thiếu ID hoặc đang tìm trong file sai. | Copy lại toàn bộ `opaque_example_id` từ `labels.jsonl`, tìm trong `annotation_queue.jsonl`. |
| VS Code hiển thị file trên một dòng dài | JSONL vốn là một JSON cho mỗi dòng. | Dùng `Ctrl+F` theo ID; không cần format toàn bộ file. |
| Lỡ sửa/xóa nhiều dòng | Có bản `labels.before_manual_review.jsonl`. | Dừng lại và nhắn mình trước khi khôi phục để không mất phần bạn đã làm đúng. |

## Điều kiện để đóng `IMP-M4-012`

M4-012 chỉ được chuyển `DONE` khi có đủ 200+ nhãn do người review, validate pass,
prediction private cho toàn bộ blind holdout và report aggregate đạt ngưỡng:

- sentiment macro F1 ≥ 0.85;
- aspect macro F1 ≥ 0.75;
- topic micro F1 ≥ 0.75;
- schema pass rate = 100%.

Nếu metric không đạt, candidate AI bị chặn; không sửa nhãn sau khi đã xem
prediction để làm đẹp điểm số.

## Bảo mật và cleanup

Giữ `private_evaluation/` ở local. Không dùng lệnh xóa hàng loạt để “làm lại”
pack; nếu muốn sample mới, dừng và hỏi mình để tạo output directory/seed mới mà
vẫn giữ evidence private cũ. Quy trình pause/resume/model-change/purge nằm ở
[M4 AI enrichment operations](./M4_AI_ENRICHMENT_OPERATIONS.md).
