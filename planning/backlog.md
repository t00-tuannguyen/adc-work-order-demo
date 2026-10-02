# Product Backlog

Nguồn: sheet *Backlog* + mục "Công việc con" của 8 đặc tả trong `team_project_management_template.xlsx`.

- **Lộ trình:** 6 tuần, mỗi sprint 1 tuần, gắn với mốc M1–M8 trong `docs/roadmap.md`.
- **Ưu tiên:** P0 = phải làm ngay · P1 = nên có · P3 = làm nếu còn thời gian
- **Trạng thái:** Chưa làm → Đang làm → Chờ review → Hoàn thành · Bị kẹt
- **Dự kiến (giờ)** của T-001–T-016 lấy từ template; của T-017–T-053 quy đổi từ mục *Các bước thực hiện* trong từng đặc tả (tổng khớp với tổng giờ đặc tả).
- Thứ tự đặt việc tôn trọng phụ thuộc: ước tính → xếp lịch → state machine/audit → agent → sự cố/HITL → KPI/Auth.

## Sprint 1 — Khởi động & nền tảng dữ liệu (Tuần 1 · M1, M2)

| Mã việc | Tên công việc | Mã US | Task/Đặc tả | Ưu tiên | Giờ | Người phụ trách | Hạn chót | Trạng thái | Ghi chú |
|---|---|---|---|---|---|---|---|---|---|
| T-001 | Lập Project Charter | US-001 | — | P0 | 4 | — | — | Chưa làm | Xác định mục tiêu, phạm vi, đối tác, chỉ số đo lường |
| T-002 | Thiết lập GitHub và quy trình nhánh | — | — | P0 | 2 | — | — | Chưa làm | Tạo kho lưu, bảo vệ nhánh, cấu hình CI/CD |
| T-003 | Thiết kế sơ đồ kiến trúc hệ thống | US-001 | — | P0 | 6 | — | — | Chưa làm | Thiết kế hệ thống, luồng dữ liệu, công nghệ sử dụng → adrs/0001, 0002 |
| T-004 | Gặp đối tác lần đầu tiên | — | — | P0 | 2 | — | — | Chưa làm | Giới thiệu dự án, lắng nghe nhu cầu; xin 15–20 PDF mẫu, xác nhận giả định đơn chiếu dở, tên miền email |
| T-005 | Xây dựng cơ sở tri thức phiên bản 1 | US-002 | — | P1 | 8 | — | — | Chưa làm | ⚠️ Dòng có sẵn trong template; Đặc tả #1 ghi "Không cần RAG" → cần xem lại có giữ không |
| T-017 | Thiết kế schema ticket, file PDF & trường trích xuất | US-001, US-002 | [ADC-001](../tasks/ADC-001-ticket-intake-pdf.md) | P0 | 5 | — | — | Chờ review | src/modules/intake/models.py (7 bảng); bật Alembic, migration ở src/services/migrations (0001 baseline identity+audit, 0002 intake) |
| T-023 | File cấu hình giả định throughput | US-003, US-016 | [ADC-002](../tasks/ADC-002-duration-estimation.md) | P0 | 4 | — | — | Chờ review | src/config/throughput.yaml (thêm product_groups), ThroughputConfigSource tự nạp lại khi file đổi. Hệ số TODO giữ null chờ mentor |
| T-024 | Hàm ước tính thời lượng + unit test | US-003, US-016 | [ADC-002](../tasks/ADC-002-duration-estimation.md) | P0 | 6 | — | — | Chờ review | estimate_duration + unit test trong src/modules/estimation; reload cấu hình làm ở T-023 |
| T-025 | Seed dataset & reset demo | US-003, US-016 | [ADC-002](../tasks/ADC-002-duration-estimation.md) | P0 | 4 | — | — | Chờ review | src/seed/orders.json (7 lệnh), incidents.json; POST /api/demo/reset (src/api/demo.py); cột ước tính trên work_orders (migration 0004) |

**Tổng dự kiến: 41 giờ**

## Sprint 2 — Lõi deterministic: đọc PDF, validator, xếp lịch, state machine (Tuần 2 · M3)

