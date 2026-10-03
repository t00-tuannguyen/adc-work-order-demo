# ADC-006: Phê duyệt HITL, quản lý phiên bản kế hoạch và audit log (Orchestrator)

> Nguồn: sheet *Đặc tả tính năng* — Đặc tả #6 trong `team_project_management_template.xlsx`.

| Trường | Giá trị |
|---|---|
| Đặc tả | #6 |
| User Story | US-012, US-015 (FR 12) |
| Functional Requirement (PRD) | FR 12 |
| Ưu tiên | P0 |
| Sprint | 2, 3, 4 |
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

AI đề xuất những thay đổi ảnh hưởng khách (đổi giờ trả, hoãn đơn, đổi ưu tiên, nhận đơn khi đang cảnh báo). Nếu tự kích hoạt sẽ rủi ro về cam kết và trách nhiệm. Cần một cổng duyệt duy nhất và lịch sử đầy đủ để truy vết.

### Người dùng mục tiêu

- Quản lý vận hành / Kinh doanh: người duyệt.
- Điều phối: người đề xuất.
- Mentor, giám khảo: xem truy vết khi demo.

### Mục tiêu kỳ vọng

- 0 thay đổi ảnh hưởng khách được kích hoạt khi chưa duyệt (FR 12).
- 100% lệnh có lịch sử trạng thái.
- Mọi plan version có người tạo, người duyệt, thời điểm; so sánh trước/sau được.

### Phương án thay thế đã xem xét

- Duyệt từng đơn riêng lẻ: chi tiết nhưng rối khi một sự cố ảnh hưởng nhiều đơn.

**→ Chọn:** duyệt theo cả plan version (duyệt/từ chối cả version, bắt buộc ghi lý do khi từ chối). Từ chối từng dòng thay đổi là "Nên có".

## 2. Thiết kế (Design)

### Kiến trúc hệ thống

Orchestrator là nơi duy nhất ghi trạng thái: nhận sự kiện (ticket mới, sự cố, cập nhật vận hành) → gọi Order / Scheduler / Risk Agent → nhận plan version đề xuất → áp bảng Human Approval Rules của PRD:

- Có thay đổi thuộc 4 loại cần duyệt → version ở PENDING_APPROVAL.
- Ngược lại → active ngay.

Chỉ 1 version active tại một thời điểm; duyệt version mới thì version cũ thành SUPERSEDED.
State machine: nhóm Normal (DRAFT → FEASIBILITY_CHECK → PENDING_APPROVAL → SCHEDULED → WAITING_ARRIVAL → READY_FOR_IRRADIATION → IN_IRRADIATION → COMPLETED_IRRADIATION → READY_FOR_RETURN → RETURNED → CLOSED) và nhóm Exception (LINE_INCIDENT, SLA_RISK, RESCHEDULE_REQUIRED, ESCALATED_TO_BUSINESS, BLOCK_NEW_ORDER). Bảng chuyển trạng thái hợp lệ định nghĩa trong code; chuyển sai bị từ chối.

### Thiết kế giao diện (UI/UX)

- Trang "Chờ duyệt": mỗi plan version một thẻ gồm nguồn (sự cố / đơn mới), số đơn bị ảnh hưởng, danh sách thay đổi có nhãn loại (đổi giờ trả / hoãn / đổi ưu tiên / nhận đơn khi cảnh báo), diff lịch trước/sau, giải thích AI; nút Duyệt / Từ chối.
- Tab "Lịch sử" trong chi tiết lệnh: timeline trạng thái — ai, khi nào, vì sao.

### Thiết kế API

- GET /api/plan-versions?status=pending
- GET /api/plan-versions/{id}/diff
- POST /api/plan-versions/{id}/approve {comment}
- POST /api/plan-versions/{id}/reject {reason}
- GET /api/work-orders/{id}/history
- Duyệt version đã cũ (đã có version mới hơn) → 409.

### Mô hình dữ liệu

