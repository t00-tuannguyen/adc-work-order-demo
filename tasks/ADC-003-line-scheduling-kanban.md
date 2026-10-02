# ADC-003: Xếp lịch Line A / Line B và hiển thị Kanban + lịch

> Nguồn: sheet *Đặc tả tính năng* — Đặc tả #3 trong `team_project_management_template.xlsx`.

| Trường | Giá trị |
|---|---|
| Đặc tả | #3 |
| User Story | US-004, US-005 (FR 04, FR 05) |
| Functional Requirement (PRD) | FR 04, FR 05 |
| Ưu tiên | P0 |
| Sprint | 2, 3 |
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

Kinh doanh hứa giờ trả với khách trong khi năng lực line và kho được kiểm tra riêng, dễ nhận đơn không kịp. Cần tự đề xuất line và khung giờ sớm nhất khả thi, và cho mọi bên cùng nhìn thấy trạng thái đơn.

### Người dùng mục tiêu

- Điều phối sản xuất (chính): xếp và theo dõi lịch.
- Kinh doanh: xem đơn đang ở giai đoạn nào.
- Quản lý vận hành: nắm tải của 2 line.

### Mục tiêu kỳ vọng

- Mỗi lệnh hợp lệ có line, giờ bắt đầu, giờ kết thúc và plan version (FR 04).
- Kanban + lịch hiển thị trạng thái và phân bổ line của mọi lệnh đang hoạt động (FR 05).
- Ticket → lịch dưới 5 giây.
- 0 trường hợp 2 lệnh chồng lấn trên cùng line.

### Phương án thay thế đã xem xét

- Để LLM xếp lịch trực tiếp: không tái lập, có thể chồng lấn → loại.
- Solver tối ưu (vd OR-Tools): mạnh nhưng quá sức 6 tuần, khó giải thích → để sau MVP.

**→ Chọn:** thuật toán greedy "earliest feasible" có luật ưu tiên, dễ kiểm chứng.

## 2. Thiết kế (Design)

### Kiến trúc hệ thống

Scheduler (deterministic):

