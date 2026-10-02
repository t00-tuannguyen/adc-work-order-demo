# ADC-007: Bảng KPI và so sánh chế độ 1 line / 2 line

> Nguồn: sheet *Đặc tả tính năng* — Đặc tả #7 trong `team_project_management_template.xlsx`.

| Trường | Giá trị |
|---|---|
| Đặc tả | #7 |
| User Story | US-013 (FR 13) |
| Functional Requirement (PRD) | FR 13 |
| Ưu tiên | P1 |
| Sprint | 5, 6 |
| Người viết | [Họ tên người phụ trách] |
| Ngày tạo / cập nhật | 23/09/2026 / 25/09/2026 |
| Trạng thái | Bản nháp |

## References
- [specs/features.md](../specs/features.md)
- [specs/api-contracts.md](../specs/api-contracts.md)
- [specs/domains.md](../specs/domains.md)
- [specs/user-roles.md](../specs/user-roles.md)
- [AGENTS.md](../AGENTS.md)

## 1. Động lực (Motivation)

### Vấn đề cần giải quyết

Đối tác và giám khảo cần thấy giá trị định lượng: điều phối 2 line kèm xử lý sự cố giúp giảm trễ và tăng hiệu suất line bao nhiêu so với vận hành 1 line.

### Người dùng mục tiêu

- Quản lý vận hành.
- Đối tác và giám khảo trong buổi pitch.

### Mục tiêu kỳ vọng

- Dashboard hiển thị KPI và chênh lệch 1 line vs 2 line trên cùng tập đơn (FR 13).
- Hiển thị đủ 6 chỉ số trong bảng Metrics của PRD (ticket → lịch, thời gian đề xuất phục hồi, thay đổi không duyệt, % lệnh có lịch sử, % đơn mới rủi ro được cảnh báo, % escalation).
- KPI chính: số đơn trễ, tổng phút trễ, % đúng giờ, hiệu suất line (thời gian bận / thời gian vận hành), thời gian hoàn tất trung bình.

### Phương án thay thế đã xem xét

- Chỉ trình bày số liệu tĩnh trên slide: nhanh nhưng kém thuyết phục.

**→ Chọn:** tính trực tiếp từ plan version bằng chính Scheduler, cho người xem chạy lại.

## 2. Thiết kế (Design)

### Kiến trúc hệ thống

KPI service đọc plan version (active hoặc được chọn) và tính chỉ số deterministic.
Chế độ so sánh: chạy Scheduler 2 lần trên cùng seed — (a) chỉ Line A, (b) Line A + B — có tùy chọn kèm sự cố. Kết quả lưu thành plan version mô phỏng, không ảnh hưởng lịch thật.

### Thiết kế giao diện (UI/UX)

Trang Dashboard:

- Hàng thẻ KPI.
- Biểu đồ cột so sánh 1 line vs 2 line (đơn trễ, % đúng giờ, hiệu suất).
- 2 timeline thu nhỏ đặt cạnh nhau.
- Bảng Metrics PRD: mục tiêu và giá trị đo thực (xanh = đạt, đỏ = chưa đạt).
- Nút "Chạy so sánh".

### Thiết kế API

- GET /api/kpi?plan_version= → {on_time_rate, late_orders, total_delay_min, utilization{A, B}, avg_lead_time}
- POST /api/simulations/compare {scenario: seed|current, include_incident} → {one_line: kpi, two_line: kpi, plan_version_ids}

### Mô hình dữ liệu

- plan_versions.is_simulation (bool, không bao giờ active)
- kpi_snapshots(id, plan_version_id FK, metrics JSON, computed_at)
- Ghi thời gian xử lý (ticket → lịch, sự cố → đề xuất) vào audit_log để tính Metrics.

### Thiết kế AI/ML

Không bắt buộc. Có thì tốt: LLM viết 2–3 câu tóm tắt nhận định từ số liệu KPI cho slide pitch; số liệu lấy nguyên từ API.

### Trường hợp đặc biệt và Xử lý lỗi

- Chưa có đơn → hiển thị trạng thái rỗng.
- Mẫu số hiệu suất bằng 0 → hiển thị 0%.
- Không trộn lịch mô phỏng với lịch thật (lọc theo is_simulation).

### Bảo mật và Quyền riêng tư

- Chỉ đọc; mọi vai trò đều xem được.
- Endpoint mô phỏng chỉ tạo version mô phỏng.

## 3. Kế hoạch (Plan)

### Các bước thực hiện

1. Định nghĩa và tính KPI + test (6h)
2. Chế độ mô phỏng 1 line (5h)
3. Dashboard (8h)
4. Kịch bản pitch và chốt số liệu (4h)

### Công việc con (liên kết Backlog)

- T-044: Tính KPI từ plan version
- T-045: Chế độ mô phỏng 1 line
- T-046: Dashboard KPI & so sánh
- T-047: Kịch bản demo pitch

### Phụ thuộc

- Cần: xếp lịch (Đặc tả #3), xử lý sự cố (Đặc tả #4), audit log (Đặc tả #6).

### Timeline dự kiến

Sprint 5 (Tuần 5: KPI, mô phỏng 1 line, dashboard) → Sprint 6 (Tuần 6: kịch bản pitch). Tổng dự kiến ~23 giờ. [Điền ngày cụ thể]

### Kế hoạch kiểm thử

- KPI tính tay trên seed khớp kết quả API.
- Trên seed, chế độ 1 line có số đơn trễ ≥ chế độ 2 line.
- Chạy mô phỏng không làm đổi version active.
- Dashboard hiển thị đủ 6 chỉ số Metrics.

### Kế hoạch triển khai

Bật cuối Sprint 5 (Demo 2) và dùng lại trong pitch cuối kỳ (Sprint 6); có thể ẩn bằng feature flag nếu chưa ổn định.

### Tiêu chí thành công

- FR 13 đạt.
- Kịch bản demo cho thấy chênh lệch rõ giữa 1 line và 2 line.
- Mọi chỉ số Metrics PRD có giá trị đo thực.

### Rủi ro và Cách giảm thiểu

- Seed không tạo chênh lệch đáng kể → tinh chỉnh seed và cấu hình (Đặc tả #2).
- Làm sau cùng nên dễ bị cắt → là P1, giữ phạm vi tối thiểu (thẻ KPI + 1 biểu đồ).

## Task con & trạng thái

| Task | Nội dung | Sprint | Dự kiến (giờ) | Owner | Trạng thái |
|---|---|---|---|---|---|
| T-044 | Tính KPI từ plan version | 5 | 6 | — | Chưa làm |
| T-045 | Chế độ mô phỏng 1 line | 5 | 5 | — | Chưa làm |
| T-046 | Dashboard KPI & so sánh | 5 | 8 | — | Chưa làm |
| T-047 | Kịch bản demo pitch | 6 | 4 | — | Chưa làm |

## Nhật ký

- 23/09/2026: Tạo từ Đặc tả #7.
- 25/09/2026: Chuyển sang lộ trình 6 tuần (6 sprint); cập nhật sprint của task con và timeline.
