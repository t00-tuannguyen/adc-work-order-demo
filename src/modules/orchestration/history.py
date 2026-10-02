"""Lịch sử trạng thái work order — ADC-006 §Mô hình dữ liệu (T-041). Mỗi lần đổi `state` ghi 1 dòng.

Dòng đầu tiên của mỗi lệnh là lúc tạo (`from_state` rỗng → DRAFT). `actor_id` luôn là người dùng thật đã kích hoạt
(ADC-008); `actor_type` cho biết ai quyết định: USER bấm tay, SYSTEM luật deterministic tự chạy (tự xếp lịch, phương
án sự cố, escalation), AGENT bước do agent AI làm (tạo lệnh từ PDF).
"""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import Enum, ForeignKey, Index, Integer, Text, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from src.modules.orchestration.state_machine import WorkOrderState
from src.services.db import Base, UTCDateTime, utcnow


class ActorType(StrEnum):
    USER = "USER"
    AGENT = "AGENT"
    SYSTEM = "SYSTEM"


def _enum(cls: type[StrEnum]) -> Enum:
    return Enum(cls, native_enum=False, validate_strings=True)


class StateHistory(Base):
    __tablename__ = "state_history"
    __table_args__ = (Index("ix_state_history_work_order_id_at", "work_order_id", "at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    work_order_id: Mapped[str] = mapped_column(ForeignKey("work_orders.id"))
    from_state: Mapped[WorkOrderState | None] = mapped_column(_enum(WorkOrderState))
    to_state: Mapped[WorkOrderState] = mapped_column(_enum(WorkOrderState))
    actor_type: Mapped[ActorType] = mapped_column(_enum(ActorType))
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str] = mapped_column(Text, default="")
    plan_version_id: Mapped[int | None] = mapped_column(ForeignKey("plan_versions.id"))
    at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


def record_created(
    db: Session, work_order_id: str, *, actor_id: str, actor_type: ActorType, reason: str, now: datetime
) -> StateHistory:
    """Dòng mở đầu lịch sử: lệnh vừa tạo ở DRAFT. Không commit — đi cùng giao dịch tạo lệnh."""
    row = StateHistory(
        work_order_id=work_order_id,
        from_state=None,
        to_state=WorkOrderState.DRAFT,
        actor_type=actor_type,
        actor_id=actor_id,
        reason=reason,
        at=now,
    )
    db.add(row)
    return row


def work_order_history(db: Session, work_order_id: str) -> list[StateHistory]:
    """Timeline cũ → mới."""
    return list(
        db.scalars(
            select(StateHistory)
            .where(StateHistory.work_order_id == work_order_id)
            .order_by(StateHistory.at, StateHistory.id)
        )
    )
