"""ADC-008 TC10 — audit log ghi đúng người dùng thật cho mọi thao tác (T-053)."""

import pytest
from sqlalchemy import select

from src.api.deps import SESSION_COOKIE
from src.modules.identity import Role, User, UserStatus
from src.modules.orchestration import AuditLog
from tests.api.test_auth import login
from tests.api.test_users import use_cookie

pytestmark = pytest.mark.asyncio


def trail(db) -> list[tuple[str, str]]:
    return [(e.actor_id, e.action) for e in db.scalars(select(AuditLog).order_by(AuditLog.id))]


async def test_tc10_every_action_is_attributed_to_the_real_user(client, google, db, sign_in):
    admin = sign_in(Role.ADMIN, email="admin@adc.test")
    admin_token = client.cookies[SESSION_COOKIE]

    await login(client, google)  # LOGIN (PENDING)
    await client.post("/api/signup/complete", json={"requested_role": "SALES", "note": "KD miền Nam"})
    an = db.scalar(select(User).where(User.email == "an@adc.test"))

    use_cookie(client, admin_token)
    await client.patch(f"/api/users/{an.id}", json={"role": "SALES", "status": "ACTIVE"})

    await login(client, google)  # LOGIN (ACTIVE) — cookie phiên mới của An
    await client.post("/auth/logout")
    use_cookie(client, admin_token)
    await client.post("/auth/logout-all")

    assert trail(db) == [
        (an.id, "LOGIN"),
        (an.id, "SIGNUP_REQUESTED"),
        (admin.id, "USER_UPDATED"),
        (an.id, "LOGIN"),
        (an.id, "LOGOUT"),
        (admin.id, "LOGOUT_ALL"),
    ]
    assert all(actor for actor, _ in trail(db))


async def test_role_change_payload_records_before_and_after(client, sign_in, db):
    sign_in(Role.ADMIN, email="admin@adc.test")
    admin_token = client.cookies[SESSION_COOKIE]
    target = sign_in(Role.SALES)
    use_cookie(client, admin_token)
    await client.patch(f"/api/users/{target.id}", json={"role": "OPS_MANAGER"})
    entry = db.scalar(select(AuditLog).where(AuditLog.action == "USER_UPDATED"))
    assert entry.payload == {
        "user_id": target.id,
        "email": target.email,
        "changes": [{"field": "role", "old": "SALES", "new": "OPS_MANAGER"}],
    }


async def test_rejected_or_noop_update_is_not_audited(client, sign_in, db):
    admin = sign_in(Role.ADMIN, email="admin@adc.test")
    await client.patch(f"/api/users/{admin.id}", json={"status": "DISABLED"})  # 409 admin cuối
    await client.patch(f"/api/users/{admin.id}", json={"role": "ADMIN"})  # không đổi gì
    assert db.scalar(select(AuditLog).where(AuditLog.action == "USER_UPDATED")) is None


async def test_demo_login_is_audited_to_demo_user(client, test_settings, db):
    test_settings.feature_demo_login = True
    await client.post("/auth/demo-login", json={"role": "PLANNER"})
    demo = db.scalar(select(User).where(User.status == UserStatus.ACTIVE))
    assert trail(db) == [(demo.id, "DEMO_LOGIN")]
