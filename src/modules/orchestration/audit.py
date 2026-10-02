"""Audit log chỉ ghi thêm (BR-10) — ADC-006 §Mô hình dữ liệu. Mọi dòng gắn người dùng thật (ADC-008, T-053).

Phần tối thiểu của T-041 cần cho T-053; state_history và API xem audit làm ở T-041.
"""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, ForeignKey, Integer, String, event
from sqlalchemy.orm import Mapped, Session, mapped_column

from src.services.db import Base, UTCDateTime, utcnow


class AuditAction(StrEnum):
    LOGIN = "LOGIN"
    DEMO_LOGIN = "DEMO_LOGIN"
    LOGOUT = "LOGOUT"
    LOGOUT_ALL = "LOGOUT_ALL"
    SIGNUP_REQUESTED = "SIGNUP_REQUESTED"
    USER_UPDATED = "USER_UPDATED"
    TICKET_UPLOADED = "TICKET_UPLOADED"
    TICKET_EXTRACTED = "TICKET_EXTRACTED"
    TICKET_CREATED = "TICKET_CREATED"
    WORK_ORDER_STATE_CHANGED = "WORK_ORDER_STATE_CHANGED"
    WORK_ORDER_FIELDS_EDITED = "WORK_ORDER_FIELDS_EDITED"
    WORK_ORDER_DELETED = "WORK_ORDER_DELETED"
    INTAKE_WARNING_ACKNOWLEDGED = "INTAKE_WARNING_ACKNOWLEDGED"
    DEMO_RESET = "DEMO_RESET"
    PLAN_VERSION_CREATED = "PLAN_VERSION_CREATED"
    PLAN_VERSION_APPROVED = "PLAN_VERSION_APPROVED"
    PLAN_VERSION_REJECTED = "PLAN_VERSION_REJECTED"
    INCIDENT_DECLARED = "INCIDENT_DECLARED"
    INCIDENT_RESOLVED = "INCIDENT_RESOLVED"
    ESCALATION_CREATED = "ESCALATION_CREATED"
    ESCALATION_UPDATED = "ESCALATION_UPDATED"
    ESCALATION_DRAFTED = "ESCALATION_DRAFTED"
    ESCALATION_APPROVED = "ESCALATION_APPROVED"


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)


class AuditLogImmutableError(Exception):
    pass


@event.listens_for(AuditLog, "before_update")
@event.listens_for(AuditLog, "before_delete")
def _forbid_mutation(mapper, connection, target):
    raise AuditLogImmutableError("audit_log chỉ ghi thêm (BR-10)")


def record(db: Session, actor_id: str, action: AuditAction, payload: dict | None = None, *, now: datetime) -> AuditLog:
    """Ghi 1 dòng audit. Không có người dùng thật → lỗi, không ghi tài khoản chung."""
    if not actor_id:
        raise ValueError("audit_log cần actor_id của người dùng thật")
    entry = AuditLog(actor_id=actor_id, action=action.value, payload=payload or {}, at=now)
    db.add(entry)
    db.commit()
    return entry