- plan_versions(id, parent_version_id, trigger, status ENUM[PROPOSED, PENDING_APPROVAL, ACTIVE, REJECTED, SUPERSEDED], requires_approval, created_by, approved_by, approved_at, comment)
- plan_changes(id, plan_version_id FK, work_order_id FK, change_type, old_value JSON, new_value JSON, needs_approval)
- state_history(id, work_order_id FK, from_state, to_state, actor_type ENUM[USER, AGENT, SYSTEM], actor_id, reason, plan_version_id, at)
- audit_log(id, actor, action, payload JSON, at) — chỉ ghi thêm

Index: state_history(work_order_id, at).

### Thiết kế AI/ML

Orchestrator là code điều phối, không phải LLM tự do: các agent được gọi như tool với input/output schema cố định. LLM không có quyền gọi hàm approve. Có thể dùng LLM tóm tắt diff giúp người duyệt đọc nhanh.

### Trường hợp đặc biệt và Xử lý lỗi

- Có sự cố mới khi version cũ đang chờ duyệt → version cũ SUPERSEDED, tạo version mới từ version active.
- Bị từ chối → giữ version active; đơn liên quan chuyển RESCHEDULE_REQUIRED để điều phối xử lý.
- Hai người duyệt cùng lúc → khóa lạc quan, người sau nhận 409.
- Hoàn tác: MVP không rollback tự động, tạo version mới.

### Bảo mật và Quyền riêng tư

- Chỉ vai trò Quản lý / Kinh doanh có quyền duyệt; người đề xuất không tự duyệt (Nên có).
- Audit log chỉ ghi thêm, không sửa/xóa.
- Trước khi có ADC-008 (Sprint 5), dùng tài khoản demo theo vai trò; sau đó dùng người dùng thật từ Google OAuth.

## 3. Kế hoạch (Plan)

### Các bước thực hiện

1. State machine + bảng chuyển hợp lệ (6h)
2. State history và audit log (5h)
3. Plan version + diff (8h)
4. Luật cần duyệt + API duyệt (6h)
5. UI Chờ duyệt và Lịch sử (8h)
6. Orchestrator gọi agent theo luồng (6h)

### Công việc con (liên kết Backlog)

- T-040: State machine work order
- T-041: Audit log & lịch sử trạng thái
- T-042: Luồng phê duyệt plan version (HITL)
- T-043: Orchestrator điều phối các agent

### Phụ thuộc

- Là nền cho mọi đặc tả khác; cần làm sớm.
- Cần schema work order (T-017).

### Timeline dự kiến

Sprint 2 (state machine, audit log) → Sprint 3 (Orchestrator) → Sprint 4 (luồng duyệt). Tổng dự kiến ~39 giờ. [Điền ngày cụ thể]

### Kế hoạch kiểm thử

- Mỗi loại trong 4 loại thay đổi → version PENDING_APPROVAL, lịch active không đổi.
- Gán line không ảnh hưởng SLA → active ngay, không cần duyệt.
- Chuyển trạng thái không hợp lệ → bị từ chối.
- Mọi lệnh trong seed có lịch sử đầy đủ từ DRAFT.
- Duyệt version cũ → 409.

### Kế hoạch triển khai

State machine và audit log bật từ Sprint 2 (các tính năng sau dựa vào); Orchestrator ở Sprint 3; luồng duyệt bật ở Sprint 4.

### Tiêu chí thành công

- FR 12 đạt.
- Theo Metrics PRD: 0 thay đổi ảnh hưởng khách không qua duyệt; 100% lệnh có lịch sử trạng thái.

### Rủi ro và Cách giảm thiểu

- Là xương sống, chậm sẽ kéo cả dự án → làm từ tuần 2, giao cho backend chính.
- Quá nhiều trạng thái gây rối giao diện → Kanban gộp theo nhóm trạng thái.
- Người duyệt khó hiểu diff → nhãn loại thay đổi + giải thích AI.

## Task con & trạng thái

| Task | Nội dung | Sprint | Dự kiến (giờ) | Owner | Trạng thái |
|---|---|---|---|---|---|
| T-040 | State machine work order | 2 | 6 | — | Chờ review |
| T-041 | Audit log & lịch sử trạng thái | 2 | 5 | — | Chờ review |
| T-042 | Luồng phê duyệt plan version (HITL) | 4 | 22 | — | Chờ review |
| T-043 | Orchestrator điều phối các agent | 3 | 6 | — | Chờ review |

