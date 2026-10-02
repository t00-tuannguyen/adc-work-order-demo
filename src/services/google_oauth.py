"""Gọi Google OAuth 2.0 / OIDC — ADR-0006. Chỉ scope `openid email profile`; không lưu access/refresh token."""

import time
from urllib.parse import urlencode

import httpx

AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
JWKS_URI = "https://www.googleapis.com/oauth2/v3/certs"
SCOPES = "openid email profile"


class GoogleOAuthError(Exception):
    pass


class GoogleOAuthClient:
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str, *, jwks_ttl_s: int = 3600):
        self.client_id = client_id
        self._client_secret = client_secret
        self.redirect_uri = redirect_uri
        self._jwks_ttl_s = jwks_ttl_s
        self._jwks: dict | None = None
        self._jwks_fetched_at = 0.0

    def authorization_url(self, *, state: str, nonce: str, code_challenge: str) -> str:
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": SCOPES,
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "prompt": "select_account",
        }
        return f"{AUTH_ENDPOINT}?{urlencode(params)}"

    def exchange_code(self, code: str, code_verifier: str) -> str:
        """Đổi authorization code lấy ID token (bỏ access_token Google trả về)."""
        try:
            resp = httpx.post(
                TOKEN_ENDPOINT,
                data={
                    "code": code,
                    "client_id": self.client_id,
                    "client_secret": self._client_secret,
                    "redirect_uri": self.redirect_uri,
                    "grant_type": "authorization_code",
                    "code_verifier": code_verifier,
                },
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()["id_token"]
        except (httpx.HTTPError, KeyError, ValueError) as e:
            raise GoogleOAuthError(f"đổi code thất bại: {e}") from e

    def jwks(self, *, force_refresh: bool = False) -> dict:
        """Khóa công khai của Google, cache trong tiến trình (Google xoay khóa định kỳ)."""
        if force_refresh or self._jwks is None or time.monotonic() - self._jwks_fetched_at > self._jwks_ttl_s:
            try:
                resp = httpx.get(JWKS_URI, timeout=10)
                resp.raise_for_status()
                self._jwks = resp.json()
            except (httpx.HTTPError, ValueError) as e:
                raise GoogleOAuthError(f"tải JWKS thất bại: {e}") from e
            self._jwks_fetched_at = time.monotonic()
        return self._jwks
