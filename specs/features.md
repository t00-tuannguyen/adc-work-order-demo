# Features — Tính năng, Functional Requirements & User Stories

## 1. Danh sách tính năng (8 đặc tả)

Mỗi tính năng có 1 file đặc tả đầy đủ (Động lực → Thiết kế → Kế hoạch) trong `tasks/`.

| Mã | Tính năng | FR | Ưu tiên | Sprint | Đặc tả |
|---|---|---|---|---|---|
| ADC-001 | Tiếp nhận ticket từ file PDF và tạo lệnh sản xuất (Order Agent) | FR 01, FR 02 | P0 | Sprint 1, 2, 3 | [ADC-001](../tasks/ADC-001-ticket-intake-pdf.md) |
| ADC-002 | Ước tính thời gian xử lý (mô hình throughput mô phỏng) | FR 03 | P0 | Sprint 1, 2 | [ADC-002](../tasks/ADC-002-duration-estimation.md) |
| ADC-003 | Xếp lịch Line A / Line B và hiển thị Kanban + lịch | FR 04, FR 05 | P0 | Sprint 2, 3 | [ADC-003](../tasks/ADC-003-line-scheduling-kanban.md) |
| ADC-004 | Xử lý sự cố line và tái lập lịch theo ưu tiên | FR 06 – FR 09 | P0 | Sprint 4 | [ADC-004](../tasks/ADC-004-incident-rescheduling.md) |
| ADC-005 | Kiểm soát rủi ro: cảnh báo/chặn đơn mới và escalation cho kinh doanh | FR 10, FR 11, FR 14 | P0 (FR 14: P1) | Sprint 4, 5 | [ADC-005](../tasks/ADC-005-risk-control-escalation.md) |
| ADC-006 | Phê duyệt HITL, quản lý phiên bản kế hoạch và audit log (Orchestrator) | FR 12 | P0 | Sprint 2, 3, 4 | [ADC-006](../tasks/ADC-006-hitl-approval-plan-version-audit.md) |
| ADC-007 | Bảng KPI và so sánh chế độ 1 line / 2 line | FR 13 | P1 | Sprint 5, 6 | [ADC-007](../tasks/ADC-007-kpi-dashboard-line-comparison.md) |
| ADC-008 | Đăng ký, đăng nhập và đăng xuất bằng tài khoản Google | — (bổ sung ngoài PRD) | P1 (đề xuất — ngoài PRD) | Sprint 5 | [ADC-008](../tasks/ADC-008-google-auth.md) |

## 2. Functional Requirements (PRD)

| ID | Ưu tiên | Yêu cầu | Tiêu chí chấp nhận | Tính năng |
|---|---|---|---|---|
| FR 01 | P0 | Tạo work order từ ticket | Trường bắt buộc được lưu kèm nguồn và timestamp | ADC-001 |
| FR 02 | P0 | Trích xuất & kiểm tra trường ticket | Thiếu sản phẩm, số lượng, quy cách, liều hoặc giờ trả → yêu cầu bổ sung | ADC-001 |
| FR 03 | P0 | Ước tính thời lượng xử lý | Tính từ giả định cấu hình hiển thị được | ADC-002 |
| FR 04 | P0 | Xếp lên Line A hoặc Line B | Lịch có line, start, end, plan version | ADC-003 |
| FR 05 | P0 | Hiển thị Kanban và lịch | Thấy trạng thái và phân bổ line của mọi đơn đang hoạt động | ADC-003 |
| FR 06 | P0 | Mô phỏng sự cố line | Chọn được line bị ảnh hưởng và thời gian dừng dự kiến | ADC-004 |
| FR 07 | P0 | Phát hiện đơn bị ảnh hưởng | Liệt kê đơn chồng lấn khung dừng | ADC-004 |
| FR 08 | P0 | Kiểm tra năng lực line thay thế | Kiểm tra Line B hoặc Line A có nhận được đơn bị ảnh hưởng | ADC-004 |
| FR 09 | P0 | Tái lập lịch theo ưu tiên | VIP và Khẩn được bảo vệ trước Thường | ADC-004 |
| FR 10 | P0 | Cảnh báo/chặn đơn mới rủi ro | Đơn mới hiện trạng thái rủi ro khi năng lực không đáp ứng giờ trả | ADC-005 |
| FR 11 | P0 | Escalate trả trễ | Đơn trễ tạo mục escalation cho kinh doanh | ADC-005 |
| FR 12 | P0 | Bắt buộc duyệt HITL | Plan version ảnh hưởng khách không ACTIVE khi chưa duyệt | ADC-006 |
| FR 13 | P1 | So sánh 1 line vs 2 line | Dashboard thể hiện khác biệt lịch và KPI | ADC-007 |
| FR 14 | P1 | Soạn thông điệp kinh doanh | AI soạn, người duyệt trước khi gửi | ADC-005 |

