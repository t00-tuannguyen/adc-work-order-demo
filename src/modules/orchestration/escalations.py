"""Escalation cho đơn trễ giờ trả — ADC-005 (T-037), BR-06.

Mọi đơn có giờ xong dự kiến > giờ trả trong phương án mới (sự cố, hoặc bị đẩy lùi khi nhận đơn WARN) có 1
escalation đang mở cho kinh doanh. Đơn SLA_RISK → ESCALATED_TO_BUSINESS. Đơn ở trạng thái khác (vd đang chờ
hàng, bị đẩy khi nhận đơn WARN) vẫn có escalation nhưng giữ trạng thái (bảng chuyển chưa có — T-040).
Phương án sau đổi số phút trễ → cập nhật mục đang mở, không tạo trùng. Hết trễ → không tự đóng: API báo
`can_close` để người xác nhận.
Nháp & duyệt (T-038): `save_draft` OPEN → DRAFTED (soạn lại khi DRAFTED được); `approve_escalation` DRAFTED →
APPROVED với thông điệp cuối do người duyệt — LLM không bao giờ gọi tới đây. MVP không gửi email thật.
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.modules.orchestration.audit import AuditAction, record
from src.modules.orchestration.history import ActorType
from src.modules.orchestration.state_machine import (
    ESCALATION_TRANSITIONS,
    EscalationStatus,
    WorkOrderState,
    assert_transition,
)
from src.modules.orchestration.transitions import HasState, transition_work_order
from src.modules.risk import OPEN_ESCALATION, Escalation


class EscalationStateError(Exception):
    """Escalation không ở trạng thái cho phép thao tác (409)."""


def open_escalation(db: Session, work_order_id: str) -> Escalation | None:
    return db.scalars(
        select(Escalation).where(Escalation.work_order_id == work_order_id, Escalation.status.in_(OPEN_ESCALATION))
    ).first()


def raise_escalation(
    db: Session,
    wo: HasState,
    *,
    delay_min: int,
    incident_id: int | None,
    actor_id: str,
    now: datetime,
    reason: str,
) -> Escalation:
    """Tạo (hoặc cập nhật) escalation đang mở của đơn rồi chuyển SLA_RISK → ESCALATED_TO_BUSINESS. Commit."""
    if delay_min <= 0:
        raise ValueError("escalation chỉ cho đơn trễ giờ trả (delay_min > 0)")
    esc = open_escalation(db, wo.id)
    if esc is None:
        esc = Escalation(
            work_order_id=wo.id, incident_id=incident_id, delay_min=delay_min, status=EscalationStatus.OPEN
        )
        db.add(esc)
        db.flush()
        action = AuditAction.ESCALATION_CREATED
    elif (esc.delay_min, esc.incident_id) != (delay_min, incident_id or esc.incident_id):
        esc.delay_min = delay_min
        esc.incident_id = incident_id or esc.incident_id
        action = AuditAction.ESCALATION_UPDATED
    else:
        action = None
    if action is not None:
        record(
            db,
            actor_id,
            action,
            {"escalation_id": esc.id, "work_order_id": wo.id, "incident_id": esc.incident_id, "delay_min": delay_min},
            now=now,
        )  # commit
    if WorkOrderState(wo.state) == WorkOrderState.SLA_RISK:
        transition_work_order(
            db,
            wo,
            WorkOrderState.ESCALATED_TO_BUSINESS,
            actor_id=actor_id,
            reason=reason,
            now=now,
            actor_type=ActorType.SYSTEM,
        )
    db.commit()
    return esc


def save_draft(db: Session, esc: Escalation, message: str, *, source: str, actor_id: str, now: datetime) -> Escalation:
    """Lưu nháp (LLM hoặc mẫu soạn sẵn). Không đụng `final_message` — nháp không bao giờ tự gửi."""
    if esc.status not in OPEN_ESCALATION:
        raise EscalationStateError(f"Escalation #{esc.id} đã {esc.status}, không soạn lại được")
    if esc.status == EscalationStatus.OPEN:
        assert_transition(ESCALATION_TRANSITIONS, esc.status, EscalationStatus.DRAFTED)
        esc.status = EscalationStatus.DRAFTED
    esc.draft_message = message
    record(
        db,
        actor_id,
        AuditAction.ESCALATION_DRAFTED,
        {"escalation_id": esc.id, "work_order_id": esc.work_order_id, "source": source},
        now=now,
    )  # commit
    return esc


def approve_escalation(db: Session, esc: Escalation, final_message: str, *, actor_id: str, now: datetime) -> Escalation:
    """Người duyệt chốt thông điệp cuối (đã sửa hay chưa) → APPROVED = được phép gửi (MVP: đánh dấu đã gửi)."""
    if esc.status != EscalationStatus.DRAFTED:
        raise EscalationStateError(f"Chỉ duyệt được escalation đã có nháp (hiện {esc.status})")
    assert_transition(ESCALATION_TRANSITIONS, esc.status, EscalationStatus.APPROVED)
    esc.status = EscalationStatus.APPROVED
    esc.final_message = final_message
    esc.approved_by = actor_id
    esc.approved_at = now
    record(
        db,
        actor_id,
        AuditAction.ESCALATION_APPROVED,
        {
            "escalation_id": esc.id,
            "work_order_id": esc.work_order_id,
            "final_message": final_message,
            "edited": final_message != esc.draft_message,
        },
        now=now,
    )  # commit
    return esc
