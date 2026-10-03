# ADR-0013: Tùy chọn OpenAI cho Order Agent (bên cạnh Gemini)

| Trường | Giá trị |
|---|---|
| Trạng thái | Proposed |
| Ngày | 03/10/2026 |
| Người quyết định | Chủ dự án (yêu cầu 03/10/2026 khi làm T-059) |
| Liên quan | ADC-001, ADR-0002, ADR-0010, T-019, T-059 |

## Bối cảnh

ADR-0010 chọn Gemini Flash cho Order Agent (đọc PDF, OCR, trích xuất 8 trường). Ngày 03/10/2026 Gemini trả `503 UNAVAILABLE` ("model is currently experiencing high demand") ở cả 4 lần thử của nhiều job liên tiếp → mọi job FAILED `OCR_FAILED`, người dùng phải nhập tay. Dự án đã có `OPENAI_API_KEY` và `langchain-openai` (ADR-0002) cho Scheduler / Risk Agent; các model OpenAI có vision (vd `gpt-4o-mini`) nhận file PDF trực tiếp qua Chat Completions (file input: text + ảnh từng trang).

## Các phương án
1. **Giữ chỉ Gemini** — đơn giản; nhưng Gemini quá tải là tiếp nhận PDF dừng hẳn.
2. **Chọn provider bằng cấu hình (`ORDER_AGENT_PROVIDER`)** — đổi provider không cần sửa code; cùng prompt, schema, luật thử lại; không thêm thư viện.
3. **Tự chuyển sang provider dự phòng khi provider chính lỗi** — chịu lỗi tốt nhất; nhưng kết quả cùng 1 file có thể đến từ 2 model khác nhau, khó so benchmark (T-022), cần cả 2 key.

## Quyết định

Chọn **2**:

- `ORDER_AGENT_PROVIDER = gemini` (mặc định, giữ nguyên ADR-0010) | `openai`.
- `openai`: `OpenAIOrderAgent` gọi qua `langchain-openai` (`get_llm`), model `OPENAI_ORDER_MODEL` (rỗng → `MODEL_NAME`), timeout `OPENAI_ORDER_TIMEOUT_S` (mặc định 60 s). Gửi nguyên file PDF (base64) + cùng `SYSTEM_PROMPT`, output `with_structured_output(DocumentExtraction)`, `temperature` theo `LLM_TEMPERATURE` (0).
- Luật thử lại dùng chung với Gemini: tối đa 3 lần; lỗi tạm thời (429/5xx, mất kết nối/timeout) chờ 1 → 2 → 4 s; sai schema / trang ngoài file / model từ chối → thử lại ngay; hết lượt → `ExtractionFailedError` (nhập tay).
- Chưa có key của provider đã chọn → không có Order Agent (job nằm QUEUED, `POST /api/tickets` TEXT → `503`), như hiện tại với Gemini.

## Hệ quả
- ✅ Gemini quá tải → đổi 1 biến môi trường + restart là tiếp nhận PDF chạy lại; không thêm thư viện.
- ⚠️ `confidence` và `box_2d` vẫn do model tự khai (ADR-0010) — chưa hiệu chỉnh cho OpenAI; tọa độ vùng của OpenAI kém chính xác hơn Gemini → highlight có thể lệch. Chạy benchmark T-022 với `ORDER_AGENT_PROVIDER=openai` trước khi dùng cho demo chính.
- ⚠️ Gửi nguyên file PDF ra OpenAI — cùng ràng buộc dữ liệu như ADR-0010: chỉ PDF giả lập / đã ẩn danh.
- ⚠️ Model phải đọc được PDF (vision); model chỉ có text sẽ lỗi 400 → job FAILED.
- 🔁 Việc tiếp theo: T-022 benchmark cả 2 provider; cân nhắc phương án 3 (tự chuyển dự phòng) bằng ADR mới nếu cần.