- Giờ bắt đầu sớm nhất = max(expected_arrival, hiện tại).
- Duyệt Line A và Line B, tìm khe trống đầu tiên đủ thời lượng trong giờ vận hành.
- Chọn line cho giờ kết thúc sớm nhất; hòa → Line A.
- Nếu giờ kết thúc > requested_return → gắn SLA_RISK, chuyển sang kiểm soát rủi ro (Đặc tả #5).
- Không ảnh hưởng SLA → gán luôn, không cần duyệt (theo bảng Human Approval Rules).

Mỗi thay đổi lịch tạo plan version mới (Đặc tả #6). Scheduler Agent chỉ gọi hàm này và diễn giải kết quả.

### Thiết kế giao diện (UI/UX)

- Kanban: cột theo nhóm trạng thái (Nháp, Chờ duyệt, Đã xếp lịch, Chờ hàng đến, Đang chiếu xạ, Chờ trả, Hoàn tất) + cột ngoại lệ (Rủi ro SLA, Đã escalate). Thẻ hiển thị mã đơn, sản phẩm, ưu tiên (màu VIP / Khẩn / Thường), giờ trả.
- Lịch dạng timeline 2 hàng (Line A, Line B) theo giờ; khối màu theo ưu tiên, vạch đỏ tại giờ trả; bấm khối xem chi tiết và lý do xếp.
- Bộ chọn plan version để xem lịch cũ.

### Thiết kế API

- POST /api/work-orders/{id}/schedule → {line, start, end, plan_version, sla_ok}
- GET /api/schedule?version=current|{n}&date= → slot của 2 line
- GET /api/work-orders?state= → dữ liệu Kanban
- PATCH /api/work-orders/{id}/state → chuyển trạng thái vận hành (hàng đến, bắt đầu chiếu, xong…), kiểm tra theo state machine.

### Mô hình dữ liệu

- lines(id, name, status, working_hours)
- schedule_slots(id, plan_version_id FK, work_order_id FK, line ENUM[A, B], start_at, end_at) — kiểm tra không chồng lấn ở tầng service

Index: schedule_slots(plan_version_id, line, start_at).

### Thiết kế AI/ML

Scheduler Agent (LLM) nhận kết quả của hàm xếp lịch và viết 1–2 câu giải thích, vd "Chọn Line B lúc 10:30 vì Line A kín đến 14:00". LLM không tự sinh giờ; validator đối chiếu mọi con số trong câu giải thích với dữ liệu.

### Trường hợp đặc biệt và Xử lý lỗi

- Không line nào kịp giờ trả → vẫn đề xuất slot sớm nhất + SLA_RISK.
- Thời lượng dài hơn giờ vận hành còn lại trong ngày → kéo sang đầu ca ngày hôm sau, không cắt đôi lệnh (BR-14, T-054); chỉ đơn Khẩn / VIP được chạy ca đêm.
- Hàng đến trễ hơn expected_arrival → giữ WAITING_ARRIVAL, tính lại lịch.
- Hai người xếp cùng lúc → khóa lạc quan theo plan version.

### Bảo mật và Quyền riêng tư

- Điều phối được xếp/sửa lịch; Kinh doanh chỉ xem.
- Chuyển trạng thái vận hành thủ công chỉ dành cho Điều phối.

## 3. Kế hoạch (Plan)

### Các bước thực hiện

1. Mô hình line và slot (3h)
2. Thuật toán earliest feasible + test (10h)
3. API lịch (5h)
4. Giao diện Kanban (8h)
5. Timeline 2 line (10h)
6. Giải thích bằng Scheduler Agent (4h)

### Công việc con (liên kết Backlog)

- T-027: Thuật toán xếp lịch earliest feasible
- T-028: API lịch & plan version
- T-029: Giao diện Kanban
- T-030: Giao diện lịch 2 line (timeline)
- T-054: Ca ngày / ca đêm theo ưu tiên (BR-14)

### Phụ thuộc

- Cần: ước tính thời lượng (Đặc tả #2), state machine + plan version (Đặc tả #6).
- Nguồn lực: thư viện timeline dựng sẵn cho frontend.

### Timeline dự kiến

Sprint 2 → Sprint 3 (thuật toán + API Tuần 2, UI Tuần 3). Tổng dự kiến ~40 giờ. [Điền ngày cụ thể]

### Kế hoạch kiểm thử

- Đơn thường, 2 line trống → Line A, bắt đầu từ giờ hàng đến.
- Line A kín → chuyển Line B (kịch bản "Capacity conflict").
- Không line nào kịp → SLA_RISK.
- 20 lệnh ngẫu nhiên → không chồng lấn.
- Đo ticket → lịch < 5 giây.

### Kế hoạch triển khai

Demo end-to-end luồng bình thường trên staging cuối Sprint 3 (Demo 1).

### Tiêu chí thành công

- FR 04, FR 05 đạt.
- Kịch bản "Normal order" và "Capacity conflict" chạy đúng.
- 0 chồng lấn trong mọi plan version.

### Rủi ro và Cách giảm thiểu

- Greedy chưa tối ưu toàn cục → chấp nhận trong MVP, ghi rõ giới hạn; thể hiện hiệu quả qua KPI (Đặc tả #7).
- UI timeline tốn thời gian → dùng thư viện có sẵn (vd FullCalendar, vis-timeline).
- Lệch múi giờ → lưu UTC, hiển thị giờ địa phương.

## Task con & trạng thái

| Task | Nội dung | Sprint | Dự kiến (giờ) | Owner | Trạng thái |
|---|---|---|---|---|---|
| T-027 | Thuật toán xếp lịch earliest feasible | 2 | 13 | — | Chờ review |
| T-028 | API lịch & plan version | 2 | 9 | — | Chờ review |
| T-029 | Giao diện Kanban | 3 | 8 | — | Chờ review |
| T-030 | Giao diện lịch 2 line (timeline) | 3 | 10 | — | Chờ review |
| T-054 | Ca ngày / ca đêm theo ưu tiên (BR-14) | 3 | 3 | — | Chờ review |

## Nhật ký

- 23/09/2026: Tạo từ Đặc tả #3.
- 25/09/2026: Chuyển sang lộ trình 6 tuần (6 sprint); cập nhật sprint của task con và timeline.
- 01/10/2026: Chốt giả định MVP — line chạy 24/7, không ràng buộc giờ vận hành; đơn dài hơn phần còn lại của ngày chạy liên tục sang ngày sau (không cắt đơn). Đổi khi đối tác trả lời (specs/domains.md §7).
- 01/10/2026: T-027 xong — `Placement` giữ phương án từng line (`options`), `placement_reason()` sinh lý do xếp deterministic từ chính kết quả (con số luôn khớp dữ liệu). Scheduler Agent (LLM) diễn giải lại câu này để ở T-034.
- 01/10/2026: Chốt khi giờ xong > giờ trả (Risk ADC-005 chưa có, bảng chuyển không có FEASIBILITY_CHECK → SLA_RISK): plan version PENDING_APPROVAL với thay đổi `RETURN_TIME_CHANGE` (cần duyệt), lịch ACTIVE giữ nguyên, đơn → PENDING_APPROVAL; Kanban xếp vào cột "Rủi ro SLA". Duyệt/từ chối ở T-042.
- 01/10/2026: T-028 xong — bảng `plan_versions`, `plan_changes` (orchestration) và `schedule_slots` (scheduling), migration 0005. Mỗi lần xếp = 1 version mới (slot version ACTIVE + slot mới); khóa lạc quan bằng cập nhật có điều kiện version ACTIVE → 409. Contract §3 đã bổ sung trước: `plan_status`, `reason` trong response xếp lịch, shape `ScheduleSlot` / `WorkOrderCard`, `GET /api/plan-versions?status=` (chỉ đọc, cho bộ chọn version), `LOCAL_UTC_OFFSET` cho `date=` và giờ trong lý do. Lý do xếp lưu trong `plan_changes.new_value`, không thêm cột vào `schedule_slots`.
- 01/10/2026: Để sau: bảng `lines` (trạng thái line — cần ở ADC-004); tự xếp lịch ngay khi đơn vào FEASIBILITY_CHECK (Orchestrator T-043) — hiện Điều phối bấm "Xếp lịch"; hàng đến trễ → tính lại lịch (cần luồng tái lập lịch T-033).
- 01/10/2026: Chạy thử Kanban: nhiều đơn trễ liên tiếp đều được đề xuất cùng khung Line A (mỗi version chờ duyệt chỉ dựa trên lịch ACTIVE). Sửa: slot đề xuất của version PENDING_APPROVAL được coi là đã giữ chỗ khi tìm khe, không chép vào version mới. T-042 khi duyệt cần gộp slot đề xuất vào version ACTIVE hiện tại (không xung đột vì đã giữ chỗ).
- 01/10/2026: T-029 xong — trang `/board` (mọi vai trò): 7 cột nhóm trạng thái + 2 cột ngoại lệ; FEASIBILITY_CHECK nằm ở cột Nháp với nhãn "Chờ xếp lịch"; PENDING_APPROVAL / RESCHEDULE_REQUIRED / BLOCK_NEW_ORDER ở Chờ duyệt; lịch trễ giờ trả hoặc LINE_INCIDENT / SLA_RISK ở Rủi ro SLA. Điều phối có nút Xếp lịch, "Xếp tất cả đơn chờ" (thứ tự BR-05) và nút bước vận hành kế tiếp. Logic nhóm cột ở `frontend/src/lib/board.ts` (test node --test).
- 01/10/2026: T-030 xong — trang `/schedule` (mọi vai trò): timeline 24h giờ Việt Nam cho Line A / B, khối màu theo ưu tiên (VIP tím · Khẩn vàng · Thường xanh), viền đứt đỏ khi trễ giờ trả, vạch đỏ tại giờ trả, khối qua nửa đêm cắt ở 2 ngày; bấm khối xem chi tiết + lý do xếp; bộ chọn plan version (ACTIVE / từng version cũ hoặc chờ duyệt) và ngày. Dựng bằng CSS, không thêm FullCalendar / vis-timeline (giữ ADR-0002, giảm phụ thuộc). Đã chạy thử end-to-end trên trình duyệt (seed reset → xếp tất cả → xem lịch).
- 01/10/2026: Nhóm chốt lại giả định giờ vận hành (thay mục "line chạy 24/7" ở trên): line chạy 24/7 nhưng ưu tiên ca ngày 06:00–22:00; ca đêm chỉ cho đơn khẩn cấp. Hiểu "khẩn cấp" = Khẩn + VIP (VIP xếp trên Khẩn theo BR-05). Thêm BR-14 vào specs/domains.md, mở T-054.
- 01/10/2026: T-054 xong — `ShiftPolicy` trong src/modules/scheduling/scheduler.py, cấu hình `lines.shifts` trong throughput.yaml (kiểm tra lúc nạp, file sai → giữ bản cũ). `earliest_start_on_line` nhận thêm ràng buộc ca; áp dụng cho xếp lịch đơn mới và tái lập lịch sự cố. Lý do xếp ghi "đơn Thường chỉ chạy ca ngày 06:00–22:00 → bắt đầu 06:00 02/10" khi bị dời; đơn Thường dài hơn ca → `422`. Bỏ mục `lines` → chạy 24/7 như trước.
- 02/10/2026: Tự xếp lịch khi tạo ticket (một phần T-043): đơn vào FEASIBILITY_CHECK qua `submit` hoặc cổng tự động (TEXT/PDF) → `auto_schedule` (src/agents/intake_pipeline.py) gọi `schedule_work_order` với actor = người tạo ticket. Kinh doanh vẫn không có quyền `EDIT_SCHEDULE` (không bấm Xếp lịch / sửa lịch). Không xếp được → giữ FEASIBILITY_CHECK, Điều phối xếp tay. Contract §1 `submit` / `POST /api/tickets` đã cập nhật trước.
- 02/10/2026: Xếp / sửa lịch thủ công cho Điều phối (BR-15, chốt với chủ dự án): trùng slot → từ chối (409, nêu đơn đang chiếm); trễ giờ trả → version `RETURN_TIME_CHANGE` chờ duyệt, lịch ACTIVE giữ nguyên; tuân luật ca BR-14. `PUT /api/work-orders/{id}/schedule` (contract §3 cập nhật trước), `manual_placement` (scheduling) + `place_work_order_manually` (orchestration, plan version `trigger: MANUAL`). UI: nút "Xếp tay" / "Sửa lịch" trên thẻ Board và chi tiết khối ở /schedule (chỉ khi xem version ACTIVE). Duyệt phương án trễ chờ T-042.
- 02/10/2026 (T-056): Tinh chỉnh UX theo góp ý chủ dự án:
  - Upload 1 file → 1 lệnh: lệnh đã tự tạo (khác DRAFT) chuyển thẳng sang Kanban; chỉ lệnh DRAFT cần xử lý mới mở màn xác nhận (`afterUploadPath`).
  - Dòng "Lịch" trên thẻ Kanban là link sang `/schedule?date=…&wo=…[&version=…]`: mở đúng ngày bắt đầu (giờ VN), đúng plan version nếu là đề xuất, viền + cuộn tới khối và mở sẵn chi tiết.
  - `placement_reason` viết lại ngắn gọn, mỗi ý 1 câu: "Line A 06:00–10:45 04/10. Sẵn sàng 23:00 03/10 nhưng đơn chỉ chạy ca ngày 06:00–22:00 → bắt đầu 06:00 04/10. Các line xong cùng lúc → chọn Line A. Kịp giờ trả 17:00 05/10." Mốc rơi vào nhiều ngày → mốc nào cũng kèm ngày. Ví dụ trong api-contracts §3 cập nhật trước. Lý do đã lưu của slot cũ giữ nguyên.
  - Giờ trả trên lịch hiện bằng cờ đỏ (hover xem giờ): trong ngày đang xem → cờ trên vạch đỏ; khác ngày → cờ trong khối.
  - Màn Tiếp nhận: bỏ nhãn "Chờ tải lên", nút "Bỏ" thành icon ✕; hỏi trạng thái ingest job giãn dần 1s → tối đa 5s (`pollDelay`) và dừng khi rời trang (OCR ~30s: ~34 → ~10 lệnh GET).
