# ADR-0006: Xác thực bằng Google OAuth 2.0 / OpenID Connect

| Trường | Giá trị |
|---|---|
| Trạng thái | Proposed |
| Ngày | 24/09/2026 |
| Liên quan | ADC-008 |

## Bối cảnh
Audit log và luật "người đề xuất không tự duyệt" cần danh tính thật; đặc tả #1–#7 đang dùng tài khoản demo chung.

## Các phương án
1. Email + mật khẩu tự quản — tốn công (quên mật khẩu, băm, khóa), rủi ro lộ mật khẩu.
2. Magic link — phụ thuộc dịch vụ gửi mail, chậm.
3. SSO doanh nghiệp (SAML / Microsoft Entra ID) — phù hợp nếu ADC dùng Microsoft; để sau MVP.
4. **Google OAuth 2.0 / OIDC (Authorization Code + PKCE)**, vai trò do hệ thống tự quản.

## Quyết định
Chọn **4**. Scope chỉ `openid email profile`; không lưu access/refresh token của Google; chỉ tên miền được phép; user mới `PENDING` đến khi ADMIN cấp vai trò. Tài khoản demo giữ sau feature flag để dự phòng khi pitch.

## Hệ quả
- ✅ Không lưu mật khẩu; đăng nhập 1 chạm.
- ⚠️ Nếu ADC không dùng Google Workspace → cho phép danh sách email cụ thể; bổ sung Microsoft sau MVP.
- 🔁 Tách OAuth client theo môi trường; checklist redirect URI.
