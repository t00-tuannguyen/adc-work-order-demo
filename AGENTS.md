# AGENTS.md — Luật chơi cho AI & team

> Mọi AI agent (Claude Code, Copilot, Cursor, Codex…) và thành viên đọc file này **trước khi làm bất cứ việc gì** trong repo.

## 1. Dự án trong 3 câu

ADC Irradiation Work Order là multi-agent orchestrator cho 2 line chiếu xạ: đọc ticket PDF của khách, ước tính thời lượng từ giả định mô phỏng, xếp lịch Line A/B và xử lý sự cố line bằng tái lập lịch theo ưu tiên. **AI xử lý đầu vào lộn xộn, điều phối và giải thích; luật deterministic tính lịch; con người duyệt mọi thay đổi ảnh hưởng khách.** Chi tiết: `specs/product-vision.md`.

## 2. Nguồn sự thật

Thứ tự ưu tiên khi mâu thuẫn:

1. `specs/` — cái gì, cho ai, luật nghiệp vụ, API contract
2. `adrs/` — quyết định kiến trúc đã chốt
3. `tasks/ADC-*.md` — đặc tả chi tiết từng tính năng (Động lực → Thiết kế → Kế hoạch)
4. `src/` — code

Code lệch spec → sửa code, hoặc đề xuất sửa spec. **Không tự ý sửa spec để khớp code.**

## 3. Luật bất biến (không được vi phạm)

- **Không** thêm thư viện/framework ngoài danh sách trong `adrs/0002-tech-stack.md`. Muốn thêm → viết ADR mới.
- **Không** đổi cấu trúc thư mục ngoài `adrs/0003-folder-structure.md`.
- **Không** đổi API public khác `specs/api-contracts.md`. Đổi contract → cập nhật spec trước, code sau.
- Mọi thay đổi code phải kèm test tương ứng.
- Không commit secret,API key, `.env`, dữ liệu thật của người dùng.
- Một PR = một task `T-xxx`. Tên branch: `feature/T-xxx-mo-ta-ngan` (xem mục 5).

## 4. Quy trình làm một task

1. Đọc file đặc tả trong `tasks/` (ví dụ `tasks/ADC-003-line-scheduling-kanban.md`) và mã việc `T-xxx` được giao trong `planning/backlog.md`.
2. Đọc phần liên quan trong `specs/domains.md`, `specs/api-contracts.md`, `specs/user-roles.md` và ADR.
3. Đặc tả thiếu hoặc mâu thuẫn → **dừng và hỏi**, ghi câu hỏi vào mục *Nhật ký* của file task.
4. Trình bày kế hoạch ngắn trước khi sửa code; chỉ sửa trong module của task.
5. Viết test dựa trên mục *Kế hoạch kiểm thử* (TC) của đặc tả.
6. Cập nhật trạng thái `T-xxx` trong file task, `planning/backlog.md` và sprint hiện tại.

## 5. Branch, commit, PR

- Branch: `feature/T-027-earliest-feasible`, `fix/BUG-003-...`, `docs/...`
- Commit (Conventional Commits, gắn mã việc):
  ```
  feat(scheduling): earliest feasible slot search [T-027]
  fix(intake): reject return time before arrival [BUG-004]
  docs(adr): add 0007-...
  ```
- PR: tiêu đề `[T-xxx] Mô tả`; mô tả liệt kê TC đã pass; 1 reviewer; CI xanh.

## 6. Definition of Done

- [ ] Tiêu chí thành công và TC liên quan trong đặc tả đã pass
- [ ] Test mới + test cũ pass; lint pass
- [ ] Không vi phạm mục 3
- [ ] API khớp `specs/api-contracts.md` (hoặc đã cập nhật contract trước)
- [ ] Thao tác mới có ghi `state_history` / `audit_log` khi áp dụng
- [ ] Cập nhật trạng thái task, backlog, sprint

## 7. Khi nào viết ADR mới

Quyết định khó đảo ngược, ảnh hưởng nhiều module, hoặc chọn giữa ≥ 2 phương án hợp lý (ví dụ: chốt stack, đổi thuật toán xếp lịch, thêm SSO Microsoft). Copy `adrs/_template.md`. ADR `Accepted` không sửa nội dung — tạo ADR mới "Supersedes".

## 8. Lệnh thường dùng

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt     # cài đặt
cp .env.example .env                # điền OPENAI_API_KEY, AI_LOG_API_KEY
bash scripts/setup_hooks.sh         # hook ghi log AI (bắt buộc, chạy 1 lần)
make run                            # chạy local → http://localhost:8000/docs
make test                           # pytest
make lint                           # ruff check (make format để format)
# seed-reset: POST /api/demo/reset — làm ở T-025
```
