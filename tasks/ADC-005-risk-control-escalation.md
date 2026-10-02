# ADC-005: Kiểm soát rủi ro: cảnh báo/chặn đơn mới và escalation cho kinh doanh

> Nguồn: sheet *Đặc tả tính năng* — Đặc tả #5 trong `team_project_management_template.xlsx`.

| Trường | Giá trị |
|---|---|
| Đặc tả | #5 |
| User Story | US-010, US-011, US-014 (FR 10, FR 11, FR 14) |
| Functional Requirement (PRD) | FR 10, FR 11, FR 14 |
| Ưu tiên | P0 (FR 14: P1) |
| Sprint | 4, 5 |
| Người viết | [Họ tên người phụ trách] |
| Ngày tạo / cập nhật | 23/09/2026 / 25/09/2026 |
| Trạng thái | Chờ review |

## References
- [specs/features.md](../specs/features.md)
- [specs/api-contracts.md](../specs/api-contracts.md)
- [specs/domains.md](../specs/domains.md)
- [specs/user-roles.md](../specs/user-roles.md)
- [AGENTS.md](../AGENTS.md)

## 1. Động lực (Motivation)

### Vấn đề cần giải quyết

Khi đang có sự cố hoặc quá tải, kinh doanh vẫn có thể hứa giờ trả cho đơn mới, khiến các đơn đã nhận càng trễ. Đơn trễ thường chỉ được biết khi đã muộn và không có đầu mối kinh doanh xử lý với khách.

### Người dùng mục tiêu

- Kinh doanh / CSKH: nhận cảnh báo, xử lý escalation, liên hệ khách.
- Quản lý: duyệt việc nhận đơn khi đang có cảnh báo.

### Mục tiêu kỳ vọng

- 100% đơn mới có rủi ro trong lúc sự cố được cảnh báo hoặc chặn (FR 10).
- 100% đơn có nguy cơ trả trễ có mục escalation (FR 11).
- AI soạn nháp thông điệp, chỉ gửi sau khi người duyệt (FR 14).
- 0 thông điệp gửi khách mà chưa duyệt.

### Phương án thay thế đã xem xét

- Chặn cứng mọi đơn mới khi có sự cố: an toàn nhưng mất cả những đơn vẫn kịp.
- Chỉ cảnh báo chung chung: dễ bị bỏ qua.

**→ Chọn** 3 mức: OK / WARN (kịp giờ trả nhưng làm đơn đã nhận trễ thêm — nhận được nhưng cần duyệt) / BLOCK (không kịp giờ trả dù xếp sớm nhất); BLOCK vẫn cho Quản lý override kèm lý do.

## 2. Thiết kế (Design)

### Kiến trúc hệ thống

Risk & Escalation Agent chạy sau Scheduler:
(a) Kiểm tra đơn mới: mô phỏng chèn đơn vào plan hiện hành; làm đơn khác vượt giờ trả → WARN (cần duyệt); giờ xong của chính đơn mới > giờ trả → BLOCK, trạng thái BLOCK_NEW_ORDER.
(b) Escalation: mọi đơn SLA_RISK có giờ xong > giờ trả → tạo escalation, lệnh chuyển ESCALATED_TO_BUSINESS.
(c) Soạn nháp thông điệp cho kinh doanh/khách.
Việc quyết định mức rủi ro là luật deterministic; LLM chỉ soạn văn bản.

### Thiết kế giao diện (UI/UX)

- Khi tạo đơn mới: banner vàng (WARN) hoặc đỏ (BLOCK) kèm lý do và giờ trả sớm nhất khả thi; nút "Yêu cầu duyệt nhận đơn".
- Hàng đợi "Escalation": đơn trễ, số phút trễ, khách, ưu tiên; mở ra thấy nháp thông điệp, sửa được, nút "Duyệt và đánh dấu đã gửi" (MVP không gửi email thật).
- Badge đếm escalation đang mở trên thanh điều hướng.

### Thiết kế API

- POST /api/work-orders/{id}/risk-check → {level: OK|WARN|BLOCK, reasons[], earliest_feasible_return}
- GET /api/escalations?status=open
- POST /api/escalations/{id}/draft → {message_draft} (gọi LLM)
- POST /api/escalations/{id}/approve {final_message} → đánh dấu đã duyệt, ghi audit.

### Mô hình dữ liệu

- risk_checks(id, work_order_id FK, plan_version_id FK, level, reasons JSON, created_at)
- escalations(id, work_order_id FK, incident_id nullable, delay_min, status ENUM[OPEN, DRAFTED, APPROVED, CLOSED], draft_message, final_message, approved_by, approved_at)

