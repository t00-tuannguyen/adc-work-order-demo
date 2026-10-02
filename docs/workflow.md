# Quy trình làm việc

## Luồng tài liệu

```
Brief / PRD ──► specs/ ──► adrs/ ──► tasks/ADC-xxx (đặc tả) ──► planning/backlog (T-xxx) ──► sprint ──► src/
```

| Bước | Ai | Output |
|---|---|---|
| Cập nhật tầm nhìn, FR, luật nghiệp vụ | Trưởng nhóm | `specs/*.md` |
| Quyết định kỹ thuật | Tech lead | `adrs/NNNN-*.md` |
| Viết đặc tả tính năng (Động lực → Thiết kế → Kế hoạch) | Người phụ trách tính năng | `tasks/ADC-NNN-*.md` |
| Chia việc, ước lượng giờ | Cả nhóm | `planning/backlog.md` |
| Lập sprint | Trưởng nhóm | `planning/sprints/sprint-NN.md` |
| Code + test theo TC của đặc tả | Dev / AI agent | PR |
| Review đối chiếu tiêu chí thành công | Reviewer | PR approved |

## Đồng bộ với file Excel quản lý dự án

Template Excel vẫn là nơi mentor theo dõi. Quy ước:

| Sheet Excel | File trong repo | Nguồn chính |
|---|---|---|
| Đặc tả tính năng | `tasks/ADC-*.md` | **Repo** (chép link sang Excel) |
| Danh sách User Story | `specs/features.md` §3 | Repo |
| Backlog | `planning/backlog.md` | Repo; cập nhật trạng thái sang Excel hằng ngày |
| Lộ trình | `docs/roadmap.md` | Excel |
| Theo dõi lỗi | GitHub Issues (`BUG-xxx`), tóm tắt ở `docs/bug-tracking.md` | GitHub |
| Đường link / Tài liệu | `docs/links.md` | Excel |
| Thành viên | `docs/team.md` | Excel |

## Nhịp hằng ngày (theo template)

1. Sáng: xem việc hôm nay trong sprint.
2. Trong ngày: cập nhật trạng thái `T-xxx` khi đổi.
3. Chiều: standup dựa trên sprint file.
4. Tối: Trưởng nhóm tổng hợp, đồng bộ Excel.

## Giao việc cho AI agent

```
Đọc AGENTS.md.
Làm T-033 (tasks/ADC-004-incident-rescheduling.md): tái lập lịch theo ưu tiên + kiểm tra line thay thế.
Dùng hàm deterministic, không để LLM quyết định giờ hay thứ tự.
Viết test theo mục "Kế hoạch kiểm thử" với seed Line A dừng 09:00–12:00.
```

```
Dùng tasks/_template.md, viết đặc tả ADC-009 cho <tính năng mới>.
Thêm các mã việc T-054+ vào planning/backlog.md.
```
