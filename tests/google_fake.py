"""Giả lập Google OIDC cho test — tự ký ID token bằng khóa RSA sinh tại chỗ, không gọi mạng."""

import json
import time
from urllib.parse import parse_qs, urlparse

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from src.modules.identity.oidc import pkce_challenge
from src.services.google_oauth import GoogleOAuthClient, GoogleOAuthError

CLIENT_ID = "test-client.apps.googleusercontent.com"


class FakeGoogle(GoogleOAuthClient):
    def __init__(self):
        super().__init__(CLIENT_ID, "secret", "http://test/auth/google/callback")
        self.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.kid = "k1"
        self._codes: dict[str, tuple[dict, str]] = {}  # code → (claims, code_challenge)
        self.fail_exchange = False

    # --- phía Google ---
    def jwks(self, *, force_refresh: bool = False) -> dict:
        jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.private_key.public_key()))
        return {"keys": [{**jwk, "kid": self.kid, "alg": "RS256", "use": "sig"}]}

    def sign(self, claims: dict, *, key=None, kid: str | None = None) -> str:
        now = int(time.time())
        payload = {"iss": "https://accounts.google.com", "aud": CLIENT_ID, "iat": now, "exp": now + 3600, **claims}
        return jwt.encode(payload, key or self.private_key, algorithm="RS256", headers={"kid": kid or self.kid})

    def exchange_code(self, code: str, code_verifier: str) -> str:
        if self.fail_exchange or code not in self._codes:
            raise GoogleOAuthError("invalid_grant")
        claims, challenge = self._codes.pop(code)
        if pkce_challenge(code_verifier) != challenge:
            raise GoogleOAuthError("invalid_grant: PKCE")
        return self.sign(claims)

    # --- phía test: giả lập người dùng đồng ý trên trang Google ---
    def consent(self, authorization_url: str, **claims) -> dict[str, str]:
        """Trả query cho callback: {code, state}. Nonce lấy từ URL như Google thật."""
        q = {k: v[0] for k, v in parse_qs(urlparse(authorization_url).query).items()}
        code = f"code-{len(self._codes)}-{q['state'][:8]}"
        defaults = {"sub": "sub-1", "email": "an@adc.test", "email_verified": True, "name": "Nguyễn An"}
        self._codes[code] = ({**defaults, **claims, "nonce": q["nonce"]}, q["code_challenge"])
        return {"code": code, "state": q["state"]}
