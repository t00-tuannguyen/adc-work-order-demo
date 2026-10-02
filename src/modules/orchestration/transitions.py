"""Chuyển trạng thái work order — chỉ Orchestration được ghi `state` (ADR-0003). ADC-006 §State machine.

Kiểm tra bảng chuyển hợp lệ, ghi `state_history` (T-041) + audit trong cùng commit.
Nhận bất kỳ object có thuộc tính `id`, `state` (không import model của Intake để tránh phụ thuộc vòng).
"""

from datetime import datetime
from typing import Protocol

from sqlalchemy.orm import Session

from src.modules.orchestration.audit import AuditAction, record
from src.modules.orchestration.history import ActorType, StateHistory
from src.modules.orchestration.state_machine import WORK_ORDER_TRANSITIONS, WorkOrderState, assert_transition


class HasState(Protocol):
    id: str
    state: WorkOrderState


def transition_work_order(
    db: Session,
    work_order: HasState,
    to_state: WorkOrderState,
    *,
    actor_id: str,
    reason: str,
    now: datetime,
    actor_type: ActorType = ActorType.USER,
    plan_version_id: int | None = None,
) -> None:
    """Sai bảng chuyển → InvalidTransitionError, không đổi gì. Commit cùng dòng lịch sử + audit."""
    from_state = WorkOrderState(work_order.state)
    assert_transition(WORK_ORDER_TRANSITIONS, from_state, to_state)
    work_order.state = to_state
    db.add(
        StateHistory(
            work_order_id=work_order.id,
            from_state=from_state,
            to_state=to_state,
            actor_type=actor_type,
            actor_id=actor_id,
            reason=reason,
            plan_version_id=plan_version_id,
            at=now,
        )
    )
    record(
        db,
        actor_id,
        AuditAction.WORK_ORDER_STATE_CHANGED,
        {"work_order_id": work_order.id, "from": from_state.value, "to": to_state.value, "reason": reason},
        now=now,
    )
