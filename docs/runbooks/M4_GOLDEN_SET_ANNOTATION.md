# M4 — Private enrichment golden-set annotation

Runbook này tạo 200 mẫu Olist private để **bạn** review và gán nhãn. Queue có
review text nên phải ở `private_evaluation/`, bị `.gitignore`; không upload lên
R2, Snowflake, OpenRouter, GitHub, screenshot hay công cụ annotation public.
Tool không gọi provider và không tiêu OpenRouter budget.

## 1. Tạo private pack

Chạy từ root. `--seed` là một chuỗi do bạn tự chọn, giữ riêng để có thể tái tạo
sample; không dùng tên, email, secret hoặc nội dung review làm seed.

```powershell
uv run reviewlens-golden-pack generate --archive-dir archive --output-dir private_evaluation\m4_enrichment_v1 --seed m4-olist-annotation-v1
```

Lệnh tạo đúng 200 rows với strata đầu vào: review score, length bucket, opaque
category bucket và delivery outcome. `annotation_queue.jsonl` chứa review text
và chỉ dùng cho việc đọc/label local. `labels.jsonl` không chứa review text, là
file duy nhất cần sửa. `METADATA.json` chỉ chứa aggregate hash/count/status.
Tool fail-closed nếu output directory đã có file; không overwrite pack cũ.

## 2. Gán nhãn từng row

Mở đồng thời queue và labels theo `opaque_example_id`. Với mỗi row trong
`labels.jsonl`, điền ba field rồi đổi `annotation_status` từ `pending` thành
`approved`:

- `sentiment`: một trong `positive`, `neutral`, `negative`, `mixed`.
- `aspect_sentiments`: JSON list (có thể rỗng) với mỗi phần tử là
  `{"aspect":"delivery","sentiment":"negative","confidence":1.0}`.
  Aspect được phép: `product_quality`, `delivery`, `packaging`,
  `customer_service`, `price_value`, `product_description`, `payment`, `other`.
- `topics`: JSON list (có thể rỗng) dùng đúng taxonomy M4 đã frozen.

Không sửa opaque ID, score, bucket hoặc delivery outcome. Không thêm note tự do,
review text, natural ID hay tên annotator vào labels. Nếu chưa chắc, giữ row ở
`pending`; tuyệt đối không đoán để đạt số lượng.

### Machine-assisted suggestions

Khi owner cho phép, tool có thể tạo suggestion offline dựa **chỉ** vào review
score và delivery outcome; nó không gửi/hiểu review text bằng model. Output là
`labels.machine_assisted.jsonl` với status `machine_assisted`, không thể qua
validator human-golden và không được dùng làm evidence/gate.

```powershell
uv run reviewlens-golden-pack suggest --annotation-queue-path private_evaluation\m4_enrichment_v1\annotation_queue.jsonl --labels-path private_evaluation\m4_enrichment_v1\labels.jsonl --output-path private_evaluation\m4_enrichment_v1\labels.machine_assisted.jsonl
```

Copy/review từng suggestion vào `labels.jsonl`; chỉ người review mới đổi status
thành `approved`. Không đổi hàng loạt `machine_assisted` thành `approved`.

## 3. Validate sau human review

Chỉ khi cả 200 rows là `approved`, chạy:

```powershell
uv run reviewlens-golden-pack validate --labels-path private_evaluation\m4_enrichment_v1\labels.jsonl --split-seed m4-eval-holdout-v1
```

Output chỉ có aggregate count/hash/holdout count; không copy output này cùng với
labels hoặc queue lên public evidence. Validator tạo deterministic split với
blind holdout tối thiểu 20% và lúc này thêm aspect vào stratum. Nó chưa gọi model
và chưa đánh giá metric: prediction private đúng version là gate riêng tiếp theo.

## 4. Điều kiện đóng M4-012

`IMP-M4-012` và TC-M4-017 chỉ được chuyển sang DONE/PASS sau khi:

1. 200+ rows có human label hợp lệ và split validate pass.
2. Prediction private tồn tại cho đúng mọi holdout ID, dùng đúng
   `enrichment_version`.
3. Aggregate evaluator chạy thành công; sentiment macro F1 ≥0.85, aspect macro
   F1 ≥0.75, topic micro F1 ≥0.75 và schema pass rate =100%.
4. Chỉ aggregate report/hash được ghi vào checklist. Không đưa labels, queue,
   predicted summary/highlights hay row-level result vào Git.

Nếu một metric fail, giữ candidate blocked và cải thiện prompt/schema/taxonomy
qua version mới; không cherry-pick holdout hoặc sửa nhãn sau khi xem prediction.

## 5. Cleanup và bảo mật

Giữ pack private cho đến khi policy retention cho phép thay đổi có kiểm soát.
Không dùng lệnh recursive delete để reset annotation. Muốn tạo sample mới, dùng
một output directory và seed mới; pack cũ giữ làm evidence private. Quy trình
pause/resume/model-change/purge được mô tả tại
[M4 AI enrichment operations](./M4_AI_ENRICHMENT_OPERATIONS.md).
