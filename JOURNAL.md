# Weekly Journal — Team MFG 08 · ADC Irradiation Work Order

> Ghi lại mỗi tuần: học được gì, khó khăn gì, quyết định gì, kế hoạch tiếp.
> Mục tiêu tuần lấy từ `planning/sprints/sprint-NN.md`; quyết định kỹ thuật quan trọng → ghi ADR trong `adrs/`.

---

## Week 1: [Ngày bắt đầu] - [Ngày kết thúc] · W1 · M1 Project Charter, M2 Gặp đối tác

### Mục tiêu tuần này
> Sprint Goal: Chốt charter, kiến trúc, stack; nhận PDF mẫu và giả định từ đối tác; schema work order, file cấu hình throughput, hàm ước tính và seed dataset chạy được.

- [ ] T-001 — Lập Project Charter
- [ ] T-002 — Thiết lập GitHub và quy trình nhánh
- [ ] T-003 — Thiết kế sơ đồ kiến trúc hệ thống
- [ ] T-004 — Gặp đối tác lần đầu tiên
- [ ] T-005 — Xây dựng cơ sở tri thức phiên bản 1
- [ ] T-017 — Thiết kế schema ticket, file PDF & trường trích xuất
- [ ] T-023 — File cấu hình giả định throughput
- [ ] T-024 — Hàm ước tính thời lượng + unit test
- [ ] T-025 — Seed dataset & reset demo

### Đã hoàn thành
- 

### Khó khăn & Giải pháp
| Khó khăn | Giải pháp | Kết quả |
|----------|-----------|---------|
| | | |

### Quyết định (ADR / thay đổi spec)
- 

### Bài học
- 

### Kế hoạch tuần sau
- 

---

## Week 2: [Ngày bắt đầu] - [Ngày kết thúc] · W2 · M3 Hoàn thành thiết kế giải pháp

### Mục tiêu tuần này
> Sprint Goal: Lõi deterministic hoàn chỉnh: lệnh bình thường được đọc từ PDF, kiểm tra trường, ước tính thời lượng và đặt lên Line A hoặc Line B; có state machine và audit log.

- [ ] T-018 — API upload PDF, lưu file & job trích xuất
- [ ] T-048 — Đọc PDF văn bản + OCR bản scan
- [ ] T-020 — Validator & yêu cầu bổ sung
- [ ] T-026 — Hiển thị breakdown thời lượng trên UI
- [ ] T-027 — Thuật toán xếp lịch earliest feasible
- [ ] T-028 — API lịch & plan version
- [ ] T-040 — State machine work order
- [ ] T-041 — Audit log & lịch sử trạng thái

### Đã hoàn thành
- 

### Khó khăn & Giải pháp
| Khó khăn | Giải pháp | Kết quả |
|----------|-----------|---------|
| | | |

### Quyết định (ADR / thay đổi spec)
- 

### Bài học
- 

### Kế hoạch tuần sau
- 

---

## Week 3: [Ngày bắt đầu] - [Ngày kết thúc] · W3 · M4 Demo 1

### Mục tiêu tuần này
> Sprint Goal: Luồng bình thường end-to-end sẵn sàng demo: PDF → Order Agent → work order → lịch → Kanban/timeline, do Orchestrator điều phối. (Demo 1)

- [ ] T-006 — Phát triển các API endpoint chính
- [ ] T-007 — Phát triển giao diện chính
- [ ] T-008 — Tích hợp mô hình AI
- [ ] T-009 — Chuẩn bị Demo lần 1
- [ ] T-019 — Order Agent trích xuất trường kèm vị trí nguồn
- [ ] T-021 — Màn hình tiếp nhận: tải file, tiến độ, xem PDF, form kết quả
- [ ] T-022 — Bộ PDF mẫu & đánh giá độ chính xác
- [ ] T-029 — Giao diện Kanban
- [ ] T-030 — Giao diện lịch 2 line (timeline)
- [ ] T-043 — Orchestrator điều phối các agent

### Đã hoàn thành
- 

### Khó khăn & Giải pháp
| Khó khăn | Giải pháp | Kết quả |
|----------|-----------|---------|
| | | |

