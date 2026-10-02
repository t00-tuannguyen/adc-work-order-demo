# src/

Cấu trúc theo `adrs/0003-folder-structure.md`, stack theo `adrs/0002-tech-stack.md`.

| Đường dẫn | Nội dung | Trạng thái |
|---|---|---|
| `main.py`, `settings.py` | FastAPI app, biến môi trường | ✅ |
| `config/throughput.yaml` | Tham số mô phỏng (ADC-002) — còn TODO chờ chốt (T-023) | ⚠️ |
| `modules/estimation/` | `estimate_duration` + đọc cấu hình | ✅ có test |
| `modules/scheduling/` | Earliest feasible, phát hiện đơn bị ảnh hưởng, thứ tự tái lập lịch | ✅ có test · `reschedule` còn TODO (T-033) |
| `modules/orchestration/` | State machine, luật duyệt HITL | ✅ có test · audit/plan version (T-041, T-042) |
| `modules/intake/` | Schema 8 trường, validator | ✅ có test · upload/PDF/OCR (T-018, T-048) |
| `modules/identity/` | Vai trò, ma trận quyền | ✅ có test · OAuth/phiên (T-049, T-050) |
| `modules/risk/`, `modules/analytics/` | Enum + mô tả việc cần làm | ⏳ T-036–T-039, T-044–T-046 |
| `agents/` | Schema output agent, graph điều phối luồng tiếp nhận, Order Agent (stub) | ⏳ T-019, T-034, T-038, T-043 |
| `api/` | `/api/estimate`, `/api/config/throughput` | ⏳ các endpoint còn lại |
| `seed/` | Seed dataset demo (≥ 5 lệnh + 1 sự cố Line A cố định) | ⏳ T-025 |