## 3. User Stories

> Sheet *Danh sách User Story* trong template còn trống. Danh sách dưới đây ghép từ trường "Mã User Story liên quan" của 8 đặc tả và FR tương ứng — **cần nhóm rà lại và điền lại vào sheet**.

| Mã | Tên câu chuyện | Vai trò | FR | Tính năng | Trạng thái |
|---|---|---|---|---|---|
| US-001 | Tạo work order từ ticket PDF | SALES | FR 01 | ADC-001 | Chưa làm |
| US-002 | Trích xuất & kiểm tra trường ticket, yêu cầu bổ sung | SALES | FR 02 | ADC-001 | Chưa làm |
| US-003 | Ước tính thời lượng xử lý từ giả định cấu hình | PLANNER | FR 03 | ADC-002 | Chưa làm |
| US-004 | Xếp lịch lên Line A hoặc Line B | PLANNER | FR 04 | ADC-003 | Chưa làm |
| US-005 | Xem Kanban và lịch 2 line | PLANNER / SALES / OPS | FR 05 | ADC-003 | Chưa làm |
| US-006 | Khai báo (mô phỏng) sự cố line | PLANNER | FR 06 | ADC-004 | Chưa làm |
| US-007 | Phát hiện đơn bị ảnh hưởng bởi sự cố | PLANNER | FR 07 | ADC-004 | Chưa làm |
| US-008 | Kiểm tra năng lực line thay thế | PLANNER | FR 08 | ADC-004 | Chưa làm |
| US-009 | Tái lập lịch theo ưu tiên | PLANNER | FR 09 | ADC-004 | Chưa làm |
| US-010 | Cảnh báo / chặn đơn mới rủi ro | SALES / OPS | FR 10 | ADC-005 | Đang làm |
| US-011 | Escalate đơn trả trễ cho kinh doanh | SALES | FR 11 | ADC-005 | Đang làm |
| US-012 | Duyệt plan version ảnh hưởng khách (HITL) | OPS_MANAGER / SALES | FR 12 | ADC-006 | Chưa làm |
| US-013 | So sánh chế độ 1 line và 2 line | OPS_MANAGER | FR 13 | ADC-007 | Chưa làm |
| US-014 | AI soạn nháp thông điệp kinh doanh | SALES | FR 14 | ADC-005 | Đang làm |
| US-015 | Xem lịch sử trạng thái & audit log | Mọi vai trò | FR 12 | ADC-006 | Chưa làm |
| US-016 | Reset dữ liệu demo & xem giả định vận hành | Nhóm phát triển | FR 03 | ADC-002 | Chưa làm |
| US-017 | Đăng ký lần đầu bằng Google | Nhân viên | — | ADC-008 | Chưa làm |
| US-018 | Đăng nhập bằng Google | Nhân viên | — | ADC-008 | Chưa làm |
| US-019 | Đăng xuất | Nhân viên | — | ADC-008 | Chưa làm |
| US-020 | Quản lý người dùng & cấp vai trò | ADMIN | — | ADC-008 | Chưa làm |

US-021 → US-028: còn trống (template có 28 dòng).

Mẫu viết: *Với vai trò **[X]**, tôi muốn **[Y]**, để đạt được **[Z]**.*

Thang ưu tiên US: Bắt buộc · Nên có · Có thì tốt · Không làm.
