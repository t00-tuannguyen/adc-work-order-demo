# ADC-002: Ước tính thời gian xử lý (mô hình throughput mô phỏng)

> Nguồn: sheet *Đặc tả tính năng* — Đặc tả #2 trong `team_project_management_template.xlsx`.

| Trường | Giá trị |
|---|---|
| Đặc tả | #2 |
| User Story | US-003, US-016 (FR 03) |
| Functional Requirement (PRD) | FR 03 |
| Ưu tiên | P0 |
| Sprint | 1, 2 |
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

Muốn xếp lịch phải biết mỗi lệnh chiếm line bao lâu. Nhóm không có dữ liệu năng suất thật của ADC và không được phép tính liều chiếu thật (ngoài phạm vi, liên quan an toàn). Cần một mô hình giả lập minh bạch, chỉnh được và cho kết quả tái lập.

### Người dùng mục tiêu

- Điều phối sản xuất: xem thời lượng dự kiến của từng lệnh.
- Nhóm phát triển / người chạy demo: chỉnh tham số để tạo tình huống.

Hiện tại: điều phối ước lượng theo kinh nghiệm, khó giải thích và khó kiểm chứng.

### Mục tiêu kỳ vọng

- Thời lượng tính từ các tham số cấu hình hiển thị được (FR 03).
- Cùng input + cùng cấu hình → cùng kết quả (100% tái lập).
- Tính dưới 100 ms/lệnh.
- Đổi tham số trong file cấu hình, không cần sửa code.

### Phương án thay thế đã xem xét

- Để LLM ước tính thời lượng: không tái lập, khó kiểm chứng → loại.
- Huấn luyện ML: không có dữ liệu sản xuất thật (non-goal của PRD) → loại.
- Bảng tra cố định theo sản phẩm: đơn giản nhưng bỏ qua số lượng và liều.

**→ Chọn:** công thức tuyến tính có tham số cấu hình.

## 2. Thiết kế (Design)

### Kiến trúc hệ thống

Module thuần, không gọi AI: estimate_duration(work_order, config), nằm trong service Scheduler.
Công thức (theo PRD):

- total_weight = quantity × pkg_weight_kg
- total_volume = quantity × dài × rộng × cao (m³)
- weight_load = total_weight × min_per_kg × density_factor[product_type]
- volume_load = total_volume × min_per_m3
- dose_load = (weight_load + volume_load) × (dose_factor[dose] − 1)
- buffer = (setup + weight_load + volume_load + dose_load) × buffer_pct
- duration = tổng các phần trên, làm tròn lên bội số 15 phút.

