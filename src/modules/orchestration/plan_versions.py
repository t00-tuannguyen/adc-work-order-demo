"""Plan version & danh sách thay đổi — ADC-006 §Mô hình dữ liệu (phần T-028, T-031 cần; duyệt/từ chối ở T-042).

`plan_versions.id` tăng dần chính là số version `{n}` trong `GET /api/schedule?version={n}`.
Chỉ Orchestration được tạo/đổi trạng thái plan version (ADR-0003).
"""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, Boolean, Enum, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.modules.orchestration.approval import ChangeType
from src.modules.orchestration.state_machine import PlanVersionStatus
from src.services.db import Base, UTCDateTime, utcnow


def _enum(cls: type[StrEnum]) -> Enum:
    return Enum(cls, native_enum=False, validate_strings=True)


class PlanTrigger(StrEnum):
    NEW_ORDER = "NEW_ORDER"
    INCIDENT = "INCIDENT"
    MANUAL = "MANUAL"


class PlanVersion(Base):
    __tablename__ = "plan_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    parent_version_id: Mapped[int | None] = mapped_column(ForeignKey("plan_versions.id"))
    trigger: Mapped[PlanTrigger] = mapped_column(_enum(PlanTrigger))
    status: Mapped[PlanVersionStatus] = mapped_column(_enum(PlanVersionStatus), index=True)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    approved_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    comment: Mapped[str | None] = mapped_column(Text)
    # trigger=INCIDENT: sự cố sinh ra phương án này (ADC-004)
    incident_id: Mapped[int | None] = mapped_column(ForeignKey("incidents.id"), index=True)


class PlanChange(Base):
    __tablename__ = "plan_changes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_version_id: Mapped[int] = mapped_column(ForeignKey("plan_versions.id"), index=True)
    work_order_id: Mapped[str] = mapped_column(ForeignKey("work_orders.id"), index=True)
    change_type: Mapped[ChangeType] = mapped_column(_enum(ChangeType))
    old_value: Mapped[dict | None] = mapped_column(JSON)
    # Gán line: {line, start, end, sla_ok, reason}
    new_value: Mapped[dict] = mapped_column(JSON)
    needs_approval: Mapped[bool] = mapped_column(Boolean, default=False)
