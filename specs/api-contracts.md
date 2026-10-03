# API Contracts

> Tổng hợp từ mục *Thiết kế API* của 8 đặc tả. Đổi contract → sửa file này **trước**, rồi mới sửa code.
> Chi tiết ngữ cảnh từng endpoint: xem file đặc tả tương ứng trong `tasks/`.

## Quy ước chung

- Base: `/api` cho dữ liệu, `/auth` cho xác thực.
- JSON, tên trường `snake_case` (khớp mô hình dữ liệu).
- Thời gian lưu UTC (ISO 8601), hiển thị theo giờ địa phương.
- Xác thực bằng cookie phiên HttpOnly (ADC-008). Chưa đăng nhập → `401`; tài khoản PENDING/DISABLED hoặc sai vai trò → `403`.
- Khóa lạc quan theo plan version: thao tác trên version đã cũ → `409`.

| HTTP | Khi nào |
|---|---|
| 202 | Nhận job bất đồng bộ (upload PDF) |
| 401 | Chưa đăng nhập |
| 403 | Sai vai trò / tài khoản chưa được cấp quyền |
| 409 | Xung đột version (duyệt version cũ, 2 người sửa cùng lúc) |
| 413 | File > 10 MB |
| 415 | Không phải PDF |
| 422 | Input không hợp lệ / thiếu trường / PDF có mật khẩu, hỏng, > 20 trang |

Mã lỗi ứng dụng (`error_code`): `OCR_FAILED`, `DOMAIN_NOT_ALLOWED`, `EMAIL_NOT_VERIFIED`, `CANCELLED`, `STATE_MISMATCH`, `ACCOUNT_DISABLED`, `AUTH_FAILED` (đổi code hoặc xác minh ID token Google thất bại — ADC-008).

---

## 1. Intake — ADC-001

| Method | Path | Request | Response |
|---|---|---|---|
| POST | `/api/tickets/upload` | multipart: `file`, `channel`, `received_at` | `202 {job_id, file_id}` |
| GET | `/api/ingest-jobs/{job_id}` | — | `{status, step, progress, work_orders[{id, review_status, state}], error_code}` |
| GET | `/api/files/{file_id}` | — | file PDF gốc (`application/pdf`, inline) để nhúng trình xem PDF của trình duyệt — không highlight vùng nguồn (chốt 30/09/2026, T-021); trang + đoạn nguồn hiện dạng chữ cạnh từng trường |
| GET | `/api/work-orders/{id}/intake` | — | `WorkOrderReview` (dưới bảng) — dữ liệu màn xác nhận ticket |
| POST | `/api/tickets` | `{raw_text, source: TEXT\|MANUAL, received_at}` | `201 {work_orders[{id, review_status, state}]}`. `TEXT`: tab "Dán nội dung" — Order Agent trích xuất đồng bộ, cùng cổng như PDF; `MANUAL`: tạo 1 lệnh DRAFT trống để nhập tay (`raw_text` bỏ qua). Đơn qua cổng tự vào FEASIBILITY_CHECK (TEXT / PDF) cũng được tự xếp lịch như `submit`. Order Agent lỗi → `502`; chưa cấu hình Order Agent (key của provider theo `ORDER_AGENT_PROVIDER`, ADR-0013) → `503` |
| PATCH | `/api/work-orders/{id}` | `{fields}` | chỉ đơn DRAFT (khác → `409`); trường gửi lên → `MANUAL`, chạy lại validator + cổng tin cậy; trả `WorkOrderReview` (dưới bảng) |
| DELETE | `/api/work-orders/{id}` | — | `204` · xóa lệnh nháp nhập nhầm / ticket rác · chỉ đơn DRAFT (khác → `409`, đơn đã qua tiếp nhận không xóa) · xóa lệnh + ticket + `field_extractions` / `clarification_requests` / `intake_warnings`, giữ file PDF gốc (có thể chứa ticket khác) · ghi audit `WORK_ORDER_DELETED` kèm bản chụp 8 trường (T-055) |
| POST | `/api/work-orders/{id}/submit` | — | chỉ cho đơn DRAFT (thiếu trường / `NEEDS_REVIEW`; khác → `409`) → FEASIBILITY_CHECK rồi hệ thống tự xếp lịch (như `POST /api/work-orders/{id}/schedule` §3, actor = người submit): OK → SCHEDULED, WARN → PENDING_APPROVAL, BLOCK → BLOCK_NEW_ORDER, không xếp được (thiếu ước tính / không có khe / xung đột version) → giữ FEASIBILITY_CHECK cho Điều phối; trả `WorkOrderReview`; hoặc `422 {detail: {errors[{field, code}], unconfirmed_fields[]}}` |
| GET | `/api/intake-warnings?status=open\|acknowledged` | — | hàng đợi cảnh báo tiếp nhận `[{id, work_order_id, field, code, created_at}]` |
| POST | `/api/intake-warnings/{id}/ack` | `{note}` | đánh dấu người đã xem, ghi audit; đã xem rồi → `409` |

