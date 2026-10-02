# ADR-0009: python-multipart để nhận file upload PDF

| Trường | Giá trị |
|---|---|
| Trạng thái | Proposed |
| Ngày | 30/09/2026 |
| Người quyết định | [Họ tên] |
| Liên quan | ADC-001, ADR-0002, T-018 |

## Bối cảnh

`POST /api/tickets/upload` (specs/api-contracts.md §1) nhận `multipart/form-data` gồm `file`, `channel`, `received_at`. FastAPI chỉ parse được `UploadFile` / `Form` khi có gói `python-multipart`; ADR-0002 chưa liệt kê gói này (nó nằm trong extra `fastapi[standard]`, không nằm trong `fastapi` trơn).

## Các phương án
1. **python-multipart** — dependency tùy chọn chính thức của FastAPI, thuần Python, stream file ra đĩa theo chunk (không nạp cả file vào RAM).
2. **Tự parse body** (`Request.stream()` + tự tách boundary) — không thêm gói nhưng tự viết parser multipart, dễ sai và khó bảo trì.
3. **Đổi contract sang body nhị phân** (`application/pdf`, metadata ở query) — không cần gói, nhưng phải đổi contract và UI không dùng được form upload chuẩn.

## Quyết định

Chọn **1**. Thêm `python-multipart>=0.0.18` vào `requirements.txt` (bản ≥ 0.0.18 đã vá lỗi DoS khi parse boundary).

## Hệ quả
- ✅ Giữ nguyên contract; dùng `UploadFile` chuẩn của FastAPI, đọc theo chunk để chặn file > 10 MB mà không nạp hết vào RAM.
- ⚠️ Thêm 1 gói phụ thuộc nhỏ, thuần Python.
- 🔁 Việc tiếp theo: bổ sung vào bảng ADR-0002 khi ADR này Accepted.
