"""Phần deterministic của Google OIDC (Authorization Code + PKCE) — ADC-008, ADR-0006, ADR-0008.

Không gọi mạng: JWKS và ID token được truyền vào (lấy bởi `src/services/google_oauth.py`).
"""

import base64
import hashlib
import secrets
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

import jwt

GOOGLE_ISSUERS = ["https://accounts.google.com", "accounts.google.com"]


class AuthErrorCode(StrEnum):
    """Mã lỗi trên `/login?error=` — specs/api-contracts.md §Quy ước chung."""

    DOMAIN_NOT_ALLOWED = "DOMAIN_NOT_ALLOWED"
    EMAIL_NOT_VERIFIED = "EMAIL_NOT_VERIFIED"
    CANCELLED = "CANCELLED"
    STATE_MISMATCH = "STATE_MISMATCH"
    ACCOUNT_DISABLED = "ACCOUNT_DISABLED"
    AUTH_FAILED = "AUTH_FAILED"  # đổi code / xác minh ID token thất bại


class AuthError(Exception):
    def __init__(self, code: AuthErrorCode, detail: str = ""):
        super().__init__(detail or code)
        self.code = code


@dataclass(frozen=True)
class GoogleIdentity:
    sub: str
    email: str
    email_verified: bool
    name: str
    picture: str | None


def random_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def pkce_challenge(code_verifier: str) -> str:
    """S256 — RFC 7636 §4.2."""
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def verify_id_token(id_token: str, jwks: dict, *, client_id: str, nonce: str, leeway_s: int = 30) -> GoogleIdentity:
    """Xác minh chữ ký RS256 bằng JWKS của Google, rồi aud, iss, exp, nonce."""
    try:
        kid = jwt.get_unverified_header(id_token).get("kid")
        key = next((k for k in jwt.PyJWKSet.from_dict(jwks).keys if k.key_id == kid), None)
        if key is None:
            raise AuthError(AuthErrorCode.AUTH_FAILED, f"không có khóa kid={kid!r} trong JWKS")
        claims = jwt.decode(
            id_token,
            key.key,
            algorithms=["RS256"],
            audience=client_id,
            issuer=GOOGLE_ISSUERS,
            leeway=leeway_s,
            options={"require": ["exp", "iat", "iss", "aud", "sub"]},
        )
    except jwt.PyJWTError as e:
        raise AuthError(AuthErrorCode.AUTH_FAILED, f"ID token không hợp lệ: {e}") from e
    if not secrets.compare_digest(str(claims.get("nonce", "")), nonce):
        raise AuthError(AuthErrorCode.AUTH_FAILED, "nonce không khớp")
    if not claims.get("email"):
        raise AuthError(AuthErrorCode.AUTH_FAILED, "ID token thiếu email")
    return GoogleIdentity(
        sub=claims["sub"],
        email=claims["email"].lower(),
        email_verified=claims.get("email_verified") is True,
        name=claims.get("name", ""),
        picture=claims.get("picture"),
    )


def email_domain(email: str) -> str:
    return email.rsplit("@", 1)[-1].lower()


def parse_list(csv: str) -> frozenset[str]:
    return frozenset(x.strip().lower() for x in csv.split(",") if x.strip())


def is_domain_allowed(email: str, allowed_domains: Iterable[str]) -> bool:
    """Danh sách rỗng → không cho ai (fail-closed)."""
    return email_domain(email) in set(allowed_domains)


def safe_next_path(next_path: str | None) -> str | None:
    """Chỉ nhận đường dẫn tương đối trong ứng dụng — chặn open redirect (`//evil`, `https://…`, `/\\evil`)."""
    if not next_path or not next_path.startswith("/") or next_path.startswith("//") or "\\" in next_path:
        return None
    return next_path