`step`: `UPLOADED | READING | DETECTING | EXTRACTING | DONE | FAILED`

`WorkOrderReview`: `{id, state, review_status, fields{8 trường, quy cách tách pkg_length_cm/pkg_width_cm/pkg_height_cm}, boundary_uncertain, errors[{field, code}], unconfirmed_fields[], can_submit, extractions[{field, value, source_kind, page, bbox, snippet, confidence}], clarifications[{field, question, status}], warnings[{id, field, code, status}], source{type: PDF\|TEXT\|MANUAL, file_id, file_name, page_count, page_from, page_to, ocr_used, channel, received_at, raw_text}, estimate{duration_min, breakdown{setup, weight_load, volume_load, dose_load, buffer}, config_version} \| null, estimate_error}` — `bbox` = `[x0, y0, x1, y1]` tỷ lệ 0–1 theo trang. `code` lỗi: `MISSING | NOT_POSITIVE | RETURN_NOT_AFTER_ARRIVAL | DOSE_OUT_OF_RANGE` (liều lấy theo giá trị quét trong ticket, chỉ kiểm tra 0 < liều ≤ 25 kGy, không đối chiếu danh mục `dose_factor`).

`estimate` (ADC-002): tính khi lệnh vào FEASIBILITY_CHECK, nhóm sản phẩm theo bảng từ khóa `product_groups` của `throughput.yaml`; `null` khi còn DRAFT hoặc không tính được — lúc đó `estimate_error` nêu lý do (nhóm sản phẩm không xác định, hệ số chưa cấu hình — BR-02).

`review_status` (ADR-0007): `AUTO_ACCEPTED` (tự vào FEASIBILITY_CHECK) · `ACCEPTED_WITH_WARNINGS` (tự vào FEASIBILITY_CHECK + có cảnh báo) · `NEEDS_REVIEW` (giữ DRAFT, chờ người xác nhận) · `NEEDS_CLARIFICATION` (thiếu/sai trường).
Mã cờ: `LOW_CONFIDENCE`, `BOUNDARY_UNCERTAIN` (→ `NEEDS_REVIEW`); `AMBIGUOUS_OCR`, `INFERRED_VALUE`, `DEFAULT_VALUE`, `POSSIBLE_DUPLICATE` (→ cảnh báo).

Ví dụ output Order Agent cho 1 trường:
```json
{
  "quantity": { "value": 120, "source_kind": "VERBATIM", "page": 1, "snippet": "Số lượng: 120 thùng", "confidence": 0.97 },
  "required_dose_kgy": { "value": null, "source_kind": null, "page": null, "snippet": null, "confidence": null }
}
```
`source_kind`: `VERBATIM | INFERRED | CONVERTED | OCR_LOW | MANUAL | DEFAULT`
`confidence`: độ tin cậy của trường (0–1) — tạm thời do Gemini tự chấm (ADR-0010), chờ hiệu chỉnh bằng benchmark T-022; `null` = nhập tay.

## 2. Estimation — ADC-002

