# Lộ trình — các mốc chính

Nguồn: sheet *Lộ trình* của template.

> Đã thống nhất (25/09/2026): dự án chạy **6 tuần**, mỗi tuần 1 sprint (`planning/sprints/sprint-01.md` … `sprint-06.md`). Brief/PRD gốc viết cho 4 tuần; phạm vi tính năng giữ nguyên, được giãn ra để có tuần xử lý phản hồi Demo 1 và tuần triển khai/đánh giá.

| Mã | Mốc | Mô tả | Tuần | Sprint | Từ | Đến | Chịu trách nhiệm | Trạng thái | Giao nộp |
|---|---|---|---|---|---|---|---|---|---|
| M1 | Hoàn thành Project Charter | Mục tiêu, phạm vi, đối tác, chỉ số đã chốt | W1 | 1 | | | Trưởng nhóm | Chưa bắt đầu | Charter, Quy chế làm việc (`AGENTS.md`) |
| M2 | Gặp đối tác lần đầu | Giới thiệu, lắng nghe nhu cầu, xác nhận hướng đi; xin PDF mẫu và chốt giả định | W1 | 1 | | | Trưởng nhóm + Mentor | Chưa bắt đầu | Biên bản họp, Báo cáo phản hồi |
| M3 | Hoàn thành thiết kế giải pháp | Kiến trúc, mô hình dữ liệu, phương án kỹ thuật; lõi deterministic chạy được | W2 | 2 | | | Cả nhóm | Chưa bắt đầu | Sơ đồ kiến trúc (`ARCHITECTURE.md`), ADR, Tài liệu giải pháp |
| M4 | Demo 1 — Bản thử nghiệm | Luồng bình thường end-to-end: PDF → work order → lịch → Kanban | W3 | 3 | | | Cả nhóm + Mentor | Chưa bắt đầu | Bản chạy được trên staging, Kịch bản demo 1–3 |
| M5 | Xử lý xong phản hồi Demo 1 | Triển khai phản hồi; sự cố Line A, tái lập lịch, rủi ro, HITL | W4 | 4 | | | Cả nhóm | Chưa bắt đầu | Báo cáo phản hồi, Danh sách cập nhật |
| M6 | Demo 2 — Sản phẩm hoàn thiện | Đủ kịch bản 1–6, KPI, đăng nhập Google | W5 | 5 | | | Cả nhóm + Mentor | Chưa bắt đầu | Sản phẩm hoàn thiện, Báo cáo chỉ số (`eval/results/report.md`) |
| M7 | Phiên bản chính thức hoạt động | Triển khai thực tế, có người dùng thật | W6 | 6 | | | Cả nhóm | Chưa bắt đầu | Địa chỉ sản phẩm, Checklist triển khai |
| M8 | Đánh giá cuối kỳ | Thuyết trình tổng kết, báo cáo tác động | W6 | 6 | | | Cả nhóm + Mentor | Chưa bắt đầu | Slide, Video demo, Báo cáo tác động (`presentation/`) |

## Câu hỏi mở cho đối tác (gom từ các đặc tả)
- Mẫu PDF ticket thật (15–20 file, có bản scan, đã ẩn danh)
- Đơn đang chiếu dở khi line hỏng có phải chạy lại từ đầu?
- Ca làm của line: nhóm chốt tạm ca ngày 06:00–22:00, ca đêm chỉ đơn Khẩn / VIP (BR-14) — đối tác xác nhận?
- Ngưỡng WARN/BLOCK
- Tên miền email được phép; ADC dùng Google Workspace hay Microsoft?