| Mã việc | Tên công việc | Mã US | Task/Đặc tả | Ưu tiên | Giờ | Người phụ trách | Hạn chót | Trạng thái | Ghi chú |
|---|---|---|---|---|---|---|---|---|---|
| T-018 | API upload PDF, lưu file & job trích xuất | US-001, US-002 | [ADC-001](../tasks/ADC-001-ticket-intake-pdf.md) | P0 | 6 | — | — | Chờ review | src/api/intake.py, src/modules/intake/ingest.py, src/services/storage.py; ADR-0009 (python-multipart). 422 mật khẩu/hỏng/>20 trang chuyển sang T-048 |
| T-048 | Đọc PDF văn bản + OCR bản scan | US-001, US-002 | [ADC-001](../tasks/ADC-001-ticket-intake-pdf.md) | P0 | 8 | — | — | Chờ review | ADR-0010 (Gemini Flash + pypdf). src/modules/intake/pdf.py (422 lúc upload), src/services/gemini.py; lời gọi Gemini ở T-019 |
| T-020 | Validator & yêu cầu bổ sung | US-001, US-002 | [ADC-001](../tasks/ADC-001-ticket-intake-pdf.md) | P0 | 4 | — | — | Chờ review | src/modules/intake/review.py (cổng + yêu cầu bổ sung + cảnh báo), src/api/intake_review.py (PATCH, submit, intake-warnings), orchestration/transitions.py |
| T-026 | Hiển thị breakdown thời lượng trên UI | US-003, US-016 | [ADC-002](../tasks/ADC-002-duration-estimation.md) | P0 | 4 | — | — | Chờ review | Ước tính gắn khi vào FEASIBILITY_CHECK, `estimate`/`estimate_error` trong WorkOrderReview; breakdown ở frontend/src/app/intake/[id], trang /assumptions (tham số + nút reset demo) |
| T-027 | Thuật toán xếp lịch earliest feasible | US-004, US-005 | [ADC-003](../tasks/ADC-003-line-scheduling-kanban.md) | P0 | 13 | — | — | Chờ review | src/modules/scheduling/scheduler.py: earliest feasible + `placement_reason`; ca làm ở T-054 |
| T-028 | API lịch & plan version | US-004, US-005 | [ADC-003](../tasks/ADC-003-line-scheduling-kanban.md) | P0 | 9 | — | — | Chờ review | src/api/scheduling.py, src/modules/orchestration/{planning,plan_versions}.py, src/modules/scheduling/models.py; migration 0005; SLA trễ → version PENDING_APPROVAL |
| T-040 | State machine work order | US-012, US-015 | [ADC-006](../tasks/ADC-006-hitl-approval-plan-version-audit.md) | P0 | 6 | — | — | Chờ review | src/modules/orchestration/state_machine.py theo domains §5 + chuyển ngoại lệ (duyệt → SCHEDULED, từ chối → RESCHEDULE_REQUIRED, xếp tay lại); override BLOCK chưa có API |
| T-041 | Audit log & lịch sử trạng thái | US-012, US-015 | [ADC-006](../tasks/ADC-006-hitl-approval-plan-version-audit.md) | P0 | 5 | — | — | Chờ review | state_history (src/modules/orchestration/history.py, migration 0009) ghi trong transition_work_order; GET /api/work-orders/{id}/history (src/api/approval.py); API đọc audit_log chưa có trong contract |

**Tổng dự kiến: 55 giờ**

## Sprint 3 — Agent, Orchestrator, Kanban/lịch — Demo 1 (Tuần 3 · M4)

