# ADC-001: Tiếp nhận ticket từ file PDF và tạo lệnh sản xuất (Order Agent)

> Nguồn: sheet *Đặc tả tính năng* — Đặc tả #1 trong `team_project_management_template.xlsx`.

| Trường | Giá trị |
|---|---|
| Đặc tả | #1 |
| User Story | US-001, US-002 (FR 01, FR 02) |
| Functional Requirement (PRD) | FR 01, FR 02 |
| Ưu tiên | P0 |
| Sprint | 1, 2, 3 |
| Người viết | [Họ tên người phụ trách] |
| Ngày tạo / cập nhật | 23/09/2026 / 26/09/2026 |
| Trạng thái | Bản nháp |

## References
- [specs/features.md](../specs/features.md)
- [specs/api-contracts.md](../specs/api-contracts.md)
- [specs/domains.md](../specs/domains.md)
- [specs/user-roles.md](../specs/user-roles.md)
- [AGENTS.md](../AGENTS.md)

## 1. Động lực (Motivation)

### Vấn đề cần giải quyết

Khách gửi đơn dưới dạng file PDF (phiếu yêu cầu dịch vụ, email in ra, bản scan) qua email/Zalo, gồm tên sản phẩm, số lượng, quy cách thùng, liều chiếu, mức ưu tiên, giờ hàng đến và giờ trả mong muốn. Hiện nhân viên kinh doanh mở từng file, đọc và nhập tay; bản scan khó đọc, trường thiếu (liều, giờ trả) thường chỉ bị phát hiện khi sản xuất đã lên kế hoạch, dẫn đến xếp lịch sai và phải hỏi lại khách.

### Người dùng mục tiêu

- Nhân viên kinh doanh / CSKH: người tải file PDF và xác nhận dữ liệu (người dùng chính).
- Điều phối sản xuất: nhận lệnh đã hợp lệ để xếp lịch.

Hiện tại: mở từng file PDF, đọc bằng mắt, nhập tay vào bảng tính; không có cơ chế kiểm tra trường bắt buộc hay đối chiếu nguồn.

### Mục tiêu kỳ vọng

- Tải được file PDF (văn bản số và bản scan); mỗi ticket trong file tạo 1 work order DRAFT, lưu kèm file gốc, trang nguồn và timestamp (FR 01).
- Trích xuất 8 trường; thiếu tên sản phẩm, số lượng, quy cách, liều hoặc giờ trả → sinh yêu cầu bổ sung (FR 02).
- Mỗi trường có nhãn nguồn gốc và vùng nguồn trên PDF để người dùng đối chiếu nhanh.
- Chỉ số (đề xuất, cần chốt với mentor): 100% trường bắt buộc được kiểm tra; độ chính xác ≥ 95% với PDF văn bản số, ≥ 85% với PDF scan; PDF 1 trang → hiện form kết quả dưới 10 giây. Mục tiêu "ticket → lịch < 5 giây" của PRD tính từ lúc ticket đã được xác nhận.

### Phương án thay thế đã xem xét

- Chỉ nhận nội dung dán vào: đơn giản nhưng không khớp thực tế khách gửi PDF.
- Form web cho khách tự điền: chuẩn nhất nhưng thay đổi quy trình của khách, ngoài phạm vi 6 tuần.
- Parser theo mẫu PDF cố định: chính xác với 1 mẫu nhưng vỡ khi khách dùng mẫu khác hoặc gửi bản scan.

**→ Chọn:** tải PDF → tách chữ (text layer; OCR nếu là bản scan) → LLM trích xuất theo JSON schema kèm vị trí nguồn → validator deterministic → cổng tin cậy (ADR-0007): chỉ cần người xác nhận khi độ tin cậy thấp, kết quả không rõ ràng thì cảnh báo cho người. Giữ tab "Dán nội dung" và chế độ nhập tay làm dự phòng.

## 2. Thiết kế (Design)

### Kiến trúc hệ thống

Luồng: Tải PDF → API lưu file + tạo job xử lý bất đồng bộ → Bộ đọc PDF: kiểm tra định dạng, dung lượng, số trang; có text layer thì trích chữ kèm toạ độ, không có thì OCR theo trang (lưu độ tin cậy từng vùng) → Tách ticket (1 file có thể nhiều ticket) → Orchestrator tạo work order DRAFT cho mỗi ticket → Order Agent (LLM, output ràng buộc schema, trả kèm trang và đoạn nguồn cho từng trường) → Validator deterministic (kiểu, đơn vị, trường bắt buộc, giờ trả > giờ đến).

→ Cổng tin cậy (deterministic, `src/modules/intake/confidence.py`, ADR-0007) dựa trên độ tin cậy OCR từng vùng và nhãn nguồn:

