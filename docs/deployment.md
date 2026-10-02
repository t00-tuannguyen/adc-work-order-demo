# Hướng dẫn triển khai (demo miễn phí)

Theo [ADR-0012](../adrs/0012-free-tier-demo-hosting.md): backend Render Free (Docker) · DB Neon Free (PostgreSQL) · frontend Vercel Hobby. **PDF tải lên lưu tạm** — mất sau mỗi lần deploy/restart.

## 1. Database — Neon

1. Tạo project trên neon.tech (region Singapore), copy connection string dạng `postgresql://...?sslmode=require`.
2. Không cần tạo bảng: backend chạy `alembic upgrade head` khi khởi động. `postgres://` / `postgresql://` được tự đổi sang driver psycopg 3 (`src/services/db.py`).

## 2. Backend — Render

1. Render → **New → Blueprint** → chọn repo; Render đọc `render.yaml` (Docker, plan free, health check `/health`).
   Hoặc **New → Web Service**: runtime Docker, Dockerfile `./Dockerfile`, Health Check Path `/health`, Instance Type Free.
2. Điền các biến `sync: false` trong `render.yaml`:

| Biến | Giá trị |
|---|---|
| `DATABASE_URL` | connection string Neon |
| `FRONTEND_URL`, `CORS_ORIGINS` | `https://<app>.vercel.app` |
| `OAUTH_REDIRECT_URI` | `https://<app>.vercel.app/auth/google/callback` (qua proxy frontend để cookie phiên là first-party) |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | OAuth client riêng cho môi trường này; thêm redirect URI trên vào Google Console |
| `ALLOWED_EMAIL_DOMAINS`, `BOOTSTRAP_ADMIN_EMAILS` | theo đội |
| `OPENAI_API_KEY`, `GEMINI_API_KEY`, `LANGCHAIN_API_KEY` | key thật |

3. Render tự đặt `PORT`; Dockerfile đọc `$PORT` (mặc định 8000 khi chạy local).
4. Kiểm tra: `https://<service>.onrender.com/health` → `{"status":"ok","env":"staging"}`.

## 3. Frontend — Vercel

1. Import repo, Root Directory `frontend`.
2. Environment Variable `BACKEND_URL=https://<service>.onrender.com` — rewrites đọc lúc **build**, đổi URL backend phải redeploy frontend.

## 4. Giữ service thức

Render Free ngủ sau 15 phút không có request (lần gọi đầu ~50 s). Tạo cron trên cron-job.org gọi `GET /health` mỗi 10 phút. Trước demo vẫn mở app trước vài phút.

## 5. Sau mỗi lần deploy

- PDF cũ mất → màn xác nhận báo "File gốc không còn trên server"; tải lại ticket demo nếu cần xem PDF.
- Reset dữ liệu demo: `POST /api/demo/reset` (bật bằng `DEMO_RESET_ENABLED=true`).

## Giới hạn

- 512 MB RAM (backend lúc rảnh ~150 MB) — xem log nếu bị OOM khi đọc PDF lớn.
- Job PDF chạy bằng `BackgroundTasks`: restart giữa chừng → job dừng, tải lại file.
- Không dùng cho dữ liệu khách thật.
