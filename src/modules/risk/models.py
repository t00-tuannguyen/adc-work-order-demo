"""Bảng của Risk context — ADC-005 §Mô hình dữ liệu.

`risk_checks`: mỗi lần kiểm tra rủi ro đơn mới (POST /risk-check hoặc khi xếp lịch), so với plan version ACTIVE
lúc kiểm tra (null khi chưa có lịch).
`escalations` (T-037): mục việc cho kinh doanh về 1 đơn trễ giờ trả. Mỗi đơn có tối đa 1 escalation đang mở
(OPEN / DRAFTED); phương án mới đổi số phút trễ → cập nhật mục đang mở. Giờ xong dự kiến = giờ trả + `delay_min`.
"""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, Enum, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.modules.risk.levels import EscalationStatus, RiskLevel
from src.services.db import Base, UTCDateTime, utcnow


def _enum(cls: type[StrEnum]) -> Enum:
    return Enum(cls, native_enum=False, validate_strings=True)


class RiskCheck(Base):
    __tablename__ = "risk_checks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    work_order_id: Mapped[str] = mapped_column(ForeignKey("work_orders.id"), index=True)
    plan_version_id: Mapped[int | None] = mapped_column(ForeignKey("plan_versions.id"))
    level: Mapped[RiskLevel] = mapped_column(_enum(RiskLevel))
    reasons: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


OPEN_ESCALATION: frozenset[EscalationStatus] = frozenset({EscalationStatus.OPEN, EscalationStatus.DRAFTED})


class Escalation(Base):
    __tablename__ = "escalations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    work_order_id: Mapped[str] = mapped_column(ForeignKey("work_orders.id"), index=True)
    incident_id: Mapped[int | None] = mapped_column(ForeignKey("incidents.id"))
    delay_min: Mapped[int] = mapped_column(Integer)
    status: Mapped[EscalationStatus] = mapped_column(_enum(EscalationStatus), default=EscalationStatus.OPEN, index=True)
    draft_message: Mapped[str | None] = mapped_column(Text)
    final_message: Mapped[str | None] = mapped_column(Text)
    approved_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