| Mã việc | Tên công việc | Mã US | Task/Đặc tả | Ưu tiên | Giờ | Người phụ trách | Hạn chót | Trạng thái | Ghi chú |
|---|---|---|---|---|---|---|---|---|---|
| T-006 | Phát triển các API endpoint chính | US-003 | — | P0 | 10 | — | — | Chưa làm | Xây dựng API cốt lõi (chi tiết ở các task ADC-xxx) |
| T-007 | Phát triển giao diện chính | US-003 | — | P0 | 10 | — | — | Chưa làm | Khung ứng dụng, điều hướng, layout chung |
| T-008 | Tích hợp mô hình AI | US-004 | — | P0 | 8 | — | — | Chưa làm | Kết nối LLM, schema output, retry/timeout |
| T-009 | Chuẩn bị Demo lần 1 | — | — | P0 | 4 | — | — | Chưa làm | Kịch bản demo luồng bình thường, triển khai staging |
| T-019 | Order Agent trích xuất trường kèm vị trí nguồn | US-001, US-002 | [ADC-001](../tasks/ADC-001-ticket-intake-pdf.md) | P0 | 8 | — | — | Chờ review | Gemini (ADR-0010): src/agents/order_agent.py, src/agents/intake_pipeline.py. Chưa chạy thử với Gemini thật (chưa có GEMINI_API_KEY) |
| T-021 | Màn hình tiếp nhận: tải file, tiến độ, xem PDF, form kết quả | US-001, US-002 | [ADC-001](../tasks/ADC-001-ticket-intake-pdf.md) | P0 | 14 | — | — | Chờ review | frontend/src/app/intake (tải PDF / dán nội dung / nhập tay, tiến độ, cảnh báo; màn xác nhận lệnh); API POST /api/tickets, GET /api/files/{id}, GET /api/work-orders/{id}/intake. Không highlight vùng nguồn (chốt 30/09) |
| T-022 | Bộ PDF mẫu & đánh giá độ chính xác | US-001, US-002 | [ADC-001](../tasks/ADC-001-ticket-intake-pdf.md) | P0 | 5 | — | — | Đang làm | 16 PDF + answers.json (src/seed/pdfs), eval/intake (sinh mẫu, chấm điểm, run_eval có cache). Chưa có số đo: key Gemini gói miễn phí hết quota (429) |
| T-029 | Giao diện Kanban | US-004, US-005 | [ADC-003](../tasks/ADC-003-line-scheduling-kanban.md) | P0 | 8 | — | — | Chờ review | frontend/src/app/board, frontend/src/lib/board.ts |
| T-030 | Giao diện lịch 2 line (timeline) | US-004, US-005 | [ADC-003](../tasks/ADC-003-line-scheduling-kanban.md) | P0 | 10 | — | — | Chờ review | frontend/src/app/schedule (timeline CSS, bộ chọn plan version) |
| T-043 | Orchestrator điều phối các agent | US-012, US-015 | [ADC-006](../tasks/ADC-006-hitl-approval-plan-version-audit.md) | P0 | 6 | — | — | Chờ review | src/agents/graph.py (langgraph validate → assess → estimate → schedule) + tự xếp lịch khi tạo ticket (commit 90ee36a) |
| T-054 | Ca ngày / ca đêm theo ưu tiên (BR-14) | US-004, US-005 | [ADC-003](../tasks/ADC-003-line-scheduling-kanban.md) | P0 | 3 | — | — | Chờ review | `ShiftPolicy` (src/modules/scheduling/scheduler.py), `lines.shifts` trong throughput.yaml: ca ngày 06:00–22:00, ca đêm chỉ Khẩn / VIP; áp dụng cả tái lập lịch sự cố |

**Tổng dự kiến: 86 giờ**

## Sprint 4 — Phản hồi Demo 1, sự cố, tái lập lịch, rủi ro, HITL (Tuần 4 · M5)

| Mã việc | Tên công việc | Mã US | Task/Đặc tả | Ưu tiên | Giờ | Người phụ trách | Hạn chót | Trạng thái | Ghi chú |
|---|---|---|---|---|---|---|---|---|---|
| T-010 | Xử lý phản hồi từ Demo 1 | — | — | P0 | 6 | — | — | Chưa làm | Triển khai phản hồi từ đối tác sau Demo 1 |
| T-031 | API & form mô phỏng sự cố | US-006, US-007, US-008, US-009 | [ADC-004](../tasks/ADC-004-incident-rescheduling.md) | P0 | 5 | — | — | Chờ review | src/api/incidents.py, src/modules/orchestration/incidents.py, migration 0006; form frontend/src/components/IncidentForm.tsx (trang /planner) |
| T-032 | Phát hiện đơn chồng lấn khung dừng | US-006, US-007, US-008, US-009 | [ADC-004](../tasks/ADC-004-incident-rescheduling.md) | P0 | 6 | — | — | Chờ review | find_affected_slots (scheduling/incident.py) + find_affected, current_downtimes (orchestration/incidents.py); API trả ở T-033 |
| T-033 | Tái lập lịch theo ưu tiên + kiểm tra line thay thế | US-006, US-007, US-008, US-009 | [ADC-004](../tasks/ADC-004-incident-rescheduling.md) | P0 | 14 | — | — | Chờ review | reschedule (scheduling/incident.py), replan/resolve (orchestration/incidents.py), POST /api/incidents/{id}/resolve; phương án INCIDENT luôn chờ duyệt |
| T-034 | Scheduler Agent giải thích phương án | US-006, US-007, US-008, US-009 | [ADC-004](../tasks/ADC-004-incident-rescheduling.md) | P0 | 5 | — | — | Chờ review | src/agents/scheduler_agent.py (validator giờ/line), POST /api/incidents/{id}/explanation, FEATURE_AI_EXPLANATION |
| T-035 | Màn hình so sánh trước/sau sự cố | US-006, US-007, US-008, US-009 | [ADC-004](../tasks/ADC-004-incident-rescheduling.md) | P0 | 8 | — | — | Chờ review | frontend/src/app/incidents (danh sách + [id] trước/sau), components/LineTimeline.tsx; GET /api/incidents |
| T-036 | Kiểm tra rủi ro đơn mới (WARN/BLOCK) | US-010, US-011, US-014 | [ADC-005](../tasks/ADC-005-risk-control-escalation.md) | P0 | 6 | — | — | Chờ review | assess_new_order (src/modules/risk), POST /risk-check (src/api/risk.py); /schedule: WARN chờ duyệt, BLOCK → BLOCK_NEW_ORDER 409; migration 0007. Override BLOCK chờ T-040/T-042 |
| T-037 | Tạo escalation cho đơn trễ | US-010, US-011, US-014 | [ADC-005](../tasks/ADC-005-risk-control-escalation.md) | P0 | 4 | — | — | Chờ review | raise_escalation (orchestration/escalations.py) gọi từ replan sự cố + đơn bị đẩy khi WARN; GET /api/escalations (can_close); migration 0008. API đóng escalation chưa có trong contract |
| T-042 | Luồng phê duyệt plan version (HITL) | US-012, US-015 | [ADC-006](../tasks/ADC-006-hitl-approval-plan-version-audit.md) | P0 | 22 | — | — | Chờ review | src/modules/orchestration/review.py, src/api/approval.py (diff/approve/reject, gộp vào ACTIVE, khóa lạc quan 409); frontend/src/app/approvals, components/HistoryTimeline.tsx. Chưa: chặn tự duyệt, LLM tóm tắt diff |