| Method | Path | Request | Response |
|---|---|---|---|
| POST | `/api/estimate` | các trường work order | `{duration_min, breakdown{setup, weight_load, volume_load, dose_load, buffer}, config_version}` |
| GET | `/api/config/throughput` | — | tham số hiện hành |
| POST | `/api/demo/reset` | — | xóa lịch (plan version, slot), sự cố và dữ liệu tiếp nhận, nạp lại `src/seed/orders.json` vào ngày hôm nay (giờ địa phương) → `{demo_date, work_orders[{id, ref, state, estimated_duration_min}], incidents[{ref, line, start_at, est_downtime_min, note}]}`; ghi audit `DEMO_RESET`. Tắt (`DEMO_RESET_ENABLED=false` hoặc `APP_ENV=production`) → `404` |

## 3. Scheduling — ADC-003

| Method | Path | Request | Response |
|---|---|---|---|
| POST | `/api/work-orders/{id}/schedule` | — | `{line, start, end, plan_version, sla_ok, plan_status, reason, risk: RiskCheck}` · chỉ đơn FEASIBILITY_CHECK (khác → `409`) · chưa có ước tính hoặc đơn chỉ chạy ca ngày mà dài hơn cả ca (BR-14) → `422` · version ACTIVE đổi trong lúc xếp → `409` · rủi ro BLOCK (§5) → `409 {detail: {error_code: NEW_ORDER_BLOCKED, message, risk: RiskCheck}}`, đơn → BLOCK_NEW_ORDER, không tạo plan version |
| PUT | `/api/work-orders/{id}/schedule` | `{line: A\|B, start}` | Điều phối xếp / sửa lịch thủ công (BR-15) → `{line, start, end, plan_version, sla_ok, plan_status, reason}` · chỉ đơn FEASIBILITY_CHECK / RESCHEDULE_REQUIRED / SCHEDULED / WAITING_ARRIVAL, chưa có đề xuất chờ duyệt (khác → `409`) · trùng đơn khác / slot chờ duyệt / khung dừng sự cố trên line → `409` (nêu đơn đang chiếm) · `start` trong quá khứ, trước giờ hàng đến, vi phạm ca (BR-14) hoặc chưa có ước tính → `422` · kịp giờ trả → version `ACTIVE` (`LINE_ASSIGNMENT`), đơn FEASIBILITY_CHECK / RESCHEDULE_REQUIRED → SCHEDULED; trễ → version `PENDING_APPROVAL` (`RETURN_TIME_CHANGE`), lịch ACTIVE giữ nguyên, đơn FEASIBILITY_CHECK / RESCHEDULE_REQUIRED → PENDING_APPROVAL, đơn đã có lịch giữ trạng thái tới khi duyệt · plan version `trigger: MANUAL` |
| GET | `/api/schedule?version=current\|{n}&date=` | — | `{plan_version, date, lines{A[ScheduleSlot], B[ScheduleSlot]}}` · `plan_version` null khi chưa có version ACTIVE · `{n}` không tồn tại → `404` |
| GET | `/api/work-orders?state=` | — | dữ liệu Kanban `[WorkOrderCard]`; `state` lặp được (`?state=A&state=B`), bỏ trống = tất cả |
| PATCH | `/api/work-orders/{id}/state` | `{to_state, reason}` | trả `WorkOrderCard` · chỉ trạng thái vận hành (WAITING_ARRIVAL → … → CLOSED; khác → `422`) · sai bảng chuyển → `409` |
| GET | `/api/plan-versions?status=` | — | bộ chọn version trên lịch: `[PlanVersionOut]` mới nhất trước; `status` = giá trị `PlanVersionStatus` hoặc `pending` (= PENDING_APPROVAL). Duyệt / diff ở §6 |

Xếp lịch (ADR-0004, T-028, T-036): mỗi lần xếp chạy kiểm tra rủi ro đơn mới (§5) rồi tạo 1 plan version mới = slot của version ACTIVE + slot mới. `OK` → thay đổi `LINE_ASSIGNMENT`, version ACTIVE ngay (version cũ SUPERSEDED), đơn → SCHEDULED. `WARN` → thay đổi `ACCEPT_DURING_WARNING` cho đơn mới + `PRIORITY_OVERRIDE` cho từng đơn bị đẩy lùi, version PENDING_APPROVAL (lịch ACTIVE không đổi), đơn mới → PENDING_APPROVAL, đơn bị đẩy giữ trạng thái — chờ duyệt ở §6. `BLOCK` → `409` như bảng trên. Slot đề xuất đang chờ duyệt được giữ chỗ: lần xếp sau không đặt đơn khác chồng lên.

