# Kịch bản demo

Dùng seed dataset cố định (`src/seed/`), reset trước mỗi lần chạy.

## 1. Normal order — ADC-001 → 003
1. Tải PDF mẫu đầy đủ → form 8 trường có highlight vùng nguồn.
2. Tạo lệnh → ước tính (vd 180 phút) → xếp lên line khả thi sớm nhất.
3. Kanban + timeline cập nhật. **Đo: ticket → lịch < 5 giây.**

## 2. Missing fields — ADC-001
PDF thiếu liều và giờ trả → yêu cầu bổ sung đúng 2 trường, nút tạo lệnh bị khóa.

## 3. Capacity conflict — ADC-003
Line A kín → Scheduler đề xuất Line B, Scheduler Agent giải thích lý do.

## 4. Line A incident — ADC-004, 005, 006 (USP)
1. Khai báo Line A dừng 09:00–12:00.
2. Màn Trước / Sau: đơn VIP/Khẩn sang Line B, đơn Thường bị DELAYED + SLA_RISK.
3. Escalation được tạo cho đơn trễ; AI soạn nháp thông điệp.
4. Plan version ở PENDING_APPROVAL — lịch ACTIVE chưa đổi → Quản lý duyệt. **Đo: đề xuất < 10 giây.**

## 5. New order during incident — ADC-005
Tạo đơn mới không kịp giờ trả → banner BLOCK kèm giờ trả sớm nhất khả thi; đơn kịp nhưng đẩy đơn khác trễ → WARN, cần duyệt.

## 6. KPI & 1 line vs 2 line — ADC-007
Chạy so sánh → biểu đồ đơn trễ, % đúng giờ, hiệu suất; bảng 6 Metrics PRD xanh/đỏ.

## Dự phòng khi pitch
- Tài khoản demo (feature flag) nếu Google/mạng lỗi.
- OCR và AI soạn thông điệp sau feature flag; tab "Dán nội dung" và nhập tay luôn bật.
