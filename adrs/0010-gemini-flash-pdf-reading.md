# ADR-0010: Gemini Flash đọc PDF, OCR và trích xuất ticket; pypdf kiểm tra file

| Trường | Giá trị |
|---|---|
| Trạng thái | Proposed |
| Ngày | 30/09/2026 |
| Người quyết định | Chủ dự án (chốt 30/09/2026 khi làm T-048) |
| Liên quan | ADC-001, ADR-0002, ADR-0007, T-048, T-019, T-022 — T-048: pypdf + client Gemini; T-019: lời gọi trích xuất |

## Bối cảnh

ADR-0002 để ngỏ công cụ đọc PDF (PyMuPDF hoặc pdfplumber) và OCR (Tesseract hoặc dịch vụ OCR) — "chốt khi làm T-048". Khách gửi cả PDF văn bản số lẫn bản scan tiếng Việt; Tesseract cần cài binary + gói `vie` trên máy dev và Docker, và chất lượng trên bản scan tiếng Việt kém.

Gemini Flash (Gemini API) nhận PDF trực tiếp (tới 50 MB / 1000 trang), tự đọc cả trang có text layer lẫn trang scan, trả JSON theo schema. Nhưng Gemini **không trả độ tin cậy OCR theo vùng**, và logprobs không khả dụng trên các model Flash mới — trái với ADR-0007 ("độ tin cậy do code gắn, không dùng độ tin cậy LLM tự khai").

## Các phương án
1. **PyMuPDF/pdfplumber + Tesseract** (ADR-0002) — có độ tin cậy từng từ do OCR engine tính; cần binary hệ thống, OCR tiếng Việt yếu.
2. **Gemini Flash đọc toàn bộ PDF, độ tin cậy do Gemini tự chấm (tạm thời)** — 1 dịch vụ cho cả 2 loại PDF, không cần binary; độ tin cậy chưa hiệu chỉnh.
3. **Gemini Flash + độ tin cậy đối chiếu deterministic** (snippet phải có trong text layer; bản scan tối đa WARN) — bám ADR-0007 nhưng bản scan không bao giờ AUTO.

## Quyết định

Chọn **2**, tạm thời, cho tới khi có số liệu benchmark (T-022):

- **Đọc / OCR / trích xuất (Order Agent):** `google-genai` gọi Gemini Flash (mặc định `gemini-3.5-flash`, đổi qua `GEMINI_MODEL`), gửi nguyên file PDF, `temperature = 0`, **1 lời gọi cho cả file**, output ràng buộc schema: danh sách ticket (khoảng trang, cờ không chắc ranh giới), mỗi ticket 8 trường `{value, source_kind, page, snippet, box_2d, confidence}` (`OrderExtraction`). Sai schema / lỗi API → thử lại tối đa 3 lần (lỗi tạm thời 429/5xx chờ 1 → 2 → 4 s) rồi job FAILED (UI chuyển nhập tay). Thay OpenAI (ADR-0002) cho Order Agent; OpenAI giữ cho các agent khác.
- **Độ tin cậy:** `confidence` từng trường do **Gemini tự chấm** (0–1), dùng thẳng với ngưỡng `ocr.low_confidence_threshold` / `warn_confidence_threshold` của ADR-0007. Thay thế riêng gạch đầu dòng "không dùng độ tin cậy LLM tự khai" của ADR-0007; phần còn lại của ADR-0007 (3 mức, cờ, ngưỡng cấu hình) giữ nguyên.
- **Kiểm tra file (deterministic):** `pypdf` (BSD, thuần Python) đếm trang, phát hiện PDF có mật khẩu / hỏng / > `MAX_PDF_PAGES` ngay lúc upload → `422`, và xác định trang nào có text layer (`ticket_files.has_text_layer`, `ocr_used`).
- `FEATURE_OCR=false` → file có trang scan bị FAILED `OCR_FAILED` (nhập tay), PDF văn bản số vẫn đọc.

## Hệ quả
- ✅ Không cần cài Tesseract; bản scan tiếng Việt đọc tốt hơn; 1 lời gọi cho cả file.
- ⚠️ **Độ tin cậy tự khai chưa hiệu chỉnh** → rủi ro AUTO cho qua số liệu sai. Bắt buộc đo **tỷ lệ AUTO sai** trên bộ PDF mẫu (T-022) trước Demo 1; nếu > 0 → siết ngưỡng hoặc chuyển sang phương án 3 (ADR mới).
- ⚠️ Gửi nguyên file PDF ra Google — không ẩn danh được trước khi gửi. Chỉ dùng PDF giả lập / đã ẩn danh cho tới khi có thỏa thuận xử lý dữ liệu với đối tác.
- ⚠️ Thêm LLM provider thứ 2 (OpenAI vẫn dùng cho Scheduler / Risk Agent) → thêm `GEMINI_API_KEY`; test giả lập Gemini, không gọi mạng.
- ⚠️ Đọc và trích xuất gộp 1 lời gọi → không tách được lỗi OCR với lỗi trích xuất; tab "Dán nội dung" (văn bản) cũng gọi Gemini với cùng schema.
- ⚠️ `box_2d` của Gemini là toạ độ xấp xỉ (chuẩn hóa 0–1000), đủ để highlight vùng, không chính xác như toạ độ text layer.
- 🔁 Việc tiếp theo: cập nhật bảng ADR-0002 (Đọc PDF, OCR) khi ADR này Accepted; T-022 benchmark và hiệu chỉnh ngưỡng.
