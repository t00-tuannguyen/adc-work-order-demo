# ADR-0001: Kiến trúc — Multi-agent orchestrator với lõi deterministic

| Trường | Giá trị |
|---|---|
| Trạng thái | Proposed |
| Ngày | 23/09/2026 |
| Liên quan | Brief (Multi Agent Design), PRD, ADC-006 |

## Bối cảnh

Hệ thống phải xử lý đầu vào lộn xộn (ticket PDF, bản scan) và phải cho kế hoạch **tái lập được, kiểm chứng được** vì ảnh hưởng cam kết với khách. 6 tuần build, 4 thành viên.

## Các phương án

1. **LLM tự do điều phối và xếp lịch** — linh hoạt nhưng không tái lập, có thể chồng lấn slot, khó giải thích → loại.
2. **Hệ luật thuần, không AI** — tái lập tốt nhưng không đọc được ticket bán cấu trúc, không giải thích tự nhiên.
3. **Orchestrator bằng code + agent chuyên trách gọi như tool + lõi deterministic** — AI ở biên (đọc, giải thích, soạn thảo), luật ở lõi (tính toán, quyết định).

## Quyết định

Chọn **phương án 3**.

| Thành phần | Vai trò | Có dùng LLM |
|---|---|---|
| Orchestrator | Sở hữu state, gọi agent, version plan, quản lý duyệt HITL. Là nơi **duy nhất** ghi trạng thái | Không (code điều phối) |
| Order Agent | Trích xuất ticket, kiểm tra thiếu trường, theo dõi SLA giờ trả | Có (output theo JSON schema) |
| Scheduler Agent | Gọi hàm xếp lịch / tái lập lịch deterministic và **giải thích** kết quả | Chỉ để giải thích |
| Risk & Escalation Agent | Luật OK/WARN/BLOCK + tạo escalation; LLM soạn nháp thông điệp | Chỉ để soạn thảo |
| Validator | Kiểm tra mọi output LLM (schema, đơn vị, số liệu trong câu giải thích khớp dữ liệu) | Không |

Quy tắc bất biến:
- LLM không tự sinh giờ, line hay thứ tự ưu tiên.
- LLM không có quyền gọi hàm approve.
- Mọi agent có input/output schema cố định.

Kiến trúc triển khai: 1 backend (modular monolith, chia module theo context trong `specs/domains.md`) + 1 frontend + 1 database + job xử lý bất đồng bộ cho PDF/OCR. Stack cụ thể: ADR-0002; cấu trúc thư mục: ADR-0003.

## Hệ quả

- ✅ Kế hoạch tái lập được, dễ test, dễ trình bày với giám khảo.
- ✅ AI thất bại (timeout, sai schema) không làm sai lịch — chỉ rơi về nhập tay / mẫu soạn sẵn.
- ⚠️ Greedy chưa tối ưu toàn cục — chấp nhận trong MVP (xem ADR-0004).
- 🔁 Viết validator đối chiếu số liệu trong câu giải thích của LLM.
