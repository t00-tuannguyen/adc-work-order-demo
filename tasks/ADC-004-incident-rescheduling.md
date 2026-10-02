# ADC-004: Xử lý sự cố line và tái lập lịch theo ưu tiên

> Nguồn: sheet *Đặc tả tính năng* — Đặc tả #4 trong `team_project_management_template.xlsx`.

| Trường | Giá trị |
|---|---|
| Đặc tả | #4 |
| User Story | US-006, US-007, US-008, US-009 (FR 06 – FR 09) |
| Functional Requirement (PRD) | FR 06 – FR 09 |
| Ưu tiên | P0 |
| Sprint | 4 |
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

Khi một line dừng, nhóm phải tự tìm các đơn bị ảnh hưởng và dựng lại lịch bằng tay. Việc này chậm, dễ ưu tiên sai (đơn thường giữ chỗ trong khi đơn VIP bị trễ) và làm trễ hẹn với khách. Đây là USP chính của dự án.

### Người dùng mục tiêu

- Điều phối sản xuất / Trưởng ca: khai báo sự cố, xem phương án phục hồi.
- Quản lý vận hành: duyệt phương án khi ảnh hưởng khách.

### Mục tiêu kỳ vọng

- Khai báo được line bị sự cố và thời gian dừng dự kiến (FR 06).
- Liệt kê đúng 100% đơn chồng lấn khung dừng (FR 07).
- Kiểm tra line còn lại có nhận được đơn bị ảnh hưởng không (FR 08).
- Ưu tiên VIP → Khẩn → Thường; cùng mức thì giờ trả sớm hơn trước (FR 09).
- Có phương án phục hồi dưới 10 giây.

### Phương án thay thế đã xem xét

- Chỉ báo động, để người lập lại lịch: không giải quyết vấn đề chính.
- Dời toàn bộ đơn bị ảnh hưởng đến sau khi sửa xong: đơn giản nhưng lãng phí line còn lại.

**→ Chọn:** thuật toán 10 bước theo "Incident Handling Logic" của PRD, tận dụng line thay thế với thứ tự ưu tiên rõ ràng.

## 2. Thiết kế (Design)

### Kiến trúc hệ thống

