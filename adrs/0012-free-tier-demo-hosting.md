# ADR-0012: Hosting miễn phí cho demo — Render Free + Neon + Vercel Hobby, file PDF lưu tạm

| Trường | Giá trị |
|---|---|
| Trạng thái | Proposed |
| Ngày | 02/10/2026 |
| Người quyết định | Chủ dự án |
| Liên quan | T-013, T-009, ADR-0002, ADC-001 (T-021) |

## Bối cảnh

ADR-0002 chốt backend Docker trên Render, frontend trên Vercel, PostgreSQL cho staging/prod, file tải lên lưu ở object storage có link hết hạn (prod). Giai đoạn demo/đánh giá cuối kỳ cần chạy **không tốn phí**:

- Render Free: filesystem tạm (mất khi deploy / restart / ngủ sau 15 phút không có request), không gắn được Render Disk, 512 MB RAM.
- Render Postgres Free bị xóa sau 30 ngày.
- Object storage miễn phí (Cloudflare R2, Supabase Storage) cần thêm thư viện (`boto3`) hoặc bị tạm dừng khi không dùng.

PDF gốc được dùng ở 2 chỗ: job trích xuất (ngay sau khi tải lên) và trình xem PDF ở màn xác nhận (`GET /api/files/{id}`, T-021).

## Các phương án

1. **Lưu tạm trên filesystem của Render Free** — không đổi code lưu file, không thêm thư viện; file mất sau mỗi lần deploy/restart → màn xác nhận không xem được PDF gốc của đơn cũ.
2. **Lưu PDF trong Postgres (bytea)** — bền, không thêm thư viện; cần migration + sửa 3 chỗ đọc/ghi, tốn dung lượng DB miễn phí.
3. **Object storage miễn phí** — đúng hướng ADR-0002 nhưng thêm thư viện/tài khoản, có thẻ thanh toán hoặc bị pause.

## Quyết định

Chọn **1** cho môi trường demo:

| Lớp | Lựa chọn |
|---|---|
| Backend | Render Free Web Service (Docker, `Dockerfile` hiện có), health check `/health` |
| Database | Neon Free (PostgreSQL), qua `DATABASE_URL`; migration chạy lúc khởi động (`migrate_db`) |
| File PDF | `UPLOAD_DIR` trên filesystem tạm của container — **không bền** |
| Frontend | Vercel Hobby, proxy `/api` + `/auth` sang backend (`BACKEND_URL`, `next.config.ts`) |
| Giữ service thức | Ping `/health` định kỳ (vd cron-job.org, 10 phút) |

Màn xác nhận xử lý file không còn: báo "file gốc không còn trên server", Sales đối chiếu bằng trang + đoạn nguồn hiện cạnh từng trường (đã có từ T-021).

## Hệ quả

- ✅ Chi phí 0; không thêm thư viện ngoài ADR-0002 (`psycopg2-binary` đã nằm trong lựa chọn PostgreSQL).
- ⚠️ PDF gốc mất sau mỗi lần deploy/restart; mở app và tải lại ticket demo sau mỗi lần deploy.
- ⚠️ Job xử lý PDF chạy bằng `BackgroundTasks` — restart giữa chừng thì job dừng ở trạng thái đang chạy, phải tải lại file.
- ⚠️ 512 MB RAM có thể không đủ cho LangChain + LangGraph + google-genai khi đọc PDF lớn → theo dõi log OOM; vượt thì lên gói trả phí.
- ⚠️ Không dùng cho dữ liệu khách thật.
- 🔁 Việc tiếp theo: khi có khách thật → ADR mới chọn phương án 2 hoặc 3 (supersede ADR này).