`plan_status`: trạng thái version vừa tạo (`ACTIVE` | `PENDING_APPROVAL`). `reason`: lý do xếp sinh deterministic từ kết quả, giờ theo `LOCAL_UTC_OFFSET` (mặc định `+07:00`), vd `"Line B 09:00–10:30. Line A chỉ trống từ 14:00 → chọn Line B. Kịp giờ trả 16:00."`.

`date` (`YYYY-MM-DD`, ngày địa phương theo `LOCAL_UTC_OFFSET`): chỉ trả slot giao với ngày đó; bỏ trống = mọi slot của version.

`PlanVersionOut`: `{id, status, parent_version_id, trigger: NEW_ORDER|INCIDENT|MANUAL, requires_approval, created_by, created_at, slot_count}` — `id` chính là số version `{n}`.

`ScheduleSlot`: `{work_order_id, product_name, priority, state, line, start, end, requested_return, sla_ok, reason}`.

`WorkOrderCard`: `{id, product_name, priority, state, review_status, expected_arrival, requested_return, estimated_duration_min, slot{line, start, end, sla_ok, plan_version, plan_status} | null}` — `slot` lấy từ version mới nhất đang ACTIVE hoặc PENDING_APPROVAL có chứa đơn.

## 4. Incident — ADC-004

| Method | Path | Request | Response |
|---|---|---|---|
| POST | `/api/incidents` | `{line, start_at, est_downtime_min, note}` | `201 IncidentOut` · chỉ PLANNER (DECLARE_INCIDENT) · `est_downtime_min` 0–10080 · `note` ≤ 500 · trùng khung dừng với sự cố OPEN khác trên cùng line → `409` |
| GET | `/api/incidents` | — | `[IncidentOut]` mọi sự cố, bắt đầu muộn nhất trước · mọi vai trò (VIEW_BOARD) — màn so sánh trước / sau (T-035) |
| GET | `/api/incidents/{id}` | — | `IncidentOut` · mọi vai trò (VIEW_BOARD) · không có → `404` |
| POST | `/api/incidents/{id}/explanation` | — | `{explanation, source: LLM\|TEMPLATE, plan_version_id}` (gọi LLM) · mọi vai trò (VIEW_BOARD) · chỉ đọc: không đổi phương án / trạng thái · không có → `404` · LLM lỗi / tắt (`FEATURE_AI_EXPLANATION=false`, thiếu `OPENAI_API_KEY`) / câu giải thích sai giờ, line, số phút, thiếu đơn hoặc nói đã duyệt → bản deterministic (`TEMPLATE`) |
| POST | `/api/incidents/{id}/resolve` | `{actual_end}` | `IncidentOut` · chỉ PLANNER · `actual_end` < `start_at` → `422` · đã RESOLVED → `409` · `actual_end` khác giờ hồi phục dự kiến → tính lại, tạo plan version đề xuất mới |

`IncidentOut`: `{incident_id, line, start_at, est_downtime_min, end_at, actual_end_at, status: OPEN|RESOLVED, note, created_by, created_at, affected_orders[AffectedOrder], proposed_plan_version, sla_risks[], explanation}`.
- `end_at` = `actual_end_at` nếu đã hồi phục, ngược lại `start_at + est_downtime_min`.
- `proposed_plan_version`: `PlanVersionOut` (§3) của phương án mới nhất do sự cố này tạo (`trigger=INCIDENT`, luôn `PENDING_APPROVAL` khi tạo — lịch ACTIVE không đổi tới khi duyệt ở §6) · `null` khi không có đơn bị ảnh hưởng.
- `sla_risks`: id các đơn có giờ xong mới > giờ trả (→ SLA_RISK).
- `explanation`: tóm tắt phương án sinh deterministic từ kết quả (T-033), trả ngay; mốc giờ kèm ngày khi phương án trải nhiều ngày. Bản viết lại bằng Scheduler Agent lấy qua `POST /api/incidents/{id}/explanation` (T-034) để phương án không phải chờ LLM.