**Tổng dự kiến: 76 giờ**

## Sprint 5 — Escalation, KPI, Google Auth — Demo 2 (Tuần 5 · M6)

| Mã việc | Tên công việc | Mã US | Task/Đặc tả | Ưu tiên | Giờ | Người phụ trách | Hạn chót | Trạng thái | Ghi chú |
|---|---|---|---|---|---|---|---|---|---|
| T-011 | Phát triển thêm tính năng từ phản hồi | US-005 | — | P1 | 8 | — | — | Chưa làm | Thêm tính năng mới theo yêu cầu đối tác |
| T-012 | Kiểm thử toàn diện và Sửa lỗi | — | — | P0 | 6 | — | — | Chưa làm | Chạy toàn bộ TC của các đặc tả, sửa lỗi |
| T-038 | Risk Agent soạn thông điệp kinh doanh | US-010, US-011, US-014 | [ADC-005](../tasks/ADC-005-risk-control-escalation.md) | P0 | 5 | — | — | Chờ review | src/agents/risk_agent.py (check_draft + mẫu soạn sẵn), POST /api/escalations/{id}/draft, /approve; `make eval-risk` chờ OPENAI_API_KEY thật |
| T-039 | Giao diện hàng đợi escalation | US-010, US-011, US-014 | [ADC-005](../tasks/ADC-005-risk-control-escalation.md) | P0 | 8 | — | — | Chờ review | frontend/src/app/escalations, components/RiskBanner.tsx (Kanban + màn xác nhận lệnh), badge menu; lib/risk.ts |
| T-044 | Tính KPI từ plan version | US-013 | [ADC-007](../tasks/ADC-007-kpi-dashboard-line-comparison.md) | P1 | 6 | — | — | Chưa làm |  |
| T-045 | Chế độ mô phỏng 1 line | US-013 | [ADC-007](../tasks/ADC-007-kpi-dashboard-line-comparison.md) | P1 | 5 | — | — | Chưa làm |  |
| T-046 | Dashboard KPI & so sánh | US-013 | [ADC-007](../tasks/ADC-007-kpi-dashboard-line-comparison.md) | P1 | 8 | — | — | Chưa làm |  |
| T-049 | Cấu hình OAuth client Google & callback xác minh ID token | US-017, US-018, US-019, US-020 | [ADC-008](../tasks/ADC-008-google-auth.md) | P1 | 10 | — | — | Chờ review | src/api/auth.py, src/modules/identity/{oidc,service}.py; ADR-0008 (PyJWT). Chờ tạo OAuth client thật trên Google Cloud |
| T-050 | Phiên đăng nhập, đăng xuất & phân quyền RBAC | US-017, US-018, US-019, US-020 | [ADC-008](../tasks/ADC-008-google-auth.md) | P1 | 6 | — | — | Chờ review | src/modules/identity/sessions.py, src/api/deps.py (current_user, require); /api/estimate & /api/config/throughput đã gắn RBAC |
| T-051 | Màn đăng nhập / đăng ký / chờ cấp quyền / menu tài khoản | US-017, US-018, US-019, US-020 | [ADC-008](../tasks/ADC-008-google-auth.md) | P1 | 10 | — | — | Chờ review | frontend/ (Next.js 16): /login, /signup/complete, /pending, /logged-out, menu tài khoản; trang theo vai trò /sales /planner /ops |
| T-052 | Trang quản lý người dùng & cấp vai trò | US-017, US-018, US-019, US-020 | [ADC-008](../tasks/ADC-008-google-auth.md) | P1 | 6 | — | — | Chờ review | API src/api/users.py + trang frontend/src/app/admin/users |
| T-053 | Gắn người dùng thật vào audit log | US-017, US-018, US-019, US-020 | [ADC-008](../tasks/ADC-008-google-auth.md) | P1 | 8 | — | — | Chờ review | audit_log chỉ ghi thêm (src/modules/orchestration/audit.py), actor_id bắt buộc; ghi LOGIN/LOGOUT/LOGOUT_ALL/DEMO_LOGIN/SIGNUP_REQUESTED/USER_UPDATED |
| T-055 | Xóa lệnh nháp | US-001 | [ADC-001](../tasks/ADC-001-ticket-intake-pdf.md) | P1 | 2 | — | — | Chờ review | DELETE /api/work-orders/{id} (chỉ DRAFT, audit WORK_ORDER_DELETED, giữ PDF gốc); nút "Xóa nháp" ở frontend/src/app/intake/[id] và icon thùng rác trên thẻ Kanban |
| T-056 | Tinh chỉnh UX tiếp nhận & lịch | US-001, US-004 | [ADC-003](../tasks/ADC-003-line-scheduling-kanban.md) | P1 | 3 | — | — | Chờ review | Upload thành công → Kanban (DRAFT mới mở màn xác nhận); thẻ Kanban → /schedule đúng ngày + khối; lý do xếp ngắn gọn; cờ giờ trả trên lịch; polling ingest giãn dần |
| T-057 | Bổ sung từ khóa nhóm sản phẩm từ ticket thật | US-003 | [ADC-002](../tasks/ADC-002-duration-estimation.md) | P1 | 2 | — | — | Chờ review | throughput.yaml: thêm nhóm vegetable, powder (density_factor null — cần chốt hệ số); mở rộng seafood, fruit |
| T-058 | Dồn lịch (compaction) sau sự cố — không để line nghỉ | US-006, US-008 | [ADC-004](../tasks/ADC-004-incident-rescheduling.md) | P0 | 4 | — | — | Chờ review | ADR-0011; compact (scheduling/incident.py), outcome PULLED_FORWARD |

