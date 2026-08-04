# Phase delivery convention

Trạng thái tổng thể và phase hiện tại được tóm tắt tại [`docs/PROJECT_STATUS.md`](../PROJECT_STATUS.md). Đây là file đầu tiên cần cập nhật khi kết thúc mỗi coding session; checklist và test cases bên dưới vẫn là nguồn evidence chi tiết.

Mỗi phase `M0`…`M8` phải có tối thiểu hai artifact:

- `Mx_CHECKLIST.md`: trạng thái từng work item, evidence, blocker và exit gate.
- `Mx_TEST_CASES.md`: test ID, loại test, precondition, steps, expected result, status và evidence.

Quy ước trạng thái:

| Status | Ý nghĩa |
|---|---|
| `DONE` | Artifact và evidence đã tồn tại, verification đã pass |
| `PARTIAL` | Có tiến triển hữu ích nhưng còn verification hoặc input chưa hoàn tất |
| `BLOCKED` | Không thể đóng nếu thiếu user/external input cụ thể |
| `DEFERRED` | Được đưa ra khỏi phase bằng quyết định có lý do và milestone đích |
| `NOT_STARTED` | Chưa bắt đầu |

Một phase chỉ được đánh dấu `COMPLETE` khi mọi P0 item là `DONE` hoặc có `DEFERRED` decision hợp lệ, tất cả mandatory test pass và exit gate có evidence. Với project solo, `Owner` là responsibility hat; self-review phải dùng checklist và bằng chứng tái chạy được. External approval chỉ bắt buộc khi ứng dụng public, có user thật hoặc policy/license yêu cầu.

Test strategy ưu tiên hiện tại:

1. Contract và policy-as-code trước integration test.
2. Deterministic fixture, property-based/replay và failure-injection cho data pipeline.
3. dbt unit/data tests cho transformation và metric.
4. Golden-set + regression evaluation cho AI/RAG/Text-to-SQL.
5. Negative security tests chạy bằng đúng service identity.
6. Cost/latency được kiểm thử như release gate, không chỉ quan sát sau deploy.

## Quy trình kết thúc coding session

1. Cập nhật work item đã chạm và evidence trong `Mx_CHECKLIST.md`.
2. Ghi test command/result thực tế trong `Mx_TEST_CASES.md`; test chưa chạy không được ghi `PASS`.
3. Cập nhật `docs/PROJECT_STATUS.md`: phase, kết quả gần nhất, test, blocker/risk, cost, input cần từ owner và 3–5 việc tiếp theo.
4. Chỉ sửa implementation plan khi task/sequencing thay đổi; chỉ sửa PRD khi requirement/scope thay đổi; tạo ADR cho quyết định kiến trúc quan trọng.
5. Chạy `python .agents/skills/reviewlens-dev-workflow/scripts/validate_project_status.py --root .` trước khi kết thúc phiên.