Ví dụ (tham số giả lập: setup 30', 0.05'/kg, 10'/m³, gia vị 1.0, 10 kGy = 1.5, buffer 10%): 120 thùng × 8 kg, 40×30×25 cm → 960 kg, 3.6 m³ → 30 + 48 + 36 + 42 + 15.6 ≈ 172' → 180 phút.
Cấu hình đọc từ file (vd config/throughput.yaml); seed dataset (≥ 5 lệnh + 1 sự cố Line A) nạp qua lệnh reset.

### Thiết kế giao diện (UI/UX)

- Chi tiết lệnh: "Thời lượng dự kiến: 3h00" kèm bảng breakdown từng thành phần.
- Trang "Giả định vận hành" (chỉ đọc trong MVP): liệt kê tham số đang dùng, có nhãn "Giá trị giả lập – không phải thông số vật lý thật".
- Nút "Reset dữ liệu demo".

### Thiết kế API

- POST /api/estimate {các trường work order} → {duration_min, breakdown{setup, weight_load, volume_load, dose_load, buffer}, config_version}
- GET /api/config/throughput → tham số hiện hành
- POST /api/demo/reset → nạp lại seed dataset
- Input thiếu/không hợp lệ → 422.

### Mô hình dữ liệu

- Không cần bảng cho cấu hình (dùng file).
- Thêm cột work_orders: estimated_duration_min, estimate_breakdown (JSON), config_version.
- File seed: seed/orders.json, seed/incidents.json.

### Thiết kế AI/ML

Không dùng AI (chủ đích deterministic). Các agent chỉ đọc breakdown để giải thích cho người dùng.

### Trường hợp đặc biệt và Xử lý lỗi

- Loại sản phẩm hoặc liều không có trong cấu hình → báo lỗi rõ, không tự lấy mặc định.
- Số lượng ≤ 0 → 422.
- Thời lượng dài hơn giờ vận hành còn lại → Scheduler xử lý (Đặc tả #3).
- File cấu hình sai định dạng → không khởi động, ghi log lỗi.

### Bảo mật và Quyền riêng tư

- Chỉ nhóm phát triển chỉnh file cấu hình (qua repo).
- Endpoint reset chỉ bật ở môi trường demo/staging.

## 3. Kế hoạch (Plan)

### Các bước thực hiện

1. Chốt công thức và tham số mẫu với mentor (2h)
2. Viết module + unit test (6h)
3. File cấu hình + reload (2h)
4. Seed dataset và nút reset (4h)
5. Hiển thị breakdown trên UI (4h)

### Công việc con (liên kết Backlog)

- T-023: File cấu hình giả định throughput
- T-024: Hàm ước tính thời lượng + unit test
- T-025: Seed dataset & reset demo
- T-026: Hiển thị breakdown thời lượng trên UI

### Phụ thuộc

- Cần schema work order (Đặc tả #1, T-017).
- Là nền cho xếp lịch (Đặc tả #3) và xử lý sự cố (Đặc tả #4).

### Timeline dự kiến

Sprint 1 → Sprint 2 (Tuần 1: cấu hình, hàm ước tính, seed; Tuần 2: breakdown trên UI). Tổng dự kiến ~18 giờ. [Điền ngày cụ thể]

### Kế hoạch kiểm thử

- Ví dụ mẫu ở trên cho kết quả 180 phút.
- Cùng input chạy 100 lần → cùng kết quả.
- Tăng dose_factor → thời lượng tăng đúng tỷ lệ.
- Cấu hình thiếu key → báo lỗi.

Nghiệm thu FR 03: thời lượng tính từ tham số hiển thị được.

### Kế hoạch triển khai

Release hàm ước tính ngay Tuần 1 làm nền cho Scheduler (Tuần 2); tham số chỉnh qua file cấu hình.

### Tiêu chí thành công

- FR 03 đạt.
- Lệnh trong seed có thời lượng hợp lý (vừa lịch 1 ngày của 2 line và có xung đột khi 1 line dừng).
- Có thể chỉnh cấu hình để tạo tình huống quá tải khi demo.

### Rủi ro và Cách giảm thiểu

- Người xem hiểu nhầm là mô hình vật lý thật → nhãn cảnh báo trên UI và trong pitch.
- Tham số khiến lịch quá thưa/quá chật, demo không có xung đột → tinh chỉnh cùng seed dataset.

## Task con & trạng thái

| Task | Nội dung | Sprint | Dự kiến (giờ) | Owner | Trạng thái |
|---|---|---|---|---|---|
| T-023 | File cấu hình giả định throughput | 1 | 4 | — | Chờ review |
| T-024 | Hàm ước tính thời lượng + unit test | 1 | 6 | — | Chờ review |
| T-025 | Seed dataset & reset demo | 1 | 4 | — | Chờ review |
| T-026 | Hiển thị breakdown thời lượng trên UI | 2 | 4 | — | Chờ review |

## Nhật ký

- 23/09/2026: Tạo từ Đặc tả #2.
- 25/09/2026: Chuyển sang lộ trình 6 tuần (6 sprint); cập nhật sprint của task con và timeline.
- 01/10/2026 (T-023): Câu hỏi mở — hệ số `density_factor` seafood/fruit/medical_goods và `dose_factor` 5/25 kGy chưa chốt với mentor → giữ `null` (dùng tới thì báo lỗi theo BR-02); seed dataset tạm chỉ dùng gia vị 10 kGy.
- 01/10/2026 (T-023): Gán `product_group` từ tên sản phẩm bằng bảng từ khóa `product_groups` trong `throughput.yaml` (deterministic, không dùng LLM); khớp 0 hoặc ≥ 2 nhóm → không gán, ước tính báo lỗi. Đổi file cấu hình khi app đang chạy → tự nạp lại (so mtime); file mới sai → giữ bản cũ + log lỗi.
- 01/10/2026 (T-025): Seed 7 lệnh, giờ `HH:MM` gắn vào ngày reset (giờ +07:00) → mỗi lần reset cùng bố cục. Kiểm chứng bằng test: 2 line kịp hết giờ trả trong 1 ngày, sự cố Line A 09:00–12:00 đụng SEED-01/SEED-03, chế độ 1 line có đơn trễ. Đơn seed vào thẳng FEASIBILITY_CHECK qua Orchestration (có audit). Thêm cột `estimated_duration_min`, `estimate_breakdown`, `config_version` (migration 0004).
- 01/10/2026 (T-025): Câu hỏi mở — đặc tả chưa nói vai trò nào được reset; tạm cho mọi user ACTIVE (`VIEW_BOARD`), bảo vệ bằng cờ `DEMO_RESET_ENABLED` + chặn cứng ở `APP_ENV=production`. Reset chưa nạp sự cố vào DB (bảng có ở T-031), chỉ trả về trong response.
- 01/10/2026 (T-026): Ước tính được tính và lưu khi lệnh vào FEASIBILITY_CHECK (tự động hoặc submit); `WorkOrderReview` thêm `estimate` + `estimate_error` (đã cập nhật api-contracts trước). Màn xác nhận lệnh hiện "Thời lượng dự kiến 3h00" + breakdown (kèm dòng "Làm tròn lên" để tổng khớp); trang `/assumptions` liệt kê tham số + nhãn giả lập + nút "Reset dữ liệu demo" (bấm 2 lần để xác nhận).
- 02/10/2026: Bỏ thẻ ước tính thủ công (`EstimateCard`) và bảng giả định vận hành (`ThroughputCard`) khỏi giao diện; bỏ mục menu "Giả định vận hành". `/assumptions` chỉ còn nút reset demo (vào thẳng URL). API `/api/estimate`, `/api/config/throughput` giữ nguyên.
- 02/10/2026 (T-057): Bổ sung bảng từ khóa `product_groups` từ 65 ticket thật nhập 03–04/10/2026 (62 file đọc được; 3 file ID12 bản scan thiếu dòng hàng). Thêm nhóm `vegetable` (nấm, bắp cải, rau) và `powder` (bột thảo dược, bột mì) — `density_factor` = null, **cần chốt hệ số**; mở rộng `seafood` (ghẹ, ếch, cá tra/trê, tuna, squid, aji, trimmeat) và `fruit` (dưa lưới, chanh dây, chuối, thơm/khóm, mía). Không dùng từ khóa "bột" trơn vì "tôm tẩm bột" sẽ khớp 2 nhóm. Còn chưa gán nhóm: "Nhộng tằm đông lạnh", "Bánh crepe sầu riêng", mã hàng "(VCF-016) PORTION/LOIN" (cá ngừ nhưng tên không có từ khóa), thùng mẫu / mẫu HACCP.