**Tổng dự kiến: 88 giờ**

## Sprint 6 — Triển khai chính thức & đánh giá cuối kỳ (Tuần 6 · M7, M8)

| Mã việc | Tên công việc | Mã US | Task/Đặc tả | Ưu tiên | Giờ | Người phụ trách | Hạn chót | Trạng thái | Ghi chú |
|---|---|---|---|---|---|---|---|---|---|
| T-013 | Triển khai lên môi trường thực tế | — | — | P0 | 4 | — | — | Đang làm | Bản demo miễn phí (ADR-0012): Render Free + Neon + Vercel, PDF lưu tạm. render.yaml, docs/deployment.md; Dockerfile đọc $PORT, sửa lỗi image không chạy được (gói cài ở /root/.local); driver psycopg 3; CI chạy migration trên PostgreSQL |
| T-014 | Kiểm thử cuối cùng và Tinh chỉnh giao diện | — | — | P0 | 6 | — | — | Chưa làm | Kiểm tra toàn diện, hoàn thiện UX |
| T-015 | Viết tài liệu hướng dẫn | — | — | P1 | 4 | — | — | Chưa làm | README, hướng dẫn sử dụng, tài liệu API |
| T-016 | Chuẩn bị thuyết trình cuối kỳ | — | — | P0 | 4 | — | — | Chưa làm | Slide, kịch bản demo, báo cáo tác động |
| T-047 | Kịch bản demo pitch | US-013 | [ADC-007](../tasks/ADC-007-kpi-dashboard-line-comparison.md) | P1 | 4 | — | — | Chưa làm |  |

**Tổng dự kiến: 22 giờ**

**Tổng toàn dự án: 368 giờ**

## Việc trống (T-055 trở đi)

Thêm việc mới vào sprint tương ứng, luôn gắn Mã US và file task.
