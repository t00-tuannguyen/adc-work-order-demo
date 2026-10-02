"""ADC-008 — quản lý người dùng & cấp vai trò (T-052)."""

import pytest
from sqlalchemy import select

from src.api.deps import SESSION_COOKIE
from src.modules.identity import Role, User, UserStatus
from tests.api.test_auth import login, redirect_of

pytestmark = pytest.mark.asyncio


@pytest.fixture
def admin(sign_in):
    return sign_in(Role.ADMIN, email="admin@adc.test")


def use_cookie(client, token):
    client.cookies.delete(SESSION_COOKIE)  # bỏ cả cookie do server đặt (domain khác) để không gửi trùng
    client.cookies.set(SESSION_COOKIE, token)


async def test_users_api_requires_admin(client, sign_in):
    assert (await client.get("/api/users")).status_code == 401
    for role in (Role.SALES, Role.PLANNER, Role.OPS_MANAGER):
        sign_in(role)
        assert (await client.get("/api/users")).status_code == 403
        assert (await client.patch("/api/users/x", json={"role": "ADMIN"})).status_code == 403


async def test_list_filters_by_status(client, sign_in, admin):
    admin_token = client.cookies[SESSION_COOKIE]
    sign_in(None, UserStatus.PENDING, email="moi@adc.test")
    use_cookie(client, admin_token)
    pending = (await client.get("/api/users", params={"status": "PENDING"})).json()
    assert [u["email"] for u in pending] == ["moi@adc.test"]
    assert len((await client.get("/api/users")).json()) == 2


async def test_tc3_admin_grants_role_then_user_enters_app(client, google, db, admin):
    admin_token = client.cookies[SESSION_COOKIE]
    await login(client, google)
    await client.post("/api/signup/complete", json={"requested_role": "PLANNER"})
    pending = db.scalar(select(User).where(User.email == "an@adc.test"))

    use_cookie(client, admin_token)
    resp = await client.patch(f"/api/users/{pending.id}", json={"role": "PLANNER", "status": "ACTIVE"})
    assert resp.status_code == 200
    body = resp.json()
    assert (body["role"], body["status"], body["approved_by"]) == ("PLANNER", "ACTIVE", admin.id)
    assert body["approved_at"]

    path, _ = redirect_of(await login(client, google))
    assert path == "/"
    assert (await client.get("/api/me")).json()["role"] == "PLANNER"


async def test_active_requires_role(client, sign_in, admin):
    admin_token = client.cookies[SESSION_COOKIE]
    pending = sign_in(None, UserStatus.PENDING, email="moi@adc.test")
    use_cookie(client, admin_token)
    assert (await client.patch(f"/api/users/{pending.id}", json={"status": "ACTIVE"})).status_code == 422


async def test_cannot_move_back_to_pending_or_null_status(client, sign_in, admin):
    admin_token = client.cookies[SESSION_COOKIE]
    user = sign_in(Role.SALES)
    use_cookie(client, admin_token)
    assert (await client.patch(f"/api/users/{user.id}", json={"status": "PENDING"})).status_code == 422
    assert (await client.patch(f"/api/users/{user.id}", json={"status": None})).status_code == 422


async def test_unknown_user_is_404(client, admin):
    assert (await client.patch("/api/users/nope", json={"role": "SALES"})).status_code == 404


@pytest.mark.parametrize("patch", [{"role": "OPS_MANAGER"}, {"status": "DISABLED"}])
async def test_last_admin_cannot_demote_or_disable_self(client, admin, patch):
    assert (await client.patch(f"/api/users/{admin.id}", json=patch)).status_code == 409


async def test_admin_can_step_down_when_another_admin_exists(client, sign_in, admin):
    admin_token = client.cookies[SESSION_COOKIE]
    sign_in(Role.ADMIN, email="admin2@adc.test")
    use_cookie(client, admin_token)
    resp = await client.patch(f"/api/users/{admin.id}", json={"role": "OPS_MANAGER"})
    assert resp.status_code == 200
    assert (await client.get("/api/users")).status_code == 403  # quyền mới có hiệu lực ngay


async def test_disabling_user_ends_their_sessions(client, sign_in, admin):
    admin_token = client.cookies[SESSION_COOKIE]
    user = sign_in(Role.SALES)
    user_token = client.cookies[SESSION_COOKIE]
    use_cookie(client, admin_token)
    assert (await client.patch(f"/api/users/{user.id}", json={"status": "DISABLED"})).status_code == 200
    use_cookie(client, user_token)
    assert (await client.get("/api/me")).status_code == 401