## Nhật ký

- 23/09/2026: Tạo từ Đặc tả #6.
- 25/09/2026: Chuyển sang lộ trình 6 tuần (6 sprint); cập nhật sprint của task con và timeline.
- 30/09/2026: T-053 (ADC-008) tạo trước bảng `audit_log(id, actor_id, action, payload, at)` + `record()` trong `src/modules/orchestration/audit.py` — chỉ ghi thêm (chặn update/delete ở ORM), `actor_id` bắt buộc là user thật. T-041 dùng lại, bổ sung state_history và API xem audit.
- 01/10/2026: T-028 (ADC-003) tạo trước bảng `plan_versions` (id = số version, + `created_at`) và `plan_changes` theo mô hình dữ liệu ở trên, cùng `schedule_work_order()` trong `src/modules/orchestration/planning.py` (LINE_ASSIGNMENT → ACTIVE, version cũ SUPERSEDED; RETURN_TIME_CHANGE → PENDING_APPROVAL). T-042 thêm duyệt/từ chối, diff; chưa có cột `is_simulation` (BR-11, ADC-007).
- 02/10/2026: T-040 chốt chuyển ngoại lệ (cập nhật `specs/domains.md` §5): duyệt phương án LINE_INCIDENT / SLA_RISK / ESCALATED_TO_BUSINESS → SCHEDULED; từ chối PENDING_APPROVAL / LINE_INCIDENT / SLA_RISK / ESCALATED_TO_BUSINESS → RESCHEDULE_REQUIRED; RESCHEDULE_REQUIRED → SCHEDULED / PENDING_APPROVAL khi Điều phối xếp tay lại (PUT schedule). Override BLOCK_NEW_ORDER chưa có API → để task riêng. T-043: graph Orchestrator (`src/agents/graph.py`) + tự xếp lịch khi tạo ticket đã làm ở commit gắn nhãn T-043 (90ee36a).
- 02/10/2026: T-041 thêm bảng `state_history` (migration 0009) ghi trong `transition_work_order` cùng commit với audit; dòng đầu lúc tạo lệnh (`from_state` rỗng → DRAFT). `actor_id` luôn là người dùng thật đã kích hoạt; `actor_type` USER (bấm tay) / SYSTEM (tự xếp lịch, phương án sự cố, escalation, seed) / AGENT (Order Agent tạo lệnh). API `GET /api/work-orders/{id}/history` (shape ghi vào contract §6). Xóa lệnh nháp xóa luôn dòng lịch sử (audit `WORK_ORDER_DELETED` giữ dấu vết). Chưa làm API đọc `audit_log` — contract chưa có.
- 02/10/2026: T-042 làm `src/modules/orchestration/review.py` + `src/api/approval.py` (diff / approve / reject, shape ghi vào contract §6), trang `/approvals` và lịch sử trạng thái trên thẻ Kanban + màn chi tiết lệnh. Duyệt version mà lịch ACTIVE đã đổi → gộp thay đổi lên lịch hiện tại, trùng giờ → 409 (nhóm chốt). `approved_by/approved_at/comment` lưu người quyết định cả khi từ chối (lý do ở `comment`). Chưa làm: "người đề xuất không tự duyệt" (Nên có — Điều phối đề xuất nhưng không có quyền duyệt, đề xuất tự động do hệ thống tạo), LLM tóm tắt diff (đang hiện lý do deterministic của từng thay đổi), từ chối từng dòng thay đổi (Nên có).
- 02/10/2026: T-042 (fix) — "so sánh lịch trước / sau" trên thẻ Chờ duyệt mở màn `/approvals/[id]`: 2 timeline cùng trục giờ (lịch nền `base_version_id` ↔ version đề xuất, đơn thay đổi làm nổi, khung dừng sự cố), chọn ngày theo slot cũ / mới, kèm thẻ thay đổi + Duyệt / Từ chối (tách `components/PlanVersionCard.tsx`). Không đổi API.
