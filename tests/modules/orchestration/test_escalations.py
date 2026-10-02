"""ADC-005 T-037 — raise_escalation: 1 mục đang mở mỗi đơn, SLA_RISK → ESCALATED_TO_BUSINESS, audit."""

import pytest
from sqlalchemy import select

from src.modules.identity import Role, User, UserStatus
from src.modules.intake import Ticket, TicketSourceType, WorkOrder
from src.modules.orchestration import AuditLog, WorkOrderState, raise_escalation
from src.modules.risk import Escalation, EscalationStatus
from tests.conftest import at


@pytest.fixture
def actor(db):
    user = User(
        google_sub="s", email="p@adc.test", email_domain="adc.test", role=Role.PLANNER, status=UserStatus.ACTIVE
    )
    db.add(user)
    db.commit()
    return user


@pytest.fixture
def make_wo(db):
    def _make(state: WorkOrderState) -> WorkOrder:
        ticket = Ticket(source_type=TicketSourceType.MANUAL)
        db.add(ticket)
        db.flush()
        wo = WorkOrder(ticket_id=ticket.id, product_name="Ớt", requested_return=at(12), state=state)
        db.add(wo)
        db.commit()
        return wo

    return _make


def test_sla_risk_order_is_escalated_once(db, actor, make_wo):
    wo = make_wo(WorkOrderState.SLA_RISK)
    first = raise_escalation(db, wo, delay_min=30, incident_id=None, actor_id=actor.id, now=at(8), reason="trễ")
    assert (first.status, first.delay_min, wo.state) == (
        EscalationStatus.OPEN,
        30,
        WorkOrderState.ESCALATED_TO_BUSINESS,
    )
    again = raise_escalation(db, wo, delay_min=30, incident_id=None, actor_id=actor.id, now=at(9), reason="trễ")
    later = raise_escalation(db, wo, delay_min=45, incident_id=None, actor_id=actor.id, now=at(9), reason="trễ")
    assert first.id == again.id == later.id and later.delay_min == 45
    assert len(db.scalars(select(Escalation)).all()) == 1
    actions = [a.action for a in db.scalars(select(AuditLog).order_by(AuditLog.id))]
    # cùng số phút trễ → không ghi thêm audit
    assert actions == ["ESCALATION_CREATED", "WORK_ORDER_STATE_CHANGED", "ESCALATION_UPDATED"]


def test_approved_escalation_is_not_reused(db, actor, make_wo):
    wo = make_wo(WorkOrderState.ESCALATED_TO_BUSINESS)
    first = raise_escalation(db, wo, delay_min=30, incident_id=None, actor_id=actor.id, now=at(8), reason="trễ")
    first.status = EscalationStatus.APPROVED
    db.commit()
    second = raise_escalation(db, wo, delay_min=90, incident_id=None, actor_id=actor.id, now=at(9), reason="trễ hơn")
    assert second.id != first.id and second.status == EscalationStatus.OPEN


def test_other_states_keep_state_and_on_time_is_rejected(db, actor, make_wo):
    wo = make_wo(WorkOrderState.SCHEDULED)
    raise_escalation(db, wo, delay_min=10, incident_id=None, actor_id=actor.id, now=at(8), reason="bị đẩy")
    assert wo.state == WorkOrderState.SCHEDULED
    with pytest.raises(ValueError):
        raise_escalation(db, wo, delay_min=0, incident_id=None, actor_id=actor.id, now=at(8), reason="kịp")
