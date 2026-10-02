# ADC-008: Đăng ký, đăng nhập và đăng xuất bằng tài khoản Google

> Nguồn: sheet *Đặc tả tính năng* — Đặc tả #8 trong `team_project_management_template.xlsx`.

| Trường | Giá trị |
|---|---|
| Đặc tả | #8 |
| User Story | US-017, US-018, US-019, US-020 |
| Functional Requirement (PRD) | — (bổ sung ngoài PRD) |
| Ưu tiên | P1 (đề xuất — ngoài PRD) |
| Sprint | 5 |
| Người viết | [Họ tên người phụ trách] |
| Ngày tạo / cập nhật | 24/09/2026 / 25/09/2026 |
| Trạng thái | Bản nháp |

## References
- [specs/features.md](../specs/features.md)
- [specs/api-contracts.md](../specs/api-contracts.md)
- [specs/domains.md](../specs/domains.md)
- [specs/user-roles.md](../specs/user-roles.md)
- [AGENTS.md](../AGENTS.md)

## 1. Động lực (Motivation)

### Vấn đề cần giải quyết

Hệ thống có phân quyền (Kinh doanh, Điều phối, Quản lý vận hành) và audit log ghi ai làm gì, nhưng Đặc tả #1–#7 đang dùng tài khoản demo dùng chung. Cần xác thực thật để biết đúng người thao tác, chặn người ngoài và áp dụng luật duyệt (người đề xuất không tự duyệt). Tự quản mật khẩu thì tốn công (quên mật khẩu, khóa tài khoản) và rủi ro lộ mật khẩu.

### Người dùng mục tiêu

- Nhân viên Kinh doanh, Điều phối, Quản lý vận hành: đăng nhập hằng ngày.
- Quản trị hệ thống (admin): duyệt tài khoản mới, cấp hoặc thu hồi vai trò.

Hiện tại: tài khoản demo dùng chung, không truy vết được người thật.

### Mục tiêu kỳ vọng

- Đăng ký lần đầu bằng Google: tạo hồ sơ từ tên, email, ảnh; gửi yêu cầu vai trò; chỉ dùng được sau khi admin cấp quyền.
- Đăng nhập 1 chạm bằng Google, hệ thống không lưu mật khẩu.
- Đăng xuất kết thúc phiên ngay trên thiết bị hiện tại.
- Chỉ email thuộc tên miền được phép (cấu hình) mới đăng ký được.
- Chỉ số: 100% thao tác trong audit log gắn với người dùng thật; 0 truy cập dữ liệu từ tài khoản chưa được cấp quyền; đăng nhập < 5 giây (không tính thời gian thao tác trên trang Google).

### Phương án thay thế đã xem xét

- Email + mật khẩu tự quản: phải làm quên mật khẩu, băm mật khẩu, khóa tài khoản; rủi ro lộ mật khẩu.
- Magic link qua email: không cần mật khẩu nhưng phụ thuộc dịch vụ gửi mail, chậm.
- SSO doanh nghiệp (SAML / Microsoft Entra ID): phù hợp nếu ADC dùng Microsoft; để sau MVP.

**→ Chọn:** Google OAuth 2.0 / OpenID Connect (Authorization Code + PKCE); vai trò do hệ thống tự quản.

## 2. Thiết kế (Design)

### Kiến trúc hệ thống

Luồng: nút "Tiếp tục với Google" → backend tạo state, nonce, PKCE rồi chuyển hướng tới Google → người dùng đồng ý → Google trả code về /auth/google/callback → backend đổi code lấy ID token, xác minh chữ ký, aud, iss, exp, nonce, email_verified và tên miền → tìm user theo google_sub:

- Chưa có: tạo user PENDING, chuyển tới màn "Hoàn tất đăng ký".
- PENDING: màn "Chờ cấp quyền".
- ACTIVE: tạo phiên (cookie HttpOnly), vào trang theo vai trò hoặc trang trước đó (tham số next).
- DISABLED: từ chối.

Đăng xuất: xóa phiên phía server và cookie; không đăng xuất tài khoản Google của người dùng.
Phân quyền kiểm tra ở API theo vai trò (RBAC). Audit log ghi user_id thật cho mọi thao tác. Chỉ dùng scope openid, email, profile; không gọi API Google khác.

### Thiết kế giao diện (UI/UX)

Thiết kế: https://claude.ai/artifact/3fPfUg9J8muJ9YGNPmf8NH — trang "Đặc tả #8 · Đăng nhập Google (Light)", 7 màn hình:

1. Đăng nhập: 1 nút "Tiếp tục với Google", không có ô mật khẩu; ghi rõ chỉ nhận email công ty.
2. Lỗi đăng nhập: email ngoài tên miền được phép; nói rõ nguyên nhân và cách xử lý.
3. Hoàn tất đăng ký: hiện hồ sơ lấy từ Google, chọn vai trò yêu cầu, ghi chú cho quản trị.
4. Chờ cấp quyền: trạng thái yêu cầu, việc tiếp theo, nút đăng xuất.
5. Menu tài khoản trong ứng dụng: thông tin, vai trò, "Đăng xuất" và "Đăng xuất mọi thiết bị".
6. Đã đăng xuất: xác nhận đăng xuất an toàn, nút đăng nhập lại.
7. Quản lý người dùng (admin): yêu cầu đang chờ, cấp vai trò, vô hiệu hóa tài khoản.

Quy ước: khi triển khai thật phải dùng nút đăng nhập chính thức theo hướng dẫn thương hiệu của Google; bản thiết kế dùng nút trung tính.

### Thiết kế API

- GET /auth/google/start?next= → 302 tới Google (state, nonce, code_challenge)
- GET /auth/google/callback?code&state → 302 tới /signup/complete | /pending | trang chính; lỗi → /login?error=DOMAIN_NOT_ALLOWED | EMAIL_NOT_VERIFIED | CANCELLED | STATE_MISMATCH | ACCOUNT_DISABLED
- POST /api/signup/complete {requested_role, note} → 200
- GET /api/me → {id, name, email, avatar_url, role, status}
- POST /auth/logout → 204; POST /auth/logout-all → 204 (Nên có)
- Admin: GET /api/users?status=; PATCH /api/users/{id} {role, status} → ghi audit
- API dữ liệu trả 401 khi chưa đăng nhập, 403 khi PENDING/DISABLED hoặc sai vai trò.

### Mô hình dữ liệu

- users(id, google_sub UNIQUE, email UNIQUE, name, avatar_url, email_domain, role ENUM[SALES, PLANNER, OPS_MANAGER, ADMIN] nullable, status ENUM[PENDING, ACTIVE, DISABLED], requested_role, request_note, created_at, approved_by, approved_at, last_login_at)
- sessions(id, user_id FK, created_at, expires_at, last_seen_at, ip, user_agent, revoked_at)
- allowed_domains(domain) — hoặc biến cấu hình
- audit_log, state_history, plan_versions dùng user_id thật thay tài khoản demo.

Index: users(status), sessions(user_id, revoked_at).

### Thiết kế AI/ML

Không dùng AI. Xác thực và phân quyền là luồng deterministic.

### Trường hợp đặc biệt và Xử lý lỗi

- Email ngoài tên miền được phép → từ chối, không tạo user.
- email_verified = false → từ chối.
- Người dùng bấm Hủy trên trang Google → quay về đăng nhập với thông báo nhẹ.
- state không khớp hoặc hết hạn (mở nhiều tab) → báo lỗi, cho thử lại.
- Tài khoản bị vô hiệu hóa → báo liên hệ quản trị.
- Người dùng đổi email Google → nhận diện theo google_sub, cập nhật email.
- Phiên hết hạn khi đang thao tác → giữ nháp form, đăng nhập lại rồi quay về trang cũ.
- Admin cuối cùng không được tự hạ quyền hoặc tự vô hiệu hóa.

### Bảo mật và Quyền riêng tư

- Authorization Code + PKCE; state chống CSRF; nonce kiểm tra ID token.
- Xác minh chữ ký ID token bằng khóa công khai của Google; kiểm tra aud, iss, exp.
- Client secret lưu trong biến môi trường, tách OAuth client theo môi trường.
- Cookie phiên HttpOnly, Secure, SameSite=Lax; hết hạn sau 12 giờ không hoạt động (tham số).
- Không lưu access token / refresh token của Google.
- Chỉ lưu tên, email, ảnh đại diện; nêu rõ trong chính sách quyền riêng tư.
- Chỉ admin cấp vai trò; mọi thay đổi vai trò vào audit log.
- Tài khoản demo chỉ bật ở môi trường demo, sau feature flag.

## 3. Kế hoạch (Plan)

### Các bước thực hiện