`AffectedOrder`: `{work_order_id, product_name, priority, state, outcome: MOVED_ALT_LINE|DELAYED|UNCHANGED|PULLED_FORWARD, change_type, old{line, start, end}, new{line, start, end}, requested_return, sla_ok, reason}`.
- Đơn bị ảnh hưởng = slot của version ACTIVE (và slot đề xuất đang chờ duyệt) trên line sự cố chồng lấn `[start_at, end_at)`, trừ đơn đã chiếu xong. Đơn đang chiếu dở chạy lại từ đầu (giả định chờ đối tác xác nhận).
- `change_type`: `LINE_ASSIGNMENT` (sang line còn lại, không xong muộn hơn) · `INCIDENT_DELAY` (xong muộn hơn lịch cũ) · `PRIORITY_OVERRIDE` (đơn chưa bắt đầu bị đẩy lùi để nhường đơn ưu tiên cao hơn đang trễ — chỉ khi nhờ đó đơn kia xong sớm hơn).
- `PULLED_FORWARD` (T-058, ADR-0011): đơn không bị ảnh hưởng, chưa bắt đầu, được kéo sớm lấp khe trống sau khi tái lập lịch — chỉ khi xong sớm hơn; giữ trạng thái, `change_type = LINE_ASSIGNMENT`.
- Thứ tự xử lý BR-05: VIP → Khẩn → Thường, cùng mức giờ trả sớm hơn trước. Mỗi đơn chọn line kết thúc sớm nhất giữa line còn lại và line sự cố sau khi hồi phục.
- Đơn SCHEDULED bị ảnh hưởng → LINE_INCIDENT; trễ giờ trả → SLA_RISK → ESCALATED_TO_BUSINESS kèm escalation (§5, T-037). Đơn ở trạng thái vận hành (WAITING_ARRIVAL…IN_IRRADIATION) vẫn được dời slot nhưng giữ trạng thái (T-040 chốt bảng chuyển).

Sự cố mới / tính lại khi phương án sự cố trước đang chờ duyệt → version chờ duyệt đó SUPERSEDED (ADR-0005), phương án mới tính cho mọi khung dừng chưa kết thúc. Trong lúc có sự cố chưa kết thúc, `POST /api/work-orders/{id}/schedule` (§3) không xếp đơn vào khung dừng.

## 5. Risk & Escalation — ADC-005

| Method | Path | Request | Response |
|---|---|---|---|
| POST | `/api/work-orders/{id}/risk-check` | — | `RiskCheck` · mọi vai trò (VIEW_BOARD) · chỉ mô phỏng: lưu `risk_checks`, không đổi lịch hay trạng thái đơn · chỉ đơn FEASIBILITY_CHECK hoặc BLOCK_NEW_ORDER (khác → `409`) · thiếu ước tính/giờ trả hoặc dài hơn cả ca → `422` |
| GET | `/api/escalations?status=open` | — | hàng đợi escalation `[Escalation]` · mọi vai trò (VIEW_BOARD) · `status`: `open` (= OPEN + DRAFTED) hoặc 1 giá trị `EscalationStatus`, bỏ trống = tất cả · sắp VIP → Khẩn → Thường, rồi trễ nhiều hơn trước |
| POST | `/api/escalations/{id}/draft` | — | `{message_draft, source: LLM\|TEMPLATE}` (gọi LLM) · SALES / OPS_MANAGER (APPROVE_ESCALATION_MESSAGE) · OPEN → DRAFTED, soạn lại khi DRAFTED được · APPROVED/CLOSED → `409` · LLM lỗi / tắt (`FEATURE_AI_MESSAGE_DRAFT=false`, thiếu `OPENAI_API_KEY`) / nháp sai giờ hoặc nhắc liều, an toàn → mẫu soạn sẵn (`TEMPLATE`) để sửa tay |
| POST | `/api/escalations/{id}/approve` | `{final_message}` | `Escalation` · đánh dấu đã duyệt, ghi audit (MVP không gửi email thật) · SALES / OPS_MANAGER · chỉ khi DRAFTED (khác → `409`) · `final_message` rỗng hoặc > 2000 ký tự → `422` · LLM không bao giờ gọi endpoint này |

