# Seed dataset

Theo PRD (Implementation Notes) và ADC-002 / ADC-004:

- `orders.json` — 7 lệnh gia vị 10 kGy (các hệ số khác còn TODO), đủ mức ưu tiên Thường / Khẩn / VIP. Giờ dạng `HH:MM` theo `timezone`, gắn vào ngày reset
- `incidents.json` — 1 sự cố Line A cố định, 09:00–12:00 — reset chỉ trả về làm mẫu; khai báo bằng `POST /api/incidents` sau khi xếp lịch các lệnh seed
- Nạp lại: `POST /api/demo/reset` (cần `DEMO_RESET_ENABLED=true`, không chạy ở `APP_ENV=production`) — xóa ticket/work order, giữ user và audit log
- `pdfs/` — 16 PDF mẫu giả lập (10 văn bản số, 6 scan) + `answers.json` (đáp án đã chuẩn hóa) để đánh giá trích xuất. Sinh lại: `python -m eval.intake.build_samples` (macOS, cần Chrome + `sips`); chạy đánh giá: `make eval-intake`

Yêu cầu: sau mỗi lần reset, kịch bản Line A incident cho kết quả giống hệt nhau; seed phải tạo được xung đột khi 1 line dừng và chênh lệch rõ giữa chế độ 1 line và 2 line.
