"""ADC-008 — luồng /auth/google/start → callback (T-049)."""

from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import func, select

from src.modules.identity import OAuthLoginAttempt, Role, User, UserStatus
from tests.conftest import FRONTEND

pytestmark = pytest.mark.asyncio


async def login(client, google, next_path=None, **claims):
    """Đi hết luồng Google; trả response của callback."""
    params = {"next": next_path} if next_path else {}
    start = await client.get("/auth/google/start", params=params)
    assert start.status_code == 302
    return await client.get("/auth/google/callback", params=google.consent(start.headers["location"], **claims))


def redirect_of(resp) -> tuple[str, dict]:
    assert resp.status_code == 302
    url = urlparse(resp.headers["location"])
    assert f"{url.scheme}://{url.netloc}" == FRONTEND
    return url.path, {k: v[0] for k, v in parse_qs(url.query).items()}


def user_count(db) -> int:
    return db.scalar(select(func.count()).select_from(User))


async def test_start_redirects_to_google_with_pkce_state_nonce(client):
    resp = await client.get("/auth/google/start")
    assert resp.status_code == 302
    url = urlparse(resp.headers["location"])
    q = {k: v[0] for k, v in parse_qs(url.query).items()}
    assert url.netloc == "accounts.google.com"
    assert q["scope"] == "openid email profile"
    assert q["code_challenge_method"] == "S256"
    assert q["state"] and q["nonce"] and q["code_challenge"]
    assert "HttpOnly" in resp.headers["set-cookie"]


async def test_tc1_first_login_creates_pending_user_and_goes_to_signup(client, google, db):
    path, _ = redirect_of(await login(client, google))
    assert path == "/signup/complete"
    user = db.scalar(select(User))
    assert (user.email, user.status, user.role, user.email_domain) == (
        "an@adc.test",
        UserStatus.PENDING,
        None,
        "adc.test",
    )


async def test_tc4_domain_not_allowed_creates_no_user(client, google, db):
    path, q = redirect_of(await login(client, google, email="an@gmail.com"))
    assert (path, q["error"]) == ("/login", "DOMAIN_NOT_ALLOWED")
    assert user_count(db) == 0


async def test_email_not_verified_is_rejected(client, google, db):
    _, q = redirect_of(await login(client, google, email_verified=False))
    assert q["error"] == "EMAIL_NOT_VERIFIED"
    assert user_count(db) == 0


async def test_tc5_cancel_on_google_returns_to_login(client):
    await client.get("/auth/google/start")
    path, q = redirect_of(await client.get("/auth/google/callback", params={"error": "access_denied", "state": "x"}))
    assert (path, q["error"]) == ("/login", "CANCELLED")


async def test_tc6_state_mismatch_then_retry_succeeds(client, google):
    start = await client.get("/auth/google/start")
    query = google.consent(start.headers["location"])
    _, q = redirect_of(await client.get("/auth/google/callback", params={**query, "state": "forged"}))
    assert q["error"] == "STATE_MISMATCH"
    path, _ = redirect_of(await login(client, google))
    assert path == "/signup/complete"


async def test_state_from_other_browser_tab_is_rejected(client, google):
    first = await client.get("/auth/google/start")
    await client.get("/auth/google/start")  # tab thứ 2 ghi đè cookie state
    _, q = redirect_of(await client.get("/auth/google/callback", params=google.consent(first.headers["location"])))
    assert q["error"] == "STATE_MISMATCH"


async def test_state_is_single_use(client, google):
    start = await client.get("/auth/google/start")
    query = google.consent(start.headers["location"])
    await client.get("/auth/google/callback", params=query)
    client.cookies.set("adc_oauth_state", query["state"], path="/auth/google")
    _, q = redirect_of(await client.get("/auth/google/callback", params=query))
    assert q["error"] == "STATE_MISMATCH"


async def test_expired_state_is_rejected(client, google, db):
    start = await client.get("/auth/google/start")
    query = google.consent(start.headers["location"])
    attempt = db.get(OAuthLoginAttempt, query["state"])
    attempt.created_at -= timedelta(minutes=11)
    db.commit()
    _, q = redirect_of(await client.get("/auth/google/callback", params=query))
    assert q["error"] == "STATE_MISMATCH"


async def test_failed_code_exchange_is_auth_failed(client, google):
    google.fail_exchange = True
    _, q = redirect_of(await login(client, google))
    assert q["error"] == "AUTH_FAILED"


async def test_pending_user_with_requested_role_goes_to_pending(client, google, db):
    await login(client, google)
    user = db.scalar(select(User))
    user.requested_role = Role.PLANNER
    db.commit()
    path, _ = redirect_of(await login(client, google))
    assert path == "/pending"


async def test_disabled_user_is_rejected(client, google, db):
    await login(client, google)
    db.scalar(select(User)).status = UserStatus.DISABLED
    db.commit()
    _, q = redirect_of(await login(client, google))
    assert q["error"] == "ACCOUNT_DISABLED"


async def test_active_user_returns_to_next_page(client, google):
    path, _ = redirect_of(await login(client, google, next_path="/board?line=A", email="admin@adc.test"))
    assert path == "/board"


async def test_next_open_redirect_falls_back_to_home(client, google):
    path, _ = redirect_of(await login(client, google, next_path="//evil.com", email="admin@adc.test"))
    assert path == "/"


async def test_bootstrap_admin_is_active_admin(client, google, db):
    await login(client, google, email="admin@adc.test")
    user = db.scalar(select(User))
    assert (user.status, user.role) == (UserStatus.ACTIVE, Role.ADMIN)


async def test_changed_google_email_updates_same_user(client, google, db):
    await login(client, google)
    await login(client, google, email="an.nguyen@adc.test")
    assert user_count(db) == 1
    assert db.scalar(select(User)).email == "an.nguyen@adc.test"


async def test_email_owned_by_other_google_account_is_rejected(client, google, db):
    await login(client, google)
    _, q = redirect_of(await login(client, google, sub="sub-2"))
    assert q["error"] == "AUTH_FAILED"
    assert user_count(db) == 1
