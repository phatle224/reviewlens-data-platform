# M0 Source Profile — Yelp Open Dataset

| Thuộc tính | Giá trị |
|---|---|
| Trạng thái | `DONE` cho M0 inventory — archive fingerprint, exact inner files, row counts và sample schema đã xác nhận |
| Current local artifact | `Yelp-JSON/` extracted directory; original ZIP không còn hiện diện tại thời điểm kết thúc profile |
| Observed source ZIP size | `4,345,335,132` bytes |
| Observed source ZIP SHA-256 | `47DD6E4D279AC9D8734DDC30BFB3D78E571B9DF4BB95923D7ACF9A6EF3D8A4AB` |
| Local last-write UTC | `2026-08-04 05:19:41Z` |
| Profile date | `2026-08-04` |
| Bundled Terms | `YELP DATASET TERMS OF USE`, last updated 2023-07-07, pages 7–10 của documentation PDF |

## 1. Outer archive inventory

| Entry | Uncompressed bytes | Compressed bytes | Xử lý |
|---|---:|---:|---|
| `Yelp JSON/Yelp Dataset Documentation & ToS copy.pdf` | 124,660 | 114,483 | Review Terms trước real-data external transfer |
| `Yelp JSON/yelp_dataset.tar` | 4,343,892,965 | 4,345,217,694 | Source payload chính; extract streaming ở M1/M2 |
| `__MACOSX/*` | 2,326 | 1,661 | Ignore bằng path rule |

Archive gốc không được commit vào Git, upload public hoặc sửa tại chỗ. `source_release_id` tạm thời được tạo từ SHA-256 của outer archive cho đến khi tài liệu bên trong cung cấp release ID authoritative.

Bundled Terms engineering review cho thấy license chỉ dành cho academic use, hạn chế public display/distribution và third-party sharing, yêu cầu review/approval trước public presentation/publication liên quan Data/Yelp brand, có term 12 tháng từ ngày access và yêu cầu xóa dữ liệu khi termination. Đây không phải tư vấn pháp lý; implementation áp restrictive default trong [security/privacy baseline](./M0_SECURITY_PRIVACY.md).

## 2. Extracted JSON inventory

| File | Bytes | Physical JSONL rows | Top-level fields từ deterministic opening sample |
|---|---:|---:|---|
| `yelp_academic_dataset_business.json` | 118,863,795 | 150,346 | `business_id`, name/address/location, stars, review_count, is_open, attributes, categories, hours |
| `yelp_academic_dataset_checkin.json` | 286,958,945 | 131,930 | `business_id`, `date` |
| `yelp_academic_dataset_review.json` | 5,341,868,833 | 6,990,280 | `review_id`, `user_id`, `business_id`, stars, useful/funny/cool, text, date |
| `yelp_academic_dataset_tip.json` | 180,604,475 | 908,915 | `user_id`, `business_id`, text, date, compliment_count |
| `yelp_academic_dataset_user.json` | 3,363,329,011 | 1,987,897 | `user_id`, name, review_count, yelping_since, friends, useful/funny/cool, fans, elite, average_stars, compliment fields |

Row counts được đo bằng nonblank JSONL lines trên file giải nén. Full JSON/schema validation vẫn thuộc M2; M0 chỉ khóa inventory và contract baseline.

## 3. Dataset contract baseline

Trang chính thức hiện mô tả JSON download gồm 5 JSON files và khoảng 6,990,280 reviews, 150,346 businesses. Con số chỉ là planning baseline; row count thật phải lấy từ extracted archive và khóa trong manifest. Nguồn: [Yelp Open Dataset](https://business.yelp.com/data/resources/open-dataset/).

| Logical dataset | Physical source dự kiến | Required | Business key | Quan hệ chính | Quyết định |
|---|---|---|---|---|---|
| `business` | `yelp_academic_dataset_business.json` | Yes | `business_id` | Parent của review/checkin/tip | Core MVP |
| `review` | `yelp_academic_dataset_review.json` | Yes | `review_id` | `business_id`, `user_id` | Core MVP |
| `user` | `yelp_academic_dataset_user.json` | Yes | `user_id` | Referenced by review/tip | Ingest; minimize serving fields |
| `checkin` | `yelp_academic_dataset_checkin.json` | Yes | `business_id` | Business | Core analytics |
| `tip` | `yelp_academic_dataset_tip.json` | Yes | Composite hash; source không bảo đảm ID riêng | `business_id`, `user_id` | Core analytics |
| `attributes` | Nested `business.attributes` | Derived | `business_id + attribute_name` | Business | Không yêu cầu file riêng |
| `photo` | Gói Yelp photos riêng | Optional/P1 | `photo_id` | Business | Không chặn MVP JSON |

Nếu tên/shape thực tế khác bảng trên, contract test phải fail `SOURCE_CONTRACT_MISMATCH`; không tự động đoán và tiếp tục.

## 4. Source semantics

- Baseline: `FULL_SNAPSHOT` theo archive release, không phải CDC/daily increment.
- Complete marker: outer ZIP tồn tại, hash ổn định, inner TAR mở được và đủ 5 required datasets.
- Same filename + different checksum: source release mới hoặc `SOURCE_RELEASE_CONFLICT`, không overwrite.
- Same checksum: `SKIPPED_DUPLICATE` nhưng release-object lineage vẫn được ghi.
- Absence chỉ được diễn giải là deletion/tombstone khi manifest được xác nhận là complete full snapshot.
- Source timestamps không có offset được giữ `TIMESTAMP_NTZ` kèm `timezone_assumption='SOURCE_LOCAL_UNKNOWN'`; không tự gắn UTC.

## 5. Profile cần hoàn tất ở M1/M2

- [x] Extract nested TAR; toàn bộ extracted directory được `.gitignore`.
- [x] Xác nhận exact filename và byte size từng JSON; outer ZIP SHA-256 là release fingerprint M0.
- [x] Đếm physical nonblank lines.
- [ ] Tính checksum từng inner JSON trong manifest generator M1/M2.
- [ ] Full-parse để đếm malformed lines thay vì chỉ line count.
- [ ] Sample deterministic đầu/giữa/cuối file, không chỉ `head`.
- [ ] Profile null/type/nested shape/cardinality và FK coverage.
- [ ] Xác nhận `attributes` nested trong `business`.
- [ ] Đọc bản Terms đi kèm và ghi explicit allowed/restricted uses.
- [ ] Tạo machine-readable manifest và source contract v1.
