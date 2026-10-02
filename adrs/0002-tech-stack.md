# ADR-0002: Tech stack

| Trường | Giá trị |
|---|---|
| Trạng thái | **Accepted** |
| Ngày | 25/09/2026 |
| Liên quan | T-003, ADR-0001, ADR-0003 |

## Bối cảnh

Các đặc tả đã nêu một số công cụ; phần còn lại chưa chốt. Repo được sinh từ **AI20K Agent Template** (FastAPI + LangGraph + OpenAI, Docker, GitHub Actions, hook ghi log AI bắt buộc để chấm bài). Thư viện PDF/OCR đề xuất trong ADC-001 đều là Python.

## Các phương án

1. **Giữ stack template (Python) + frontend Next.js** — tận dụng khung đã chạy, CI, Docker, hướng dẫn chương 4–7 của Technical Book; PDF/OCR cùng ngôn ngữ với backend.
2. Giữ stack template + frontend Streamlit — nhanh nhưng khó làm Kanban, timeline 2 line và trình xem PDF có highlight.
3. Backend Node/TypeScript — đồng nhất ngôn ngữ với frontend nhưng phải bỏ khung template và tách service PDF/OCR riêng.

## Quyết định

Chọn **1**.

| Lớp | Lựa chọn | Ghi chú |
|---|---|---|
| Backend | Python 3.11 + FastAPI + Uvicorn | Modular monolith, entry `src.main:app` |
| Điều phối agent | LangGraph (graph do code định nghĩa) | Orchestrator là code, không phải LLM tự do (ADR-0001) |
| LLM provider | OpenAI qua `langchain-openai`, mặc định `gpt-4o-mini` | Bắt buộc structured output / JSON schema; nhiệt độ 0 cho trích xuất |
| Cấu hình giả định | YAML (`src/config/throughput.yaml`) đọc bằng PyYAML | ADC-002 |
| Đọc PDF văn bản | PyMuPDF hoặc pdfplumber | Chốt khi làm T-048 |
| OCR bản scan | Tesseract (gói tiếng Việt) hoặc dịch vụ OCR | Sau feature flag |
| Database | SQLite (dev/test) → PostgreSQL (staging/prod), SQLAlchemy 2 + Alembic | Cần JSON column (breakdown, bbox, payload) |
| Job queue | FastAPI `BackgroundTasks` trong MVP | Nâng lên hàng đợi riêng (vd RQ/Celery) nếu job PDF/OCR chậm → ADR mới |
| Lưu file | Thư mục cục bộ ngoài web root (dev), object storage có link hết hạn (prod) | Không public |
| Frontend | Next.js + TypeScript (thư mục `frontend/`) | Timeline: FullCalendar hoặc vis-timeline (ADC-003) |
| Font UI | Fira Sans, Fira Code | ADC-001 (UI/UX) |
| Xác thực | Google OAuth 2.0 / OIDC, Authorization Code + PKCE | ADR-0006 |
| Test / lint | pytest + pytest-asyncio + httpx, ruff | `make test`, `make lint` |
| CI/CD | GitHub Actions (`.github/workflows/ci.yml`) | ruff + pytest mỗi push/PR |
| Monitoring / AI log | LangSmith (tracing LLM) + hook ghi log AI của template | Sentry nếu còn thời gian |
| Hosting | Docker; backend trên Render, frontend trên Vercel | Cần staging + production |
| Solver tối ưu | OR-Tools — **để sau MVP** | ADC-003 |

## Hệ quả

- ✅ Dùng lại ngay khung chạy được, CI và Dockerfile của template.
- ✅ Một ngôn ngữ cho backend, PDF/OCR và lõi deterministic.
- ⚠️ Hai ngôn ngữ (Python + TypeScript) → contract API trong `specs/api-contracts.md` là điểm đồng bộ duy nhất.
- 🔁 Sau khi chốt, agent/thành viên chỉ dùng thư viện trong ADR này. Thêm thư viện lớn → ADR mới.