### Thiết kế AI/ML

Risk Agent nhận JSON sự kiện (đơn, ưu tiên, giờ trả cũ, giờ dự kiến mới, lý do, phương án) → soạn nháp ngắn, lịch sự, tiếng Việt (tùy chọn tiếng Anh): lời xin lỗi, nguyên nhân ở mức chung, giờ trả mới đề xuất, đầu mối liên hệ.
Ràng buộc: không hứa giờ khác dữ liệu; không đề cập an toàn hay liều chiếu.
Đánh giá: checklist chấm tay trên 10 tình huống mẫu.

### Trường hợp đặc biệt và Xử lý lỗi

- Đơn mới thiếu giờ trả → đã bị chặn ở bước tiếp nhận (Đặc tả #1).
- Sự cố kết thúc sớm → rủi ro hết, escalation chuyển "Có thể đóng" để người xác nhận.
- Nhiều đơn cùng một khách → gộp một thông điệp (có thì tốt).
- LLM lỗi → hiển thị mẫu thông điệp soạn sẵn để điền tay.

### Bảo mật và Quyền riêng tư

- Chỉ Kinh doanh / Quản lý duyệt thông điệp; nháp không bao giờ tự gửi.
- Không đưa thông tin khách thật vào prompt.

## 3. Kế hoạch (Plan)

### Các bước thực hiện

1. Luật mức rủi ro + test (6h)
2. Tự động tạo escalation (4h)
3. Prompt soạn thông điệp + đánh giá (5h)
4. UI banner và hàng đợi escalation (8h)

### Công việc con (liên kết Backlog)

- T-036: Kiểm tra rủi ro đơn mới (WARN/BLOCK)
- T-037: Tạo escalation cho đơn trễ
- T-038: Risk Agent soạn thông điệp kinh doanh
- T-039: Giao diện hàng đợi escalation

### Phụ thuộc

- Cần: xếp lịch (Đặc tả #3), xử lý sự cố (Đặc tả #4), luồng duyệt (Đặc tả #6).

### Timeline dự kiến

Sprint 4 (FR 10, FR 11) → Sprint 5 (hàng đợi escalation, hoàn thiện FR 14). Tổng dự kiến ~23 giờ. [Điền ngày cụ thể]

### Kế hoạch kiểm thử

- Đơn mới trong sự cố, vẫn kịp và không ảnh hưởng đơn khác → OK.
- Kịp nhưng đẩy đơn khác trễ → WARN.
- Không thể kịp → BLOCK kèm giờ sớm nhất.
- Mọi đơn SLA_RISK trễ đều có escalation (đếm đủ 100%).
- Nháp không chứa giờ sai so với dữ liệu.
- Không có đường nào gửi thông điệp mà bỏ qua bước duyệt.

### Kế hoạch triển khai

Bật cùng tính năng sự cố (Sprint 4); hàng đợi và AI soạn thông điệp ở Sprint 5. Phần AI soạn thông điệp đặt sau feature flag để tắt được nếu LLM chậm khi demo.

### Tiêu chí thành công

- FR 10, FR 11 đạt 100% theo bảng Metrics của PRD.
- FR 14: mọi escalation trong kịch bản demo có nháp.
- 0 thông điệp gửi mà chưa duyệt.

### Rủi ro và Cách giảm thiểu

- Ngưỡng WARN/BLOCK chưa sát thực tế → đưa tham số vào cấu hình, hỏi ý kiến đối tác.
- LLM viết hứa hẹn quá mức → ràng buộc prompt + bắt buộc người duyệt.

## Task con & trạng thái

| Task | Nội dung | Sprint | Dự kiến (giờ) | Owner | Trạng thái |
|---|---|---|---|---|---|
| T-036 | Kiểm tra rủi ro đơn mới (WARN/BLOCK) | 4 | 6 | — | Chờ review |
| T-037 | Tạo escalation cho đơn trễ | 4 | 4 | — | Chờ review |
| T-038 | Risk Agent soạn thông điệp kinh doanh | 5 | 5 | — | Chờ review |
| T-039 | Giao diện hàng đợi escalation | 5 | 8 | — | Chờ review |

## Nhật ký

- 23/09/2026: Tạo từ Đặc tả #5.
- 25/09/2026: Chuyển sang lộ trình 6 tuần (6 sprint); cập nhật sprint của task con và timeline.
- 25/09/2026: Thống nhất "kịp giờ trả nhưng đẩy đơn khác trễ" = WARN (khớp TC và `docs/demo-scenarios.md`); BLOCK chỉ khi chính đơn mới không kịp.
- 01/10/2026 (T-036): Chốt cách mô phỏng chèn đơn (BR-07): xếp vào khe trống sớm nhất; trễ thì thử đẩy lùi đơn ưu tiên thấp hơn chưa bắt đầu (SCHEDULED, chưa có đề xuất chờ duyệt), đơn bị đẩy xếp lại như tái lập lịch sự cố. Kịp nhờ đẩy → WARN (kể cả khi đơn bị đẩy vẫn kịp — đổi lịch đã hứa là PRIORITY_OVERRIDE, cần duyệt); vẫn trễ → BLOCK. Đơn Thường chỉ ra OK/BLOCK. `POST /schedule` tự chạy risk check: BLOCK → BLOCK_NEW_ORDER + `409 NEW_ORDER_BLOCKED` (thay cho RETURN_TIME_CHANGE cũ), WARN → version chờ duyệt ACCEPT_DURING_WARNING + PRIORITY_OVERRIDE. `POST /risk-check` chỉ mô phỏng. Đã cập nhật `specs/api-contracts.md` §3, §5.
- 01/10/2026: Còn mở — API Quản lý override đơn BLOCK chưa có trong contract (chờ T-040 chốt chuyển BLOCK_NEW_ORDER → ? và T-042). Ngưỡng WARN/BLOCK chưa tham số hóa: luật hiện chỉ dựa vào giờ trả, chưa có ngưỡng nào để đưa vào cấu hình.
- 01/10/2026 (T-037): Escalation tạo cho mọi đơn trễ trong phương án mới — phương án sự cố và cả đơn bị đẩy trễ khi nhận đơn WARN (để đủ 100% FR 11), dù phương án còn chờ duyệt. Chỉ đơn SLA_RISK chuyển ESCALATED_TO_BUSINESS; đơn trạng thái khác giữ nguyên (chờ T-040). Mỗi đơn tối đa 1 mục đang mở, tính lại thì cập nhật `delay_min`. "Có thể đóng" là trường tính `can_close`, không thêm trạng thái; chưa có API đóng escalation trong contract — cần chốt.
- 01/10/2026 (T-038): Risk Agent dùng OpenAI qua `get_llm()` (ADR-0002) + `EscalationDraft`. Nháp LLM qua kiểm tra deterministic `check_draft` (giờ/ngày phải khớp giờ trả cũ hoặc giờ trả mới, phải có giờ trả mới, cấm "liều/kGy/an toàn/bức xạ/Line A|B"); vi phạm, LLM lỗi, tắt `FEATURE_AI_MESSAGE_DRAFT` hoặc thiếu key → mẫu soạn sẵn (`source=TEMPLATE`). Nguyên nhân gửi LLM chỉ ở mức chung (sự cố kỹ thuật / điều chỉnh kế hoạch), không có thông tin khách. Duyệt chỉ từ DRAFTED. Bộ đánh giá 10 tình huống: `make eval-risk` → eval/results/risk-messages.md (ràng buộc cứng chấm tự động, checklist chấm tay) — chưa chạy được vì `.env` chưa có OPENAI_API_KEY thật. Gộp thông điệp nhiều đơn cùng khách: chưa làm (work order chưa có trường khách hàng).
- 01/10/2026 (T-039): Banner rủi ro (vàng WARN / đỏ BLOCK, lý do + giờ trả sớm nhất) trên thẻ Kanban và màn xác nhận lệnh (tự kiểm tra khi lệnh FEASIBILITY_CHECK / BLOCK_NEW_ORDER); "Yêu cầu duyệt nhận đơn" = Điều phối xếp lịch đơn WARN → plan chờ duyệt. Trang /escalations (lọc Đang mở / Đã duyệt / Tất cả, AI soạn nháp, sửa, "Duyệt và đánh dấu đã gửi"), badge đếm escalation mở trên menu cho Kinh doanh / Quản lý. Đã thử tay trên trình duyệt: Kanban WARN → chờ duyệt, BLOCK → banner đỏ; /escalations soạn nháp (mẫu soạn sẵn) → duyệt, badge menu cập nhật. Sửa khi thử: `can_close` lấy thay đổi mới nhất của đơn trong version ACTIVE / chờ duyệt, không lấy bản chép lịch ACTIVE trong đề xuất khác (trước đó đơn đang trễ trong phương án sự cố bị báo nhầm "Có thể đóng").
