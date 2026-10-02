"""ADC-008 — phiên, đăng xuất, hoàn tất đăng ký, RBAC (T-050)."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from src.api.deps import SESSION_COOKIE, require
from src.modules.identity import Action, Role, User, UserSession, UserStatus, create_session
from src.services.db import get_db
from src.settings import get_settings
from tests.api.test_auth import login, redirect_of

pytestmark = pytest.mark.asyncio

DATA_API = "/api/config/throughput"


async def test_callback_sets_httponly_lax_session_cookie(client, google):
    resp = await login(client, google)
    cookie = next(c for c in resp.headers.get_list("set-cookie") if c.startswith(f"{SESSION_COOKIE}="))
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie and "Max-Age" not in cookie


async def test_tc2_pending_user_sees_me_but_data_api_is_403(client, google):
    await login(client, google)
    me = await client.get("/api/me")
    assert me.status_code == 200
    assert me.json() | {"id": None} == {
        "id": None,
        "name": "Nguyễn An",
        "email": "an@adc.test",
        "avatar_url": None,
        "role": None,
        "status": "PENDING",
        "requested_role": None,
    }
    assert (await client.get(DATA_API)).status_code == 403


async def test_signup_complete_then_next_login_goes_to_pending(client, google, db):
    await login(client, google)
    resp = await client.post("/api/signup/complete", json={"requested_role": "PLANNER", "note": " Điều phối ca sáng "})
    assert resp.status_code == 200
    user = db.scalar(select(User))
    db.refresh(user)
    assert (user.requested_role, user.request_note, user.status) == (
        Role.PLANNER,
        "Điều phối ca sáng",
        UserStatus.PENDING,
    )
    path, _ = redirect_of(await login(client, google))
    assert path == "/pending"


async def test_cannot_request_admin_role(client, google):
    await login(client, google)
    assert (await client.post("/api/signup/complete", json={"requested_role": "ADMIN"})).status_code == 422


async def test_active_user_cannot_resubmit_signup(client, sign_in):
    sign_in(Role.SALES)
    assert (await client.post("/api/signup/complete", json={"requested_role": "PLANNER"})).status_code == 422


async def test_signup_requires_login(client):
    assert (await client.post("/api/signup/complete", json={"requested_role": "SALES"})).status_code == 401


async def test_tc3_approved_user_logs_in_to_home_and_reads_data(client, google, db):
    await login(client, google)
    user = db.scalar(select(User))
    user.status, user.role = UserStatus.ACTIVE, Role.SALES
    db.commit()
    path, _ = redirect_of(await login(client, google))
    assert path == "/"
    assert (await client.get(DATA_API)).status_code == 200


async def test_tc7_logout_clears_cookie_and_old_cookie_no_longer_works(client, sign_in):
    sign_in()
    token = client.cookies[SESSION_COOKIE]
    assert (await client.get(DATA_API)).headers["cache-control"] == "no-store"

    resp = await client.post("/auth/logout")
    assert resp.status_code == 204
    assert f'{SESSION_COOKIE}=""' in resp.headers["set-cookie"] and "Max-Age=0" in resp.headers["set-cookie"]

    client.cookies.set(SESSION_COOKIE, token)  # "bấm Back" với cookie cũ
    assert (await client.get(DATA_API)).status_code == 401


async def test_logout_without_session_is_204(client):
    assert (await client.post("/auth/logout")).status_code == 204


async def test_logout_all_revokes_every_device(client, sign_in, db):
    user = sign_in()
    phone = client.cookies[SESSION_COOKIE]
    laptop = create_session(db, user, now=datetime.now(UTC), ttl=timedelta(hours=12))
    client.cookies.set(SESSION_COOKIE, laptop)
    assert (await client.post("/auth/logout-all")).status_code == 204
    for token in (phone, laptop):
        client.cookies.set(SESSION_COOKIE, token)
        assert (await client.get(DATA_API)).status_code == 401


async def test_logout_all_requires_login(client):
    assert (await client.post("/auth/logout-all")).status_code == 401


async def test_tc8_expired_session_then_relogin_returns_to_previous_page(client, google, db):
    await login(client, google, email="admin@adc.test")
    for s in db.scalars(select(UserSession)):
        s.expires_at -= timedelta(hours=13)
    db.commit()
    assert (await client.get(DATA_API)).status_code == 401

    path, q = redirect_of(await login(client, google, next_path="/board?draft=1", email="admin@adc.test"))
    assert (path, q) == ("/board", {"draft": "1"})
    assert (await client.get(DATA_API)).status_code == 200


async def test_session_expiry_slides_on_activity(client, sign_in, db):
    sign_in()
    session = db.scalar(select(UserSession))
    session.expires_at -= timedelta(hours=11)  # còn 1 giờ
    db.commit()
    await client.get(DATA_API)
    db.refresh(session)
    assert session.expires_at - session.last_seen_at == timedelta(hours=12)


async def test_disabled_user_with_live_session_is_403(client, sign_in):
    sign_in(status=UserStatus.DISABLED)
    assert (await client.get("/api/me")).status_code == 403
    assert (await client.get(DATA_API)).status_code == 403


async def test_demo_login_is_404_when_flag_off(client):
    assert (await client.post("/auth/demo-login", json={"role": "SALES"})).status_code == 404


async def test_demo_login_when_flag_on(client, test_settings):
    test_settings.feature_demo_login = True
    assert (await client.post("/auth/demo-login", json={"role": "OPS_MANAGER"})).status_code == 204
    me = (await client.get("/api/me")).json()
    assert (me["role"], me["status"], me["email"]) == ("OPS_MANAGER", "ACTIVE", "demo.ops_manager@demo.local")


@pytest.fixture
def approval_client(db_factory, test_settings):
    """App tối giản có route gắn require(APPROVE_PLAN_VERSION) — API duyệt thật làm ở T-042."""
    app = FastAPI()

    @app.post("/approve")
    def approve(user: User = Depends(require(Action.APPROVE_PLAN_VERSION))):
        return {"by": user.id}

    def _db():
        with db_factory() as s:
            yield s

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_settings] = lambda: test_settings
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.parametrize(("role", "expected"), [(Role.PLANNER, 403), (Role.SALES, 200), (Role.OPS_MANAGER, 200)])
async def test_tc9_planner_cannot_approve_plan_version(approval_client, sign_in, client, role, expected):
    sign_in(role)
    approval_client.cookies.set(SESSION_COOKIE, client.cookies[SESSION_COOKIE])
    assert (await approval_client.post("/approve")).status_code == expected