1. Tạo OAuth client trên Google Cloud Console, cấu hình redirect URI cho từng môi trường (2h)
2. Backend start/callback + xác minh ID token (8h)
3. Phiên, đăng xuất, middleware RBAC (6h)
4. Màn đăng nhập, lỗi, hoàn tất đăng ký, chờ cấp quyền, menu tài khoản, đã đăng xuất (10h)
5. Trang quản lý người dùng (6h)
6. Gắn người dùng thật vào audit log thay tài khoản demo (3h)
7. Kiểm thử (5h)

### Công việc con (liên kết Backlog)

- T-049: Cấu hình OAuth client Google & callback xác minh ID token
- T-050: Phiên đăng nhập, đăng xuất & phân quyền RBAC
- T-051: Màn đăng nhập / đăng ký / chờ cấp quyền / menu tài khoản
- T-052: Trang quản lý người dùng & cấp vai trò
- T-053: Gắn người dùng thật vào audit log

### Phụ thuộc

- Cần: audit log và state machine (Đặc tả #6).
- Tài khoản Google Cloud để tạo OAuth client.
- Chốt với đối tác tên miền email được phép (ví dụ tên miền email của ADC) hoặc danh sách email cụ thể.
- Chính sách quyền riêng tư ngắn cho màn đăng nhập.

### Timeline dự kiến

Sprint 5 (backend OAuth, phiên, RBAC, UI, quản lý người dùng, gắn audit). Tổng dự kiến ~40 giờ. [Điền ngày cụ thể khi chốt lịch dự án]

### Kế hoạch kiểm thử

- TC1: đăng nhập lần đầu → tạo user PENDING, vào màn hoàn tất đăng ký.
- TC2: user PENDING đăng nhập → màn chờ cấp quyền; API dữ liệu trả 403.
- TC3: admin cấp vai trò → user vào đúng trang theo vai trò.
- TC4: email ngoài tên miền → lỗi DOMAIN_NOT_ALLOWED, không tạo user.
- TC5: bấm Hủy trên Google → thông báo nhẹ, không lỗi hệ thống.
- TC6: state sai → STATE_MISMATCH, thử lại được.
- TC7: đăng xuất → cookie bị xóa; bấm Back không vào lại được trang dữ liệu.
- TC8: phiên hết hạn → đăng nhập lại, quay về trang cũ.
- TC9: vai trò Điều phối (PLANNER) gọi API duyệt kế hoạch → 403 (theo ma trận quyền `specs/user-roles.md` §2).
- TC10: audit log ghi đúng người dùng cho mọi thao tác.

Nghiệm thu: pass toàn bộ TC.

### Kế hoạch triển khai

Bật ở staging trước với tên miền demo. Giữ đăng nhập tài khoản demo sau feature flag để dùng khi pitch nếu mạng hoặc Google gặp sự cố.

### Tiêu chí thành công

- 100% thao tác trong audit log gắn người dùng thật.
- 0 truy cập dữ liệu từ tài khoản PENDING / DISABLED.
- Người dùng đăng nhập bằng 1 nút, không cần mật khẩu.
- Đăng xuất có hiệu lực ngay trên thiết bị hiện tại.

### Rủi ro và Cách giảm thiểu

- Cấu hình redirect URI sai giữa các môi trường → tách client theo môi trường, có checklist triển khai.
- ADC không dùng Google Workspace → cho phép danh sách email cụ thể; bổ sung Microsoft sau MVP.
- Mạng yếu khi pitch → tài khoản demo sau feature flag.
- Lộ client secret → biến môi trường, không commit lên GitHub.

## Task con & trạng thái

| Task | Nội dung | Sprint | Dự kiến (giờ) | Owner | Trạng thái |
|---|---|---|---|---|---|
| T-049 | Cấu hình OAuth client Google & callback xác minh ID token | 5 | 10 | — | Chờ review |
| T-050 | Phiên đăng nhập, đăng xuất & phân quyền RBAC | 5 | 6 | — | Chờ review |
| T-051 | Màn đăng nhập / đăng ký / chờ cấp quyền / menu tài khoản | 5 | 10 | — | Chờ review |
| T-052 | Trang quản lý người dùng & cấp vai trò | 5 | 6 | — | Chờ review |
| T-053 | Gắn người dùng thật vào audit log | 5 | 8 | — | Chờ review |

## Nhật ký

- 24/09/2026: Tạo từ Đặc tả #8.
- 25/09/2026: Chuyển sang lộ trình 6 tuần (6 sprint); cập nhật sprint của task con và timeline.
- 25/09/2026: Sửa TC9 — Kinh doanh được duyệt plan version theo ma trận quyền; đổi thành Điều phối → 403.
- 30/09/2026 (T-049): Chốt với chủ dự án — làm toàn bộ backend T-049→T-053; thêm PyJWT[crypto] (ADR-0008); bật SQLAlchemy (`create_all` lúc khởi động, Alembic để T-017). Quyết định khi triển khai:
  - State OAuth lưu bảng `oauth_login_attempts` (state, nonce, code_verifier, next; dùng 1 lần, hết hạn `OAUTH_STATE_TTL_MIN`) + cookie `adc_oauth_state` để gắn với trình duyệt.
  - Thêm mã lỗi `AUTH_FAILED` (đổi code / xác minh ID token thất bại) vào `specs/api-contracts.md`.
  - `ALLOWED_EMAIL_DOMAINS` rỗng → không ai đăng ký được (fail-closed). `BOOTSTRAP_ADMIN_EMAILS` tạo ADMIN đầu tiên (không có ai để duyệt họ).
  - User PENDING chưa gửi yêu cầu vai trò → quay lại `/signup/complete` thay vì `/pending`.
  - "Trang chính" = `/` của frontend (`FRONTEND_URL`); frontend tự điều hướng theo vai trò vì đặc tả chưa định nghĩa trang theo từng vai trò.
  - ❓ Chưa chốt: tên miền email của ADC (T-004); trang đích theo vai trò.
- 30/09/2026 (T-050): Phiên lưu `sessions` với id = sha256(token), cookie `adc_session` không đặt Max-Age (hạn trượt 12h do server giữ). Phiên cấp cả cho PENDING (để gửi `/api/signup/complete` và gọi `/api/me`), API dữ liệu vẫn 403. `/api/signup/complete` chỉ nhận SALES/PLANNER/OPS_MANAGER; ADMIN hoặc user không PENDING → 422. Thêm `POST /auth/demo-login` (sau `FEATURE_DEMO_LOGIN`) vào contract. Email đã gắn với `google_sub` khác → từ chối `AUTH_FAILED`, không tự gộp tài khoản. TC9 kiểm tra qua dependency `require(APPROVE_PLAN_VERSION)`; API duyệt thật làm ở T-042.
- 30/09/2026 (T-052): Xong API `GET/PATCH /api/users`. Luật: ACTIVE phải có vai trò; không đưa về PENDING; không để hệ thống còn 0 ADMIN ACTIVE (409); vô hiệu hóa → thu hồi mọi phiên; PENDING → ACTIVE ghi `approved_by/approved_at`. Đổi vai trò có hiệu lực ngay ở request kế tiếp (user đọc lại mỗi request). Trang UI chờ frontend (T-007).
- 30/09/2026 (T-053): `audit_log` tối thiểu đặt ở `orchestration` (context sở hữu audit — ADC-006); `record()` từ chối actor rỗng. Hiện ghi: LOGIN, DEMO_LOGIN, LOGOUT, LOGOUT_ALL, SIGNUP_REQUESTED, USER_UPDATED (payload có giá trị cũ/mới). Đăng nhập thất bại không ghi vì chưa có người dùng. Các thao tác nghiệp vụ sau này (duyệt plan, sự cố…) gọi `record(db, user.id, …)` với user từ `require(action)`.
- 30/09/2026 (T-051): Bị kẹt — chưa có khung frontend (T-007). Backend cho 7 màn đã sẵn: `/auth/google/start`, `/login?error=`, `/api/signup/complete`, `/api/me`, `/auth/logout(-all)`, `/api/users`.
- 30/09/2026 (T-051): Dựng khung Next.js 16 trong `frontend/` (một phần T-007) + 7 màn theo thiết kế (Light). Trang chính theo vai trò chốt tạm: SALES `/sales`, PLANNER `/planner`, OPS_MANAGER `/ops`, ADMIN `/admin/users` — ❓ cần PO xác nhận. Frontend proxy `/api` + `/auth` qua `next.config.ts` (giải quyết cookie cross-site khi deploy Vercel/Render). Bổ sung `requested_role` vào `GET /api/me` (contract) để phân biệt `/signup/complete` với `/pending`. Nháp form ước tính giữ trong sessionStorage (TC8). Test logic bằng `node --test` (không thêm thư viện test). Còn thiếu: CI chưa chạy frontend; nút Google chưa theo brand guideline chính thức.
