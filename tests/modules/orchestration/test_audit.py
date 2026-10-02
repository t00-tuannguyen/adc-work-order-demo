"""BR-10 — audit log chỉ ghi thêm; ADC-008 T-053 — mọi dòng gắn người dùng thật."""

from datetime import UTC, datetime

import pytest

from src.modules.identity import Role, User, UserStatus
from src.modules.orchestration import AuditAction, AuditLogImmutableError, record

NOW = datetime(2026, 10, 1, 8, tzinfo=UTC)


@pytest.fixture
def user(db):
    u = User(google_sub="s", email="a@adc.test", email_domain="adc.test", role=Role.SALES, status=UserStatus.ACTIVE)
    db.add(u)
    db.commit()
    return u


def test_record_stores_actor_action_payload(db, user):
    entry = record(db, user.id, AuditAction.LOGIN, {"outcome": "ACTIVE"}, now=NOW)
    assert (entry.actor_id, entry.action, entry.payload, entry.at) == (user.id, "LOGIN", {"outcome": "ACTIVE"}, NOW)


@pytest.mark.parametrize("actor", ["", None])
def test_record_requires_real_user(db, actor):
    with pytest.raises(ValueError):
        record(db, actor, AuditAction.LOGIN, now=NOW)


def test_audit_log_cannot_be_updated(db, user):
    entry = record(db, user.id, AuditAction.LOGIN, now=NOW)
    entry.action = "TAMPERED"
    with pytest.raises(AuditLogImmutableError):
        db.commit()


def test_audit_log_cannot_be_deleted(db, user):
    entry = record(db, user.id, AuditAction.LOGIN, now=NOW)
    db.delete(entry)
    with pytest.raises(AuditLogImmutableError):
        db.commit()
