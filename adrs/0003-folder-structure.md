# ADR-0003: Cấu trúc thư mục

| Trường | Giá trị |
|---|---|
| Trạng thái | **Accepted** |
| Ngày | 23/09/2026 (cập nhật 25/09/2026 theo ADR-0002) |

## Bối cảnh

Bản đề xuất đầu tiên dùng `src/backend/modules/…` và `src/frontend/`. Repo được sinh từ AI20K Agent Template, trong đó Dockerfile, CI và Makefile trỏ vào `src.main:app`, còn `src/agents|api|models|services` đã có sẵn. Cần một cấu trúc vừa chia module theo bounded context (`specs/domains.md`), vừa giữ khung template.

## Các phương án

1. **Đúng bản đề xuất đầu** (`src/backend/modules/…`) — phải sửa Dockerfile, CI, Makefile, import.
2. **Giữ nguyên template** (`agents/api/services/models`) — logic nghiệp vụ trộn chung trong `services/`, khó giao việc theo context.
3. **Lai**: module theo context ở `src/modules/`, giữ lớp `agents/` và `api/` của template, frontend tách ra root.

## Quyết định

Chọn **3**.

### Root
| Thư mục | Nội dung |
|---|---|
| `specs/` | Tầm nhìn, domain, vai trò, tính năng/FR/US, API contract |
| `adrs/` | Quyết định kiến trúc `NNNN-ten.md` |
| `planning/` | `backlog.md`, `sprints/sprint-NN.md` (6 sprint) |
| `tasks/` | Mỗi đặc tả tính năng 1 file `ADC-NNN-ten.md` (Động lực → Thiết kế → Kế hoạch) |
| `src/` | Mã nguồn backend |
| `frontend/` | Next.js (khởi tạo ở T-007) |
| `tests/` | pytest, cấu trúc song song với `src/modules/` |
| `docs/` | Quy trình, kịch bản demo, link, thành viên, theo dõi lỗi, sơ đồ kiến trúc; `docs/guide/` là Technical Book của template |
| `eval/` | Bằng chứng đánh giá (Metrics PRD, độ chính xác trích xuất) |
| `presentation/` | Slide, video demo |
| `scripts/` | Hook ghi log AI của template (không sửa) |

### Bên trong `src/`
```
src/
├── main.py                  # FastAPI app (src.main:app)
├── settings.py              # biến môi trường (pydantic-settings)
├── api/                     # router HTTP theo context, khớp specs/api-contracts.md
├── agents/                  # Order / Scheduler / Risk Agent: prompt + JSON schema output, graph LangGraph
├── modules/
│   ├── types.py             # Line, Priority dùng chung giữa các context
│   ├── intake/              # ADC-001: upload, PDF/OCR, validator, yêu cầu bổ sung
│   ├── estimation/          # ADC-002: estimate_duration (thuần)
│   ├── scheduling/          # ADC-003, ADC-004: scheduler, phát hiện đơn bị ảnh hưởng, reschedule
│   ├── risk/                # ADC-005: risk-check, escalation
│   ├── orchestration/       # ADC-006: state machine, plan version, luật duyệt, audit
│   ├── analytics/           # ADC-007: KPI, mô phỏng 1 vs 2 line
│   └── identity/            # ADC-008: OAuth, phiên, RBAC
├── services/                # hạ tầng dùng chung (LLM client, lưu file, DB)
├── config/
│   └── throughput.yaml      # giả định mô phỏng (ADC-002)
└── seed/
    ├── orders.json          # ≥ 5 lệnh
    ├── incidents.json       # 1 sự cố Line A cố định
    └── pdfs/                # 15–20 PDF mẫu đã ẩn danh + đáp án
```

### Quy ước đặt tên
- Task/đặc tả: `ADC-NNN-kebab-case.md`
- Việc trong backlog: `T-NNN` · User story: `US-NNN` · Lỗi: `BUG-NNN` · Mốc: `M1…M8`
- ADR: `NNNN-kebab-case.md`
- Module Python: `snake_case`; test: `tests/modules/<context>/test_*.py`

## Hệ quả
- ✅ Mỗi module ứng với 1 context → dễ giao việc cho người và AI agent.
- ✅ Giữ nguyên Dockerfile, CI, `make run/test/lint` của template.
- ⚠️ Module khác chỉ gọi qua interface public (`__init__.py`); chỉ `orchestration` được ghi trạng thái work order.
- ⚠️ `modules/*` không import `agents/` hay `api/` (lõi deterministic không phụ thuộc LLM/HTTP).