`RiskCheck`: `{level: OK|WARN|BLOCK, reasons[], earliest_feasible_return}` — luật deterministic BR-07 (T-036), mô phỏng chèn đơn vào lịch ACTIVE + slot đề xuất đang chờ duyệt + khung dừng sự cố chưa kết thúc:
- Xếp vào khe trống sớm nhất (như §3) kịp giờ trả → `OK`.
- Trễ → thử đẩy lùi đơn ưu tiên thấp hơn chưa bắt đầu (SCHEDULED, slot bắt đầu ≥ hiện tại, không có đề xuất đang chờ duyệt); đơn bị đẩy xếp lại theo BR-05 như tái lập lịch sự cố. Nhờ đẩy mà đơn mới kịp → `WARN` (nhận được nhưng cần duyệt; `reasons` nêu từng đơn bị đẩy, trễ hay vẫn kịp). Đơn Thường không đẩy được ai → chỉ `OK` hoặc `BLOCK`.
- Kể cả khi đẩy vẫn trễ → `BLOCK`; Quản lý override kèm lý do (chưa có API — T-040/T-042).
- `earliest_feasible_return`: giờ xong của đơn mới theo phương án `OK`/`WARN`; với `BLOCK` là giờ xong sớm nhất khi xếp vào khe trống (không đẩy đơn nào).
- `reasons[]`: câu chữ sinh deterministic, giờ theo `LOCAL_UTC_OFFSET`.

`Escalation`: `{id, work_order_id, product_name, priority, state, incident_id, delay_min, requested_return, expected_finish, status: OPEN|DRAFTED|APPROVED|CLOSED, draft_message, final_message, approved_by, approved_at, can_close}` (T-037).
- Tạo tự động (BR-06) cho mọi đơn có giờ xong > giờ trả trong phương án mới: phương án sự cố (§4, `incident_id` = sự cố) và đơn bị đẩy lùi khi nhận đơn WARN (`incident_id` null). Đơn SLA_RISK → ESCALATED_TO_BUSINESS; đơn ở trạng thái khác giữ trạng thái. Mỗi đơn tối đa 1 escalation đang mở (OPEN/DRAFTED); phương án sau đổi số phút trễ → cập nhật `delay_min` của mục đó.
- `expected_finish` = `requested_return + delay_min`.
- `can_close`: đang mở nhưng giờ xong theo kế hoạch hiện hành (thay đổi mới nhất của đơn trong version ACTIVE / PENDING_APPROVAL, không có thì slot của version ACTIVE) đã kịp giờ trả, vd sự cố kết thúc sớm hoặc phương án bị từ chối → người xác nhận đóng (chưa có API đóng — chờ chốt).

## 6. Approval, Plan version & Audit — ADC-006