### Quyết định (ADR / thay đổi spec)
- 

### Bài học
- 

### Kế hoạch tuần sau
- 

---

## Week 4: [Ngày bắt đầu] - [Ngày kết thúc] · W4 · M5 Xử lý xong phản hồi Demo 1

### Mục tiêu tuần này
> Sprint Goal: Kịch bản "Line A down" chạy được: phát hiện đơn bị ảnh hưởng, dời theo ưu tiên, cảnh báo/chặn đơn mới, tạo escalation, plan version chờ duyệt HITL.

- [ ] T-010 — Xử lý phản hồi từ Demo 1
- [ ] T-031 — API & form mô phỏng sự cố
- [ ] T-032 — Phát hiện đơn chồng lấn khung dừng
- [ ] T-033 — Tái lập lịch theo ưu tiên + kiểm tra line thay thế
- [ ] T-034 — Scheduler Agent giải thích phương án
- [ ] T-035 — Màn hình so sánh trước/sau sự cố
- [ ] T-036 — Kiểm tra rủi ro đơn mới (WARN/BLOCK)
- [ ] T-037 — Tạo escalation cho đơn trễ
- [ ] T-042 — Luồng phê duyệt plan version (HITL)

### Đã hoàn thành
- 

### Khó khăn & Giải pháp
| Khó khăn | Giải pháp | Kết quả |
|----------|-----------|---------|
| | | |

### Quyết định (ADR / thay đổi spec)
- 

### Bài học
- 

### Kế hoạch tuần sau
- 

---

## Week 5: [Ngày bắt đầu] - [Ngày kết thúc] · W5 · M6 Demo 2

### Mục tiêu tuần này
> Sprint Goal: Sản phẩm hoàn thiện cho Demo 2: hàng đợi escalation + AI soạn thông điệp, KPI và so sánh 1 vs 2 line, đăng nhập Google + RBAC, audit gắn người dùng thật.

- [ ] T-011 — Phát triển thêm tính năng từ phản hồi
- [ ] T-012 — Kiểm thử toàn diện và Sửa lỗi
- [ ] T-038 — Risk Agent soạn thông điệp kinh doanh
- [ ] T-039 — Giao diện hàng đợi escalation
- [ ] T-044 — Tính KPI từ plan version
- [ ] T-045 — Chế độ mô phỏng 1 line
- [ ] T-046 — Dashboard KPI & so sánh
- [ ] T-049 — Cấu hình OAuth client Google & callback xác minh ID token
- [ ] T-050 — Phiên đăng nhập, đăng xuất & phân quyền RBAC
- [ ] T-051 — Màn đăng nhập / đăng ký / chờ cấp quyền / menu tài khoản
- [ ] T-052 — Trang quản lý người dùng & cấp vai trò
- [ ] T-053 — Gắn người dùng thật vào audit log

### Đã hoàn thành
- 

### Khó khăn & Giải pháp
| Khó khăn | Giải pháp | Kết quả |
|----------|-----------|---------|
| | | |

### Quyết định (ADR / thay đổi spec)
- 

### Bài học
- 

### Kế hoạch tuần sau
- 

---

## Week 6: [Ngày bắt đầu] - [Ngày kết thúc] · W6 · M7 Phiên bản chính thức, M8 Đánh giá cuối kỳ

### Mục tiêu tuần này
> Sprint Goal: Triển khai production, kiểm thử cuối, tài liệu hướng dẫn, kịch bản pitch và báo cáo tác động.

- [ ] T-013 — Triển khai lên môi trường thực tế
- [ ] T-014 — Kiểm thử cuối cùng và Tinh chỉnh giao diện
- [ ] T-015 — Viết tài liệu hướng dẫn
- [ ] T-016 — Chuẩn bị thuyết trình cuối kỳ
- [ ] T-047 — Kịch bản demo pitch

### Đã hoàn thành
- 

### Khó khăn & Giải pháp
| Khó khăn | Giải pháp | Kết quả |
|----------|-----------|---------|
| | | |

### Quyết định (ADR / thay đổi spec)
- 

### Bài học
- 

### Kế hoạch tuần sau
- 

---