1. Nhận sự cố (line, thời điểm, thời gian dừng) → các lệnh liên quan chuyển LINE_INCIDENT.
2. Tìm slot chồng lấn [start, start + downtime].
3. Sắp theo ưu tiên, sau đó theo giờ trả.
4. Kiểm tra khe trống phù hợp trên line còn lại.
5. Dời đơn ưu tiên cao khả thi trước; nếu phải đẩy lùi đơn Thường chưa bắt đầu trên line thay thế thì đó là priority override → cần duyệt.
6. Đơn không dời được → xếp lại sau khi line hồi phục.
7. Dựng lại cả 2 lịch thành plan version mới.
8. Đơn vượt giờ trả → SLA_RISK.
9. Chuyển sang kiểm soát rủi ro và escalation (Đặc tả #5).
10. Gửi duyệt trước khi kích hoạt (Đặc tả #6).

Giả định cần xác nhận với đối tác: đơn đang chiếu dở trên line hỏng phải chạy lại từ đầu.

### Thiết kế giao diện (UI/UX)

- Nút "Khai báo sự cố" → form: line, thời điểm, thời gian dừng dự kiến, ghi chú.
- Màn hình so sánh Trước / Sau: 2 timeline cạnh nhau, vùng dừng tô xám gạch chéo.
- Bảng đơn bị ảnh hưởng: ưu tiên, line cũ → mới, giờ xong cũ → mới, giờ trả, trạng thái SLA.
- Đoạn giải thích của Scheduler Agent + nút "Gửi duyệt".

### Thiết kế API

- POST /api/incidents {line, start_at, est_downtime_min, note} → {incident_id, affected_orders[], proposed_plan_version, sla_risks[], explanation}
- GET /api/incidents/{id}
- POST /api/incidents/{id}/resolve {actual_end} → tính lại nếu line hồi phục sớm/muộn hơn dự kiến.

### Mô hình dữ liệu

- incidents(id, line, start_at, est_downtime_min, actual_end_at, status, created_by)
- incident_affected_orders(incident_id FK, work_order_id FK, old_slot_id, new_slot_id, outcome ENUM[MOVED_ALT_LINE, DELAYED, UNCHANGED])
- plan_versions bổ sung: trigger (NORMAL / INCIDENT), incident_id.

### Thiết kế AI/ML

- Scheduler Agent gọi tool deterministic reschedule(incident); không tự quyết thứ tự hay giờ.
- Orchestrator điều phối: Scheduler Agent → Risk & Escalation Agent.
- LLM viết giải thích cho từng đơn bị dời/hoãn bằng ngôn ngữ nghiệp vụ; validator kiểm tra giờ và line trong câu giải thích khớp dữ liệu.

### Trường hợp đặc biệt và Xử lý lỗi

- Thời gian dừng = 0 hoặc nằm hoàn toàn trong quá khứ → không có đơn bị ảnh hưởng.
- Không còn khe trống → mọi đơn bị ảnh hưởng trễ và được escalate.
- Sự cố kéo dài hơn dự kiến → tạo plan version mới từ version đang active.
- Cả 2 line cùng dừng → trả phương án, tất cả đơn liên quan thành SLA_RISK.
- Đơn VIP vẫn trễ dù đã ưu tiên → escalate ngay.

### Bảo mật và Quyền riêng tư

- Chỉ Điều phối / Trưởng ca được khai báo sự cố.
- Phương án chưa duyệt không thay đổi lịch active.
- Ghi audit người khai báo và thời điểm.

## 3. Kế hoạch (Plan)

### Các bước thực hiện

1. Form + API sự cố (5h)
2. Phát hiện đơn chồng lấn (4h)
3. Tái lập lịch theo ưu tiên + kiểm tra line thay thế (14h)
4. Giải thích bằng Scheduler Agent (5h)
5. Màn hình Trước / Sau (8h)
6. Kịch bản seed "Line A down" (2h)

### Công việc con (liên kết Backlog)

- T-031: API & form mô phỏng sự cố
- T-032: Phát hiện đơn chồng lấn khung dừng
- T-033: Tái lập lịch theo ưu tiên + kiểm tra line thay thế
- T-034: Scheduler Agent giải thích phương án
- T-035: Màn hình so sánh trước/sau sự cố

### Phụ thuộc

- Cần: xếp lịch (Đặc tả #3), plan version và luồng duyệt (Đặc tả #6).
- Đi kèm: kiểm soát rủi ro và escalation (Đặc tả #5).

### Timeline dự kiến

Sprint 4 (Tuần 4). Tổng dự kiến ~38 giờ. [Điền ngày cụ thể]

### Kế hoạch kiểm thử

Seed: ≥ 5 lệnh, Line A dừng 09:00–12:00.

- Danh sách đơn chồng lấn khớp kết quả tính tay.
- Đơn VIP / Khẩn sang Line B trước đơn Thường.
- Đơn Thường không vừa → DELAYED + SLA_RISK.
- Plan version mới không chồng lấn.
- Phương án < 10 giây.
- Lịch active không đổi khi chưa duyệt.

### Kế hoạch triển khai

Bật sau Sprint 4; khóa kịch bản "Line A incident" cố định trong seed để dùng cho Demo 2 và pitch.

### Tiêu chí thành công

- FR 06 – FR 09 đạt.
- Kịch bản Line A incident cho kết quả giống nhau sau mỗi lần reset.
- Không có đơn ưu tiên cao bị trễ trong khi đơn ưu tiên thấp hơn vẫn giữ chỗ.

### Rủi ro và Cách giảm thiểu

- Lỗi ở ca biên do logic phức tạp → test theo bảng tình huống, giữ thuật toán greedy đơn giản.
- Giả định về đơn đang chiếu dở chưa đúng thực tế → hỏi đối tác ở buổi gặp tuần 1–2.
- Giải thích AI sai số liệu → validator + luôn hiển thị bảng số liệu bên cạnh.

## Task con & trạng thái

| Task | Nội dung | Sprint | Dự kiến (giờ) | Owner | Trạng thái |
|---|---|---|---|---|---|
| T-031 | API & form mô phỏng sự cố | 4 | 5 | — | Chờ review |
| T-032 | Phát hiện đơn chồng lấn khung dừng | 4 | 6 | — | Chờ review |
| T-033 | Tái lập lịch theo ưu tiên + kiểm tra line thay thế | 4 | 14 | — | Chờ review |
| T-034 | Scheduler Agent giải thích phương án | 4 | 5 | — | Chờ review |
| T-035 | Màn hình so sánh trước/sau sự cố | 4 | 8 | — | Chờ review |
| T-058 | Dồn lịch (compaction) sau sự cố | 4 | 4 | — | Chờ review |

## Nhật ký

- 23/09/2026: Tạo từ Đặc tả #4.
- 25/09/2026: Chuyển sang lộ trình 6 tuần (6 sprint); cập nhật sprint của task con và timeline.
- 01/10/2026 (T-031): bảng `incidents`, `incident_affected_orders`, `plan_versions.incident_id` (migration 0006); `POST /api/incidents`, `GET /api/incidents/{id}` + audit `INCIDENT_DECLARED`; contract §4 bổ sung `IncidentOut` / `AffectedOrder`. Chốt: trùng khung dừng với sự cố OPEN cùng line → 409; `est_downtime_min` 0–10080; seed `INC-A-01` không tự khai báo khi reset (để demo xếp lịch xong rồi mới cho line dừng), reset xóa sự cố cũ. **Còn:** form "Khai báo sự cố" trên frontend.
- 01/10/2026 (T-032): `find_affected` (src/modules/orchestration/incidents.py) quét slot version ACTIVE + slot đề xuất chờ duyệt, chồng lấn khung dừng của **mọi** sự cố chưa kết thúc (giờ hồi phục thực tế nếu đã resolve) → xử lý được cả khi 2 line cùng dừng. Bỏ qua đơn đã chiếu xong (COMPLETED_IRRADIATION trở đi); đơn đang chiếu dở vẫn tính (giả định chạy lại từ đầu). API trả danh sách này cùng phương án ở T-033 (`AffectedOrder` cần cả slot mới).
- 01/10/2026 (T-033): `reschedule` (src/modules/scheduling/incident.py) + `replan_incident`, `resolve_incident` (src/modules/orchestration/incidents.py); `POST /api/incidents` trả phương án, thêm `POST /api/incidents/{id}/resolve`. Chốt:
  - Phương án sự cố **luôn** PENDING_APPROVAL (bước 10), kể cả khi chỉ có đơn sang line còn lại kịp giờ — lịch ACTIVE không đổi tới khi duyệt.
  - Mỗi đơn chọn line kết thúc sớm nhất giữa line còn lại và line sự cố sau hồi phục (khung dừng = slot bận). `change_type`: LINE_ASSIGNMENT (không xong muộn hơn) · INCIDENT_DELAY · PRIORITY_OVERRIDE (đơn bị đẩy).
  - Priority override mở rộng từ "đơn Thường trên line thay thế" thành **mọi đơn ưu tiên thấp hơn chưa bắt đầu**, chỉ khi nhờ đó đơn cao hơn xong sớm hơn — cần để đạt tiêu chí "không đơn ưu tiên cao trễ trong khi đơn thấp hơn giữ chỗ" (seed: VIP SEED-02 bị trễ 525 phút nếu không được đẩy đơn Khẩn SEED-03). Contract §4 đã cập nhật.
  - Sự cố mới / resolve lệch giờ → phương án sự cố đang chờ duyệt SUPERSEDED, tính lại cho mọi khung dừng chưa kết thúc (ADR-0005). Đề xuất xếp lịch chờ duyệt rơi vào khung dừng → gộp vào phương án sự cố, version cũ SUPERSEDED.
  - Xếp lịch đơn mới (T-028) coi khung dừng chưa kết thúc là bận; slot giữ chỗ lấy mọi dòng thay đổi của version chờ duyệt (phương án sự cố có cả thay đổi không cần duyệt).
  - `explanation` + `reason` từng đơn sinh deterministic; T-034 thay bằng Scheduler Agent + validator.
  - **Câu hỏi mở (T-040/T-042):** (1) bảng chuyển chưa có WAITING_ARRIVAL/READY_FOR_IRRADIATION/IN_IRRADIATION → LINE_INCIDENT nên đơn ở các trạng thái này được dời slot nhưng giữ trạng thái; (2) duyệt phương án cần LINE_INCIDENT/SLA_RISK → SCHEDULED; (3) đơn đã LINE_INCIDENT nhưng không còn bị ảnh hưởng sau khi tính lại (hồi phục sớm) giữ nguyên trạng thái.
  - **Lưu ý demo:** `now` là giờ thật — kịch bản INC-A-01 (09:00–12:00 hôm nay) chỉ có đơn bị ảnh hưởng nếu khai báo trước 12:00 giờ địa phương; test cố định đồng hồ 07:30 cho kết quả giống nhau sau mỗi lần reset.
- 02/10/2026 (T-031): form "Khai báo sự cố" (frontend/src/components/IncidentForm.tsx) trên trang Điều phối `/planner`: line, thời điểm bắt đầu (giờ VN), thời gian dừng giờ + phút, ghi chú; xem trước khung dừng; kiểm tra phía client khớp backend (0–10080 phút, ghi chú ≤ 500). Sau khai báo hiển thị tóm tắt phương án (bảng đơn bị ảnh hưởng cũ → mới, kịp / trễ, giải thích) + link mở phương án trên timeline. Màn Trước / Sau đầy đủ và nút "Gửi duyệt" để T-035; form resolve sự cố chưa có (chưa có task UI). Mục "Sự cố line" ở sidebar chuyển sang chờ T-035.
- 02/10/2026 (T-034): Scheduler Agent (src/agents/scheduler_agent.py) viết lại giải thích phương án từ dữ liệu deterministic (khung dừng, lịch cũ → mới, lý do, kịp / trễ bao nhiêu phút); `check_explanation` đối chiếu mọi giờ / ngày / số phút, cặp "Line X HH:MM" phải là mốc slot hoặc khung dừng trên đúng line, phải nhắc đủ đơn, cấm nói "đã duyệt" và nhắc liều / an toàn — vi phạm, LLM lỗi hoặc tắt (`FEATURE_AI_EXPLANATION`, thiếu key) → bản deterministic. Chốt:
  - Endpoint riêng `POST /api/incidents/{id}/explanation` (chỉ đọc, VIEW_BOARD) thay vì gọi LLM trong `POST /api/incidents` → phương án vẫn trả ngay (< 10 giây), GET không gọi LLM mỗi lần; không lưu kết quả (tránh migration chồng với 0009 của T-041). Không ghi audit vì không đổi trạng thái.
  - Giải thích là 1 đoạn cho cả phương án (đủ từng đơn), không tách lý do từng đơn — bảng số liệu luôn hiện cạnh bên (T-035).
  - Sửa `incident_explanation`: phương án trải nhiều ngày → mọi mốc kèm ngày (trước đây đơn dời sang hôm sau hiện "10:45–17:15" như thể chồng khung dừng).
- 02/10/2026 (T-035): màn `/incidents` (danh sách, Điều phối khai báo tại chỗ rồi sang so sánh) và `/incidents/[id]` (so sánh trước / sau); thêm `GET /api/incidents` (mọi vai trò) vào contract §4 — mục sidebar "Sự cố line" mở cho mọi vai trò vì người duyệt cần xem phương án. Timeline tách thành `components/LineTimeline.tsx` dùng chung với màn lịch. Chốt:
  - "Trước" = version cha của phương án (lịch ACTIVE lúc tính), "Sau" = phương án đề xuất; chưa có phương án → chỉ lịch ACTIVE. Khung dừng của **mọi** sự cố tô xám gạch chéo (phương án tính cho mọi khung dừng chưa kết thúc); đơn không bị ảnh hưởng hiện mờ; chọn ngày theo các ngày có khung dừng / slot cũ / slot mới.
  - 2 timeline xếp **trên / dưới** cùng trục giờ thay vì cạnh nhau: trục 24h chia đôi bề ngang thì khối không đọc được giờ.
  - Không có nút "Gửi duyệt": phương án sự cố tự PENDING_APPROVAL khi tạo (T-033) → hiện trạng thái "Đã gửi duyệt"; duyệt / từ chối ở T-042. Phương án SUPERSEDED (sự cố sau tính gộp) → báo đã bị thay.
  - Giải thích hiện ngay bản deterministic rồi thay bằng bản Scheduler Agent (POST …/explanation) nếu qua validator; nhãn nguồn "Scheduler Agent (AI)" / "Bản tự động theo luật".
- 02/10/2026 (T-058): yêu cầu "plan sau sự cố không để line nghỉ" → ADR-0011 (Proposed): sau `reschedule`, `compact` dồn trái mọi đơn chưa bắt đầu (SCHEDULED/LINE_INCIDENT, không có đề xuất chờ duyệt), chỉ nhận khi xong sớm hơn; đơn không bị ảnh hưởng được kéo sớm → `PULLED_FORWARD`, giữ trạng thái. Không cần migration (VARCHAR(14) vừa giá trị mới). **Chờ chốt:** có phải báo khách khi đơn xong sớm hơn hẹn không.
