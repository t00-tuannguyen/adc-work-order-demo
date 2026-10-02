"""Bảng của Scheduling context — ADC-003 §Mô hình dữ liệu (T-028), ADC-004 §Mô hình dữ liệu (T-031).

Slot thuộc 1 plan version; mỗi version chứa toàn bộ lịch 2 line. Không chồng lấn kiểm tra ở tầng service (BR-04).
Giờ vận hành line lấy từ cấu hình (giả định MVP 24/7) — bảng `lines` để ADC-004 khi cần trạng thái line.
"""

from datetime import datetime, timedelta
from enum import StrEnum

from sqlalchemy import Enum, ForeignKey, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.modules.scheduling.incident import AffectedOutcome
from src.modules.types import Line
from src.services.db import Base, UTCDateTime, utcnow


def _enum(cls: type[StrEnum]) -> Enum:
    return Enum(cls, native_enum=False, validate_strings=True)


class ScheduleSlot(Base):
    __tablename__ = "schedule_slots"
    __table_args__ = (Index("ix_schedule_slots_plan_version_id_line_start_at", "plan_version_id", "line", "start_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_version_id: Mapped[int] = mapped_column(ForeignKey("plan_versions.id"))
    work_order_id: Mapped[str] = mapped_column(ForeignKey("work_orders.id"), index=True)
    line: Mapped[Line] = mapped_column(_enum(Line))
    start_at: Mapped[datetime] = mapped_column(UTCDateTime)
    end_at: Mapped[datetime] = mapped_column(UTCDateTime)


class IncidentStatus(StrEnum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"


class LineIncident(Base):
    """1 sự cố line (FR 06). `id` tăng dần là `incident_id` trong API."""

    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    line: Mapped[Line] = mapped_column(_enum(Line))
    start_at: Mapped[datetime] = mapped_column(UTCDateTime)
    est_downtime_min: Mapped[int] = mapped_column(Integer)
    actual_end_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    status: Mapped[IncidentStatus] = mapped_column(_enum(IncidentStatus), default=IncidentStatus.OPEN, index=True)
    note: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    @property
    def end_at(self) -> datetime:
        """Giờ hồi phục: thực tế nếu đã resolve, ngược lại theo thời gian dừng dự kiến."""
        return self.actual_end_at or self.start_at + timedelta(minutes=self.est_downtime_min)


class IncidentAffectedOrder(Base):
    """Đơn bị 1 phương án sự cố dời/hoãn. `new_slot_id` thuộc plan version đề xuất của phương án đó."""

    __tablename__ = "incident_affected_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id"), index=True)
    work_order_id: Mapped[str] = mapped_column(ForeignKey("work_orders.id"), index=True)
    old_slot_id: Mapped[int] = mapped_column(ForeignKey("schedule_slots.id"))
    new_slot_id: Mapped[int | None] = mapped_column(ForeignKey("schedule_slots.id"))
    outcome: Mapped[AffectedOutcome] = mapped_column(_enum(AffectedOutcome))