- Thiếu trường: tạo yêu cầu bổ sung, giữ DRAFT (BR-01).
- **REVIEW** — có trường OCR < `low_confidence_threshold` (0,8) hoặc không chắc ranh giới ticket: giữ DRAFT, `review_status = NEEDS_REVIEW`; người dùng xác nhận/sửa các trường bị gắn cờ rồi submit (HITL, BR-12).
- **WARN** — không rõ ràng (OCR 0,8–0,9, giá trị AI suy luận / mặc định, file trùng): **tự** chuyển FEASIBILITY_CHECK, đồng thời tạo cảnh báo tiếp nhận cho người xem lại (`ACCEPTED_WITH_WARNINGS`, BR-13).
- **AUTO** — rõ ràng: **tự** chuyển FEASIBILITY_CHECK, gọi ước tính thời lượng (Đặc tả #2) và xếp lịch (Đặc tả #3), không cần người xác nhận (`AUTO_ACCEPTED`).

Job báo tiến độ 4 bước cho UI; mọi bước ghi audit log (Đặc tả #6).
Công cụ (ADR-0010, chốt khi làm T-048): pypdf kiểm tra file lúc upload (mật khẩu / hỏng / số trang / text layer); Gemini Flash đọc, OCR và trích xuất 8 trường trong 1 lời gọi.

### Thiết kế giao diện (UI/UX)

Thiết kế: https://claude.ai/artifact/3fPfUg9J8muJ9YGNPmf8NH — trang "Đặc tả #1 · Tiếp nhận ticket" (bản Light và Dark), 6 màn hình:

1. Tải file PDF: tab "Tải file PDF" / "Dán nội dung"; vùng kéo thả kèm nút "Chọn file từ máy"; ghi rõ giới hạn 10 MB, 20 trang; danh sách file mẫu cho demo.
2. Đang trích xuất: thanh tiến độ 4 bước (Tải lên → Đọc PDF/OCR → Nhận diện ticket → Trích xuất 8 trường); cho chạy nền.
3. Kết quả đủ trường: trình xem PDF bên trái (lật trang, phóng to, mở file gốc), vùng nguồn tô vàng và đánh số 1–8 khớp với trường bên phải. Nhãn nguồn: Nguyên văn / AI suy luận / Đã quy đổi / OCR tin cậy thấp / Nhập tay / Mặc định.
4. Cần xác nhận (REVIEW): trường tin cậy thấp viền đỏ, nhảy tới vùng nguồn trên PDF; nút "Xác nhận & tạo lệnh" chỉ mở khi mọi trường bị gắn cờ đã được xác nhận hoặc sửa.
5. Đã tạo lệnh kèm cảnh báo (WARN): banner vàng liệt kê trường không rõ ràng (lý do + vùng nguồn), nút "Đã xem" / "Sửa"; cảnh báo cũng vào hàng đợi "Cảnh báo tiếp nhận".
6. Thiếu trường: tóm tắt lỗi đầu form có link tới trường lỗi; lỗi hiện ngay dưới trường; khối câu hỏi bổ sung gửi khách do AI soạn; nút tạo lệnh bị khóa.
7. PDF không đọc được: banner lỗi, tải file khác hoặc nhập tay.
8. Tạo lệnh thành công (AUTO): tiến trình trạng thái, thông tin lệnh, nhật ký — không có bước bấm xác nhận.

Quy ước: "Tên sản phẩm" là ô nhập tự do, lấy nguyên văn. Mức ưu tiên có màu riêng, luôn kèm chữ: Thường – xám xanh, Khẩn – cam, VIP – hồng tím. Phong cách theo UI/UX Pro Max: Fira Sans (Fira Code cho mã/số), tương phản chữ ≥ 4.5:1, viền focus rõ, vùng bấm ≥ 40–44px, tôn trọng thiết lập giảm chuyển động.

### Thiết kế API

- POST /api/tickets/upload (multipart: file, channel, received_at) → 202 {job_id, file_id}
- GET /api/ingest-jobs/{job_id} → {status, step: UPLOADED|READING|DETECTING|EXTRACTING|DONE|FAILED, progress, work_orders[{id, review_status, state}], error_code}
- GET /api/files/{file_id} → file PDF gốc (inline) cho trình xem PDF của trình duyệt — **không highlight vùng nguồn** (chốt 30/09/2026); GET /api/work-orders/{id}/intake → dữ liệu màn xác nhận
- POST /api/tickets {raw_text, source, received_at} → giữ cho tab "Dán nội dung"
- PATCH /api/work-orders/{id} {fields} → trường sửa thành MANUAL, chạy lại validator + cổng tin cậy; POST /api/work-orders/{id}/submit (chỉ đơn DRAFT: thiếu trường / NEEDS_REVIEW) → FEASIBILITY_CHECK hoặc 422 kèm danh sách trường lỗi / chưa xác nhận.
- GET /api/intake-warnings?status=open; POST /api/intake-warnings/{id}/ack {note} → người đã xem cảnh báo, ghi audit.
- Lỗi: 413 (quá 10 MB), 415 (không phải PDF), 422 (PDF có mật khẩu/hỏng/quá 20 trang); OCR thất bại → job FAILED, error_code OCR_FAILED để UI chuyển nhập tay.

### Mô hình dữ liệu

- ticket_files(id, file_name, storage_path, sha256, size_bytes, page_count, has_text_layer, ocr_used, channel, received_at, uploaded_by)
- ingest_jobs(id, file_id FK, status, step, error_code, started_at, finished_at)
- tickets(id, file_id FK nullable, source_type ENUM[PDF, TEXT, MANUAL], raw_text, page_from, page_to)
- work_orders(id, ticket_id FK, review_status ENUM[AUTO_ACCEPTED, ACCEPTED_WITH_WARNINGS, NEEDS_REVIEW, NEEDS_CLARIFICATION], product_name, product_group nullable — gán ở bước ước tính (Đặc tả #2), quantity, pkg_length_cm, pkg_width_cm, pkg_height_cm, pkg_weight_kg, required_dose_kgy, priority ENUM[NORMAL, URGENT, VIP], expected_arrival, requested_return, state, created_at, updated_at)
- field_extractions(id, work_order_id FK, field, value, source_kind ENUM[VERBATIM, INFERRED, CONVERTED, OCR_LOW, MANUAL, DEFAULT], page, bbox JSON, snippet, confidence)
- clarification_requests(id, work_order_id FK, field, question, status, answered_at)
- intake_warnings(id, work_order_id FK, field nullable, code, status ENUM[OPEN, ACKNOWLEDGED], acknowledged_by, acknowledged_at, note)

Index: work_orders(state), work_orders(requested_return), work_orders(review_status), intake_warnings(status), ingest_jobs(status), ticket_files(sha256).

### Thiết kế AI/ML

- Order Agent nhận văn bản theo trang (kèm toạ độ dòng) và trả JSON: mỗi trường gồm value, source_kind, page, snippet; trường không có trong PDF trả null, không được đoán.
- Tên sản phẩm lấy nguyên văn. Mức ưu tiên suy luận từ cụm như "gấp", "khẩn" → gắn "AI suy luận" để người dùng xác nhận.
- Prompt: định nghĩa 8 trường, đơn vị chuẩn (cm, kg, kGy, dd/mm/yyyy hh:mm), few-shot từ các mẫu PDF (phiếu yêu cầu, email in ra). Không cần RAG.
- Độ tin cậy (ADR-0010, **tạm thời**): Gemini tự chấm `confidence` 0–1 cho từng trường; hiệu chỉnh bằng benchmark T-022. < `low_confidence_threshold` (0,8) → "OCR tin cậy thấp" → REVIEW; [0,8; 0,9) → cảnh báo; ≥ 0,9 → không cần người xác nhận. Ngưỡng ở mục `ocr` của `throughput.yaml`.
- Đánh giá: 15–20 PDF mẫu (≥ 5 bản scan) có đáp án; đo độ chính xác từng trường, tỷ lệ phát hiện đúng trường thiếu, độ đúng của trang/vùng nguồn, và **tỷ lệ AUTO sai** (đơn AUTO có trường sai — mục tiêu ≈ 0) để hiệu chỉnh ngưỡng.

### Trường hợp đặc biệt và Xử lý lỗi

- File không phải PDF, > 10 MB, > 20 trang, có mật khẩu hoặc hỏng → báo lỗi rõ, không tạo lệnh.
- Bản scan quá mờ, OCR không đọc được → chuyển nhập tay, vẫn cho xem file gốc.
- Một file nhiều ticket → tách thành nhiều lệnh nháp; không chắc ranh giới → REVIEW, yêu cầu người dùng xác nhận.
- Tải trùng file (cùng sha256) → cảnh báo có thể trùng đơn (không chặn).
- Đơn WARN đã có lịch mà người sửa trường → tạo plan version mới theo luật duyệt ADR-0005.
- Đơn vị khác (inch, lb) → quy đổi, gắn nhãn "Đã quy đổi".
- Liều không có trong danh mục cấu hình → cần xác nhận.
- Giờ trả ≤ giờ hàng đến → lỗi hiện ngay dưới trường.
- LLM trả sai schema hoặc timeout → thử lại tối đa 3 lần (lỗi quá tải chờ 1 → 2 → 4 s) rồi chuyển nhập tay.

### Bảo mật và Quyền riêng tư

- Chỉ vai trò Kinh doanh / Điều phối được tải file và tạo lệnh.
- Kiểm tra MIME và nội dung thật của file, giới hạn dung lượng; không thực thi JavaScript hay tệp nhúng trong PDF.
- File lưu ở vùng lưu trữ riêng, truy cập qua link có thời hạn; không công khai.
- Dùng dữ liệu giả lập khi demo; nếu dùng file thật phải ẩn tên, SĐT, email trước khi gửi LLM/OCR bên ngoài.
- API key lưu trong biến môi trường, không commit lên GitHub.

## 3. Kế hoạch (Plan)

### Các bước thực hiện

1. Chốt schema ticket, file PDF và trường trích xuất (5h)
2. API upload + lưu file + job xử lý bất đồng bộ (6h)
3. Đọc PDF văn bản và OCR bản scan (8h)
4. Order Agent trích xuất kèm trang/vùng nguồn (8h)
5. Validator + yêu cầu bổ sung (4h)
6. UI: tải file, tiến độ, trình xem PDF có highlight, form kết quả (14h)
7. Bộ PDF mẫu và đánh giá độ chính xác (5h)

### Công việc con (liên kết Backlog)

- T-017: Thiết kế schema ticket, file PDF & trường trích xuất
- T-018: API upload PDF, lưu file & job trích xuất
- T-048: Đọc PDF văn bản + OCR bản scan
- T-019: Order Agent trích xuất trường kèm vị trí nguồn
- T-020: Validator & yêu cầu bổ sung
- T-021: Màn hình tiếp nhận: tải file, tiến độ, xem PDF, form kết quả
- T-022: Bộ PDF mẫu & đánh giá độ chính xác

### Phụ thuộc

- Cần trước: state machine và audit log (Đặc tả #6) ở mức tối thiểu.
- Liên quan: Đặc tả #2 cần gán nhóm sản phẩm (product_group) từ tên sản phẩm để lấy hệ số mật độ.
- Nguồn lực: API key LLM; thư viện đọc PDF và OCR có gói tiếng Việt; 15–20 PDF mẫu từ đối tác (đã ẩn danh), có cả bản scan.

### Timeline dự kiến

Sprint 1 → Sprint 3 (Tuần 1: schema; Tuần 2: upload, đọc PDF/OCR, validator; Tuần 3: Order Agent, UI, bộ PDF mẫu). Tổng dự kiến ~50 giờ. [Điền ngày cụ thể khi chốt lịch dự án]

### Kế hoạch kiểm thử

- TC1: PDF văn bản đầy đủ → lệnh DRAFT đủ 8 trường, mỗi trường có trang và vùng nguồn.
- TC2: PDF scan → OCR chạy; trường tin cậy thấp được gắn nhãn, lệnh giữ DRAFT với `NEEDS_REVIEW`.
- TC3: PDF thiếu liều và giờ trả → yêu cầu bổ sung đúng 2 trường, nút tạo lệnh bị khóa.
- TC4: PDF chứa 2 ticket → 2 lệnh nháp.
- TC5: file > 10 MB / không phải PDF / có mật khẩu → báo lỗi đúng mã.
- TC6: bản scan không đọc được → chuyển nhập tay, file vẫn xem được.
- TC7: đơn vị lb/inch → quy đổi đúng.
- TC8: giờ trả ≤ giờ đến → lỗi dưới trường.
- TC9: LLM timeout → cho nhập tay.
- TC10: thao tác toàn bộ bằng bàn phím; trình đọc màn hình đọc được lỗi của từng trường.
- TC11: PDF đủ trường, mọi vùng tin cậy ≥ 0,9 → tự vào FEASIBILITY_CHECK và có lịch, không cần bấm xác nhận (`AUTO_ACCEPTED`).
- TC12: trường tin cậy 0,8–0,9 hoặc ưu tiên suy luận → vẫn có lịch, có cảnh báo tiếp nhận mở (`ACCEPTED_WITH_WARNINGS`).
- TC13: người sửa/xác nhận trường tin cậy thấp → trường thành MANUAL, submit được.
- TC14: file nhiều ticket không chắc ranh giới → `NEEDS_REVIEW`.

Nghiệm thu: pass toàn bộ TC + đạt ngưỡng chính xác trên bộ PDF mẫu.

### Kế hoạch triển khai

Release cùng bản Demo 1 (cuối Sprint 3) trên staging. OCR đặt sau feature flag để tắt được nếu chậm khi demo; tab "Dán nội dung" và chế độ nhập tay luôn bật làm dự phòng.

### Tiêu chí thành công

- FR 01, FR 02 đạt tiêu chí nghiệm thu.
- Toàn bộ PDF trong seed dataset chuyển thành lệnh hợp lệ hoặc sinh đúng yêu cầu bổ sung.
- PDF văn bản 1 trang → hiện form kết quả dưới 10 giây.
- Không lệnh nào vào FEASIBILITY_CHECK khi thiếu trường bắt buộc.

### Rủi ro và Cách giảm thiểu

- OCR tiếng Việt kém trên bản scan → gắn nhãn tin cậy thấp, bắt buộc xác nhận; khuyến nghị khách gửi PDF gốc.
- Ngưỡng tin cậy đặt sai → AUTO cho qua số liệu sai: đo tỷ lệ AUTO sai trên bộ mẫu (T-022), bắt đầu ngưỡng chặt, nới dần.
- Mẫu PDF của khách đa dạng → xin mẫu từ đối tác ngay tuần 1; dùng LLM thay vì template cứng.
- LLM trích sai số liệu (nhầm 120 thùng với 120 kg) → validator + highlight vùng nguồn để đối chiếu nhanh.
- Xử lý PDF/OCR chậm → job bất đồng bộ, cho chạy nền.
- File chứa thông tin nhạy cảm → ẩn danh khi gửi ra ngoài, lưu trữ riêng.

## Task con & trạng thái

| Task | Nội dung | Sprint | Dự kiến (giờ) | Owner | Trạng thái |
|---|---|---|---|---|---|
| T-017 | Thiết kế schema ticket, file PDF & trường trích xuất | 1 | 5 | — | Chờ review |
| T-018 | API upload PDF, lưu file & job trích xuất | 2 | 6 | — | Chờ review |
| T-048 | Đọc PDF văn bản + OCR bản scan | 2 | 8 | — | Chờ review |
| T-019 | Order Agent trích xuất trường kèm vị trí nguồn | 3 | 8 | — | Chờ review |
| T-020 | Validator & yêu cầu bổ sung | 2 | 4 | — | Chờ review |
| T-021 | Màn hình tiếp nhận: tải file, tiến độ, xem PDF, form kết quả | 3 | 14 | — | Chờ review |
| T-022 | Bộ PDF mẫu & đánh giá độ chính xác | 3 | 5 | — | Đang làm |
| T-055 | Xóa lệnh nháp | 5 | 2 | — | Chờ review |

## Nhật ký

- 23/09/2026: Tạo từ Đặc tả #1.
- 25/09/2026: Chuyển sang lộ trình 6 tuần (6 sprint); cập nhật sprint của task con và timeline.
- 26/09/2026: Đổi kiến trúc xác nhận ticket (ADR-0007): chỉ HITL khi độ tin cậy thấp, không rõ ràng → cảnh báo cho người; thêm TC11–TC14, `review_status`, `intake_warnings`. Đã có `assess` + nhánh trong `intake_graph`; còn API/DB/UI.
- 30/09/2026 (T-017): Thêm 7 bảng ở `src/modules/intake/models.py`, bật Alembic (`migrate_db()` lúc khởi động; DB cũ tạo bằng `create_all` được stamp baseline `0001` rồi nâng lên `0002`). Quyết định khi triển khai, **cần chốt để cập nhật mục Mô hình dữ liệu**:
  - `intake_warnings.created_at` — thêm vì `GET /api/intake-warnings` (specs/api-contracts.md) trả `created_at`; thêm `clarification_requests.created_at` cho đồng bộ.
  - Giá trị enum chưa có trong đặc tả: `ingest_jobs.status` = QUEUED/RUNNING/SUCCEEDED/FAILED; `clarification_requests.status` = OPEN/ANSWERED; `intake_warnings.code` dùng `FlagCode` của cổng tin cậy.
  - `progress` của ingest job suy ra từ `step`, không lưu cột. `work_orders.ticket_id` unique (1 ticket → 1 lệnh). `ticket_files.sha256` không unique (file trùng chỉ cảnh báo, BR-13).
  - `field_extractions.value` là JSON (quy cách lưu `{length, width, height}`), `bbox` = `[x0, y0, x1, y1]` theo toạ độ trang PDF.
  - Enum lưu dạng VARCHAR (`native_enum=False`) để SQLite và PostgreSQL giống nhau.
- 30/09/2026 (T-018): `POST /api/tickets/upload` + `GET /api/ingest-jobs/{job_id}` (quyền `UPLOAD_TICKET`: Kinh doanh / Điều phối). Thêm `python-multipart` (ADR-0009, Proposed). Quyết định khi triển khai:
  - Upload đọc theo chunk, vượt `MAX_UPLOAD_MB` → 413; nhận diện PDF bằng chữ ký `%PDF-` trong 1024 byte đầu (không tin `Content-Type`) → sai thì 415. Lỗi thì không tạo bản ghi, không để lại file. File lưu `UPLOAD_DIR/<file_id>.pdf`, chỉ giữ basename của tên gốc.
  - **422 cho PDF có mật khẩu / hỏng / > 20 trang chưa làm** — cần thư viện PDF, chốt ở T-048 (kiểm tra ngay lúc upload để giữ đúng contract).
  - Job chạy bằng `BackgroundTasks` với session riêng; các bước cắm vào qua `IngestStage` (`get_ingest_stages`). Chưa có pipeline (T-048/T-019) → job đứng ở `QUEUED` / `UPLOADED`.
  - `progress` theo bước đã tới: UPLOADED 25, READING 50, DETECTING 75, EXTRACTING 90, DONE/FAILED 100. Lỗi `IngestError(code)` → FAILED kèm `error_code` (vd `OCR_FAILED`); lỗi không mong đợi → FAILED, `error_code = null`. Job không tồn tại → 404.
  - Ghi audit `TICKET_UPLOADED` (file_id, job_id, sha256, size_bytes).
- 30/09/2026 (T-048): Chủ dự án chốt **Gemini Flash** đọc PDF + OCR + trích xuất 8 trường (1 lời gọi/file), **độ tin cậy tạm do Gemini tự chấm**, benchmark bổ sung sau (T-022) — ADR-0010 (Proposed), thay gạch đầu dòng "không dùng độ tin cậy LLM tự khai" của ADR-0007. T-048 gồm: pypdf kiểm tra lúc upload → 422 (mật khẩu mở / hỏng / > `MAX_PDF_PAGES`; chỉ có owner password vẫn nhận), ghi `page_count`, `has_text_layer` (mọi trang có ≥ 20 ký tự), `ocr_used` (có trang scan); `check_ocr_allowed` cho `FEATURE_OCR=false`; client Gemini (`GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_TIMEOUT_S`). Lời gọi trích xuất làm ở T-019 (Gemini thay OpenAI cho Order Agent).
- 30/09/2026 (T-019): Order Agent chạy trên Gemini (ADR-0010), 1 lời gọi/file → `DocumentExtraction` (ticket + khoảng trang + `boundary_uncertain` + 8 trường có kiểu cụ thể). Job chạy đủ READING (gọi Gemini) → DETECTING (tạo `tickets`) → EXTRACTING (tạo `work_orders` DRAFT + `field_extractions`), audit `TICKET_EXTRACTED` gắn người tải file. Quyết định khi triển khai:
  - Gemini lỗi / sai schema / trang ngoài file → thử lại (xem mục 30/09 chạy thử bên dưới); vẫn lỗi hoặc không có ticket nào → job FAILED `OCR_FAILED` (nhập tay) — dùng chung mã vì đọc và trích xuất là 1 lời gọi.
  - Chuẩn hóa deterministic: giờ không có múi giờ → giờ Việt Nam (+07:00); giờ không parse được → coi như thiếu; `confidence < low_confidence_threshold` → nhãn `OCR_LOW`; quy cách lưu 1 dòng `package_dimensions_cm` và tách 3 cột work order.
  - **`field_extractions.bbox` = `[x0, y0, x1, y1]` tỷ lệ 0–1 theo trang** (đổi từ `box_2d` 0–1000 của Gemini), thay cho "toạ độ trang PDF" ghi ở T-017 — UI nhân với kích thước trang khi vẽ.
  - `review_status` để trống: validator + cổng tin cậy + yêu cầu bổ sung + cảnh báo chạy trong bước EXTRACTING ở T-020 (cờ `boundary_uncertain` hiện chỉ có trong bộ nhớ job và audit).
  - Chưa chạy thử với Gemini thật (chưa có `GEMINI_API_KEY`); test dùng Gemini giả. Đã kiểm tra SDK chuyển được `DocumentExtraction` sang schema Gemini.
- 30/09/2026 (T-019, chạy thử Gemini thật với 3 PDF giả lập: phiếu văn bản số, file 2 email/2 ticket có inch/lb và "gấp"/"mai", bản scan JPEG):
  - Trích xuất đúng toàn bộ giá trị (quy đổi đơn vị, ngày tương đối, 2 ticket, không đoán trường thiếu); vùng nguồn `box_2d` trúng đúng ô trên bản scan.
  - `gemini-3.8-flash` trả 503 quá tải ở mọi lần gọi → đổi mặc định sang `gemini-3.5-flash`; thử lại tối đa 3 lần (tối đa 4 lời gọi), lỗi tạm thời 429/5xx chờ 1 → 2 → 4 s, sai schema thử lại ngay. `3.5-flash` cũng thỉnh thoảng 503, backoff cứu được.
  - Prompt quy định rõ `source_kind`: đổi định dạng ngày / "Thường" → NORMAL vẫn là VERBATIM; CONVERTED chỉ khi đổi đơn vị đo → hết cảnh báo thừa trên bản scan. Tắt AFC của SDK (không dùng tool).
  - **Rủi ro còn mở:** (1) `confidence` tự chấm gần như hằng số (0,95–0,99; 0,9–0,95 với giá trị suy luận), kể cả bản scan → cần bản scan mờ thật trong T-022; (2) độ trễ 1 lời gọi 9–28 s (thêm thời gian chờ khi 503) → chưa đạt "PDF 1 trang < 10 s"; trường hợp xấu nhất 4 lời gọi × `GEMINI_TIMEOUT_S` (60 s).
- 30/09/2026 (T-020): Bước EXTRACTING chạy validator + cổng tin cậy (`run_gate`, `record_gate`): thiếu/sai trường → DRAFT `NEEDS_CLARIFICATION` + `clarification_requests`; tin cậy thấp / không chắc ranh giới → DRAFT `NEEDS_REVIEW`; WARN / AUTO → tự vào FEASIBILITY_CHECK qua `transition_work_order` (Orchestration, audit `WORK_ORDER_STATE_CHANGED`, actor = người tải file), WARN tạo `intake_warnings`. File trùng sha256 → cảnh báo `POSSIBLE_DUPLICATE`. API: PATCH, submit, `GET /api/intake-warnings`, ack (contract đã bổ sung shape `WorkOrderReview` và các mã 409). Quyết định khi triển khai:
  - Thêm cột `tickets.boundary_uncertain` (migration `0003`) — cần để UI hiện lý do và để tính lại cổng khi người sửa.
  - PATCH chỉ cho đơn DRAFT (409 nếu đã qua — sửa đơn đã có lịch cần plan version, ADC-003/006). Trường gửi lên → `MANUAL` (gửi đúng giá trị cũ = xác nhận, TC13), giữ trang/vùng nguồn. Sau PATCH: còn lỗi → `NEEDS_CLARIFICATION`, hết lỗi → `NEEDS_REVIEW` chờ người submit (không tự đi tiếp, không tạo cảnh báo); câu hỏi bổ sung đã có trường → `ANSWERED`.
  - Submit: còn lỗi hoặc còn trường REVIEW chưa `MANUAL` → 422; cờ cấp ticket (ranh giới) được coi là đã xác nhận khi người bấm submit (TC14). `review_status` giữ nguyên để biết vì sao đơn cần người.
  - Câu hỏi bổ sung hiện là mẫu cố định theo trường/mã lỗi; khối "AI soạn câu hỏi gửi khách" để lại cho UI (T-021) nếu còn cần.
  - `state_history` chưa có (T-041) — chuyển trạng thái mới ghi audit.
  - **Cần ADC-002 bổ sung:** `dose_factor` cho 5 và 25 kGy đang `null` → mọi ticket 5/25 kGy bị hỏi lại "liều không có trong danh mục" (chạy thử Gemini thật đã gặp với ticket 5 kGy).
- 30/09/2026 (T-021): Chủ dự án chốt **không highlight vùng nguồn** (không thêm thư viện render PDF): màn xác nhận nhúng trình xem PDF của trình duyệt (`GET /api/files/{id}`, mở đúng trang ticket), mỗi trường hiện "Trang N · nhãn nguồn" + đoạn nguồn dạng chữ. Contract đã đổi trước (bỏ `/pages/{n}`, thêm `/api/work-orders/{id}/intake`, chốt shape `POST /api/tickets`). Đã làm:
  - `/intake`: tab "Tải file PDF" (kéo thả / chọn file, kênh nhận, kiểm tra 10 MB phía client, tiến độ 4 bước poll job 1 s, nhiều ticket → danh sách lệnh, 1 ticket → mở thẳng), tab "Dán nội dung" (`POST /api/tickets` TEXT — Order Agent chạy đồng bộ, cùng cổng như PDF), "Nhập tay" (lệnh DRAFT trống), lỗi 413/415/422/`OCR_FAILED` kèm lối thoát nhập tay; thẻ "Cảnh báo tiếp nhận" (danh sách mở + "Đã xem").
  - `/intake/[id]`: tài liệu gốc (PDF / văn bản dán / nhập tay) + form 8 trường theo 3 nhóm, nhãn nguồn, lỗi ngay dưới trường (`aria-describedby`, `aria-invalid`), tóm tắt lỗi đầu form có link tới trường, trường tin cậy thấp viền đỏ + "Xác nhận giá trị này" (→ MANUAL), câu hỏi bổ sung + "Sao chép câu hỏi", "Lưu nháp" / "Xác nhận & tạo lệnh" (khóa khi còn lỗi), banner cảnh báo cho đơn WARN, banner thành công cho đơn đã qua DRAFT.
  - Chạy thử thật (backend + frontend tách riêng, Gemini thật): upload qua proxy Next → job → màn thiếu trường, màn WARN (trùng file), nhập tay; ảnh chụp khớp thiết kế. Giờ hiển thị/nhập theo giờ Việt Nam (UTC+7).
  - **Chưa làm / hạn chế:** câu hỏi bổ sung là mẫu cố định (chưa "AI đề xuất"); danh sách file mẫu cho demo chờ T-022; TC10 (bàn phím, trình đọc màn hình) mới đảm bảo bằng control gốc + nhãn/ARIA, chưa kiểm bằng trình đọc màn hình thật.
  - **Key Gemini hiện là gói miễn phí (20 request / model)** — hết quota trả 429; retry hiện gọi thêm 3 lần dù không thể thành công → đề xuất không retry khi 429 `RESOURCE_EXHAUSTED`.
- 30/09/2026 (T-022): Bộ mẫu `src/seed/pdfs/` — 16 PDF giả lập (10 văn bản số, 6 scan chất lượng giảm dần: ảnh nhỏ, JPEG nén, nghiêng 0,8–2,5°), 17 ticket, phủ TC1, TC3, TC4, TC7, TC8, liều ngoài danh mục, 1 ticket trải 2 trang, email tiếng Anh, đơn vị gam, ngày tương đối; đáp án `answers.json` sinh từ `eval/intake/samples.py`. Công cụ: `eval/intake/build_samples.py` (Chrome + `sips`, chỉ máy dev), `scoring.py` (chấm sau chuẩn hóa: độ chính xác trường theo loại, phát hiện trường thiếu, trang nguồn, khoảng trang ticket, quyết định cổng, **tỷ lệ AUTO sai**, độ trễ), `run_eval.py` (`make eval-intake`, cache kết quả thô theo model để chạy tiếp khi hết quota).
  - **Chưa có số đo:** key Gemini gói miễn phí đã hết quota `gemini-3.5-flash` (429 `RESOURCE_EXHAUSTED`, 20 request) → cần chạy `make eval-intake` khi quota hồi hoặc dùng key trả phí, rồi điền `eval/results/report.md` và hiệu chỉnh ngưỡng. Còn thiếu: bản scan thật từ đối tác (bộ hiện tại là scan mô phỏng).
- 01/10/2026 (T-021): Chủ dự án bỏ **tab "Dán nội dung"** và ô **"Kênh nhận"** khỏi màn Tiếp nhận đơn — chỉ còn tải PDF + "Nhập tay" làm dự phòng. Backend giữ nguyên (`POST /api/tickets` TEXT, trường `channel` tùy chọn) vì không ảnh hưởng UI; màn xác nhận vẫn hiển thị được ticket TEXT cũ.
- 02/10/2026 (T-055): Thêm xóa lệnh nháp — `DELETE /api/work-orders/{id}` (quyền `UPLOAD_TICKET`, chỉ DRAFT, khác → 409) + nút "Xóa nháp" có bước xác nhận trên màn xác nhận lệnh. Quyết định khi triển khai:
  - Xóa cứng (không thêm trạng thái mới vào state machine): lệnh DRAFT chưa vào lịch, chưa ảnh hưởng khách; dấu vết giữ trong audit `WORK_ORDER_DELETED` (work_order_id, ticket_id, source, file_id, bản chụp 8 trường).
  - Xóa luôn ticket (1 ticket → 1 lệnh) và `field_extractions` / `clarification_requests` / `intake_warnings`; **giữ** `ticket_files` + file PDF vì 1 file có thể chứa nhiều ticket và là chứng từ gốc. Job trích xuất sau đó không còn liệt kê lệnh đã xóa.
- 02/10/2026: Chỉ Kinh doanh tiếp nhận ticket — bỏ quyền `UPLOAD_TICKET` của PLANNER (specs/user-roles.md, permissions.py, roles.ts); Điều phối không còn menu / trang Tiếp nhận đơn.
- 02/10/2026 (T-055, bổ sung): Kanban lệnh — thẻ ở trạng thái DRAFT có icon thùng rác (chỉ Kinh doanh), xác nhận ngay trên thẻ rồi gọi `DELETE /api/work-orders/{id}`; bấm thẻ (Kinh doanh) mở màn chi tiết lệnh. Thẻ cột Nháp bỏ nút kiểm tra rủi ro (xếp lịch tự kiểm tra, BR-07).