| Method | Path | Request | Response |
|---|---|---|---|
| GET | `/api/plan-versions?status=pending` | — | danh sách chờ duyệt (`[PlanVersionOut]` §3) |
| GET | `/api/plan-versions/{id}/diff` | — | `PlanDiff` (dưới bảng) · mọi vai trò (VIEW_BOARD) · không có version → `404` |
| POST | `/api/plan-versions/{id}/approve` | `{comment}` (≤ 500, tùy chọn) | `PlanVersionOut` · SALES / OPS_MANAGER (APPROVE_PLAN_VERSION) · version → ACTIVE, version ACTIVE cũ → SUPERSEDED (BR-09); đơn có thay đổi đang PENDING_APPROVAL / LINE_INCIDENT / SLA_RISK / ESCALATED_TO_BUSINESS / RESCHEDULE_REQUIRED → SCHEDULED, đơn khác giữ trạng thái · lịch ACTIVE đã đổi kể từ lúc đề xuất → gộp thay đổi của version lên lịch ACTIVE hiện tại, trùng giờ → `409` · version không còn PENDING_APPROVAL (đã duyệt / từ chối / có version mới hơn thay thế) hoặc người khác vừa duyệt → `409` · ghi audit `PLAN_VERSION_APPROVED` |
| POST | `/api/plan-versions/{id}/reject` | `{reason}` (bắt buộc, ≤ 500) | `PlanVersionOut` · quyền như approve · version → REJECTED, lịch ACTIVE giữ nguyên; đơn có thay đổi đang PENDING_APPROVAL / LINE_INCIDENT / SLA_RISK / ESCALATED_TO_BUSINESS → RESCHEDULE_REQUIRED (Điều phối xếp tay lại, §3), đơn khác giữ trạng thái · `reason` rỗng → `422` · không còn PENDING_APPROVAL → `409` · ghi audit `PLAN_VERSION_REJECTED` |
| GET | `/api/work-orders/{id}/history` | — | timeline trạng thái: ai, khi nào, vì sao (T-041) · mọi vai trò (VIEW_BOARD) · `[{id, from_state, to_state, actor_type: USER\|AGENT\|SYSTEM, actor_id, actor_name, reason, plan_version_id, at}]` cũ → mới; dòng đầu là lúc tạo lệnh (`from_state: null` → DRAFT) · không có lệnh → `404` |

`PlanDiff` (T-042): `{plan_version: PlanVersionOut, base_version_id, base_changed, incident_id, changes[{work_order_id, product_name, priority, state, requested_return, change_type: LINE_ASSIGNMENT|RETURN_TIME_CHANGE|INCIDENT_DELAY|PRIORITY_OVERRIDE|ACCEPT_DURING_WARNING, needs_approval, old: {line, start, end}|null, new: {line, start, end}, sla_ok, reason}], decided_by, decided_by_name, decided_at, comment}` — "trước" (`old`) là slot của đơn trong lịch ACTIVE hiện tại khi version còn chờ duyệt (`base_changed` = lịch ACTIVE đã đổi kể từ lúc đề xuất), hoặc trong version cha khi đã xử lý; `null` = đơn chưa có lịch. `decided_*` / `comment`: người duyệt / từ chối, thời điểm, ghi chú hoặc lý do từ chối.

## 7. KPI — ADC-007

| Method | Path | Request | Response |
|---|---|---|---|
| GET | `/api/kpi?plan_version=` | — | `{on_time_rate, late_orders, total_delay_min, utilization{A, B}, avg_lead_time}` |
| POST | `/api/simulations/compare` | `{scenario: seed\|current, include_incident}` | `{one_line: kpi, two_line: kpi, plan_version_ids}` |

## 8. Auth — ADC-008

| Method | Path | Request | Response |
|---|---|---|---|
| GET | `/auth/google/start?next=` | — | `302` tới Google (state, nonce, code_challenge) |
| GET | `/auth/google/callback?code&state` | — | `302` → `/signup/complete` \| `/pending` \| trang chính; lỗi → `/login?error=<code>` |
| POST | `/api/signup/complete` | `{requested_role, note}` | `200` |
| GET | `/api/me` | — | `{id, name, email, avatar_url, role, status, requested_role}` — `requested_role` để frontend chọn giữa `/signup/complete` và `/pending` |
| POST | `/auth/logout` | — | `204` |
| POST | `/auth/logout-all` | — | `204` (Nên có) |
| POST | `/auth/demo-login` | `{role}` | `204` + cookie phiên; `404` khi `FEATURE_DEMO_LOGIN` tắt (ADR-0006, dự phòng pitch) |
| GET | `/api/users?status=` | — | ADMIN · `[{id, name, email, avatar_url, role, status, requested_role, request_note, created_at, approved_by, approved_at, last_login_at}]` |
| PATCH | `/api/users/{id}` | `{role?, status?}` | ADMIN, ghi audit · trả user như trên · `404` không có user · `422` ACTIVE thiếu vai trò / đưa về PENDING · `409` hạ quyền hoặc vô hiệu hóa ADMIN ACTIVE cuối cùng · DISABLED → thu hồi mọi phiên |
