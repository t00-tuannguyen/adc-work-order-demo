from datetime import UTC, datetime

import pytest

from src.modules.identity import Role, User, UserStatus
from src.modules.intake import Ticket, TicketSourceType, WorkOrder
from src.modules.orchestration import (
    ActorType,
    AuditLog,
    InvalidTransitionError,
    StateHistory,
    WorkOrderState,
    transition_work_order,
)

NOW = datetime(2026, 10, 1, 8, tzinfo=UTC)


@pytest.fixture
def setup(db):
    u = User(google_sub="s", email="a@adc.test", email_domain="adc.test", role=Role.SALES, status=UserStatus.ACTIVE)
    t = Ticket(source_type=TicketSourceType.MANUAL)
    db.add_all([u, t])
    db.flush()
    wo = WorkOrder(ticket_id=t.id)
    db.add(wo)
    db.commit()
    return u, wo


def test_valid_transition_is_audited(db, setup):
    u, wo = setup
    transition_work_order(db, wo, WorkOrderState.FEASIBILITY_CHECK, actor_id=u.id, reason="test", now=NOW)
    db.expire_all()
    assert db.get(WorkOrder, wo.id).state == WorkOrderState.FEASIBILITY_CHECK
    log = db.query(AuditLog).filter_by(action="WORK_ORDER_STATE_CHANGED").one()
    assert log.payload == {"work_order_id": wo.id, "from": "DRAFT", "to": "FEASIBILITY_CHECK", "reason": "test"}


def test_invalid_transition_changes_nothing(db, setup):
    u, wo = setup
    with pytest.raises(InvalidTransitionError):
        transition_work_order(db, wo, WorkOrderState.SCHEDULED, actor_id=u.id, reason="x", now=NOW)
    assert wo.state == WorkOrderState.DRAFT and db.query(AuditLog).count() == 0
    assert db.query(StateHistory).count() == 0


def test_transition_writes_state_history(db, setup):
    """T-041: mỗi lần chuyển ghi 1 dòng lịch sử — ai, khi nào, vì sao, plan version nào."""
    u, wo = setup
    transition_work_order(
        db, wo, WorkOrderState.FEASIBILITY_CHECK, actor_id=u.id, reason="tự động", now=NOW, actor_type=ActorType.SYSTEM
    )
    row = db.query(StateHistory).one()
    assert (row.work_order_id, row.from_state, row.to_state, row.actor_type, row.actor_id, row.reason) == (
        wo.id,
        WorkOrderState.DRAFT,
        WorkOrderState.FEASIBILITY_CHECK,
        ActorType.SYSTEM,
        u.id,
        "tự động",
    )
    assert row.at == NOW and row.plan_version_id is None
