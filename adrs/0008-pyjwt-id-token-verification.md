# ADR-0008: PyJWT[crypto] để xác minh ID token Google

| Trường | Giá trị |
|---|---|
| Trạng thái | Proposed |
| Ngày | 30/09/2026 |
| Người quyết định | [Họ tên] |
| Liên quan | ADC-008, ADR-0002, ADR-0006, T-049 |

## Bối cảnh

ADC-008 (mục *Bảo mật*) yêu cầu xác minh chữ ký ID token bằng khóa công khai của Google (JWKS, RS256) và kiểm tra `aud`, `iss`, `exp`, `nonce`. ADR-0002 chưa có thư viện JWT/mật mã nào; thư viện chuẩn Python không xác minh được chữ ký RSA.

## Các phương án
1. **PyJWT[crypto]** (`pyjwt` + `cryptography`) — nhỏ, chỉ làm JWT/JWK; tự gọi token endpoint bằng `httpx` (đã có). Phải tự viết phần kiểm tra claim riêng của Google (`email_verified`, tên miền).
2. **google-auth** — thư viện chính thức (`id_token.verify_oauth2_token`), nhưng kéo thêm `requests`, `pyasn1`, `rsa`, `cachetools`; khó giả lập JWKS trong test.
3. **Không xác minh chữ ký** — OIDC Core §3.1.3.7 cho phép khi ID token nhận trực tiếp từ token endpoint qua TLS; không cần thư viện mới nhưng lệch yêu cầu bảo mật của ADC-008.

## Quyết định

Chọn **1**. Thêm `pyjwt[crypto]>=2.9.0` vào `requirements.txt`. Chỉ chấp nhận thuật toán `RS256`; khóa lấy từ JWKS của Google (`https://www.googleapis.com/oauth2/v3/certs`), cache trong tiến trình. Gọi token endpoint bằng `httpx`.

## Hệ quả
- ✅ Đúng yêu cầu bảo mật của ADC-008; test tự ký token bằng khóa RSA sinh tại chỗ, không gọi mạng.
- ⚠️ `cryptography` là gói có phần native — cần wheel phù hợp khi build Docker (có sẵn cho `python:3.11-slim`).
- 🔁 Việc tiếp theo: bổ sung dòng "Xác thực" trong ADR-0002 khi ADR này Accepted.
