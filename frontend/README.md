# frontend/

Next.js 16 + TypeScript (ADR-0002). Khung dựng ở T-051 (ADC-008) — phần còn lại của T-007 (layout chung cho các màn nghiệp vụ) làm tiếp trên khung này.

```bash
cd frontend
npm install
npm run dev          # http://localhost:3000 — cần backend chạy ở :8000 (make run)
npm test             # node --test: logic điều hướng / quyền (src/lib/*.test.ts)
npm run typecheck && npm run lint && npm run build
```

- **Proxy cùng origin:** `next.config.ts` chuyển `/api/*` và `/auth/*` sang `BACKEND_URL` (mặc định `http://localhost:8000`). Trình duyệt chỉ thấy origin của frontend nên cookie phiên HttpOnly `SameSite=Lax` luôn là first-party, kể cả khi frontend (Vercel) và backend (Render) ở 2 domain.
- Backend: `FRONTEND_URL=http://localhost:3000` (mặc định) để callback Google quay về đây.
- Contract: `specs/api-contracts.md`. Ma trận quyền trong `src/lib/roles.ts` chỉ để hiển thị — backend là nơi kiểm tra thật.

| Trang | Ai | Ghi chú |
|---|---|---|
| `/login` | mọi người | "Tiếp tục với Google", thông báo `?error=`, tài khoản demo (khi `FEATURE_DEMO_LOGIN`) |
| `/signup/complete`, `/pending` | PENDING | Chọn vai trò yêu cầu; chờ cấp quyền |
| `/logged-out` | mọi người | Sau đăng xuất / đăng xuất mọi thiết bị |
| `/sales` | SALES | Ước tính thời lượng + quyền; các mục khác "Chưa làm · T-xxx" |
| `/planner` | PLANNER | Ước tính, giả định vận hành |
| `/ops` | OPS_MANAGER | Giả định vận hành; duyệt/KPI chờ T-042, T-046 |
| `/admin/users` | ADMIN | Duyệt yêu cầu, cấp/đổi vai trò, vô hiệu hóa (T-052) |

- Timeline 2 line: FullCalendar hoặc vis-timeline (ADC-003).
- Font: Fira Sans / Fira Code; màu ưu tiên luôn kèm chữ (Thường – xám xanh, Khẩn – cam, VIP – hồng tím).
- Thiết kế UI: xem `docs/links.md`.
- Nhãn "Giá trị giả lập – không phải thông số vật lý thật" ở mọi nơi hiện thời lượng/giả định.
