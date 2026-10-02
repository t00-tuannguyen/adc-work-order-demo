"""Bảng của Intake context — ADC-001 §Mô hình dữ liệu (T-017).

`work_orders.state` chỉ được ghi qua Orchestration (ADR-0003); intake chỉ tạo đơn ở DRAFT.
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, Boolean, Enum, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.modules.intake.confidence import FlagCode
from src.modules.intake.schemas import SourceKind, TicketSourceType
from src.modules.orchestration import WorkOrderState
from src.modules.types import Priority
from src.services.db import Base, UTCDateTime, utcnow


def _new_id() -> str:
    return uuid.uuid4().hex


def _enum(cls: type[StrEnum]) -> Enum:
    # Lưu dạng VARCHAR + CHECK (không dùng enum native) để SQLite và PostgreSQL giống nhau
    return Enum(cls, native_enum=False, validate_strings=True)


class IngestStep(StrEnum):
    """Tiến độ 4 bước hiển thị cho UI — GET /api/ingest-jobs/{job_id}."""

    UPLOADED = "UPLOADED"
    READING = "READING"
    DETECTING = "DETECTING"
    EXTRACTING = "EXTRACTING"
    DONE = "DONE"
    FAILED = "FAILED"


class IngestJobStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class ReviewStatus(StrEnum):
    """Kết quả cổng tin cậy (ADR-0007) lưu trên work order."""

    AUTO_ACCEPTED = "AUTO_ACCEPTED"
    ACCEPTED_WITH_WARNINGS = "ACCEPTED_WITH_WARNINGS"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"


class ClarificationStatus(StrEnum):
    OPEN = "OPEN"
    ANSWERED = "ANSWERED"


class WarningStatus(StrEnum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"


class TicketFile(Base):
    __tablename__ = "ticket_files"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_id)
    file_name: Mapped[str] = mapped_column(String(255))
    storage_path: Mapped[str] = mapped_column(Text)
    # Không unique: file trùng chỉ tạo cảnh báo POSSIBLE_DUPLICATE, không chặn (BR-13)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    size_bytes: Mapped[int] = mapped_column(Integer)
    page_count: Mapped[int | None] = mapped_column(Integer)
    has_text_layer: Mapped[bool | None] = mapped_column(Boolean)
    ocr_used: Mapped[bool] = mapped_column(Boolean, default=False)
    channel: Mapped[str | None] = mapped_column(String(32))
    received_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    uploaded_by: Mapped[str] = mapped_column(ForeignKey("users.id"))


class IngestJob(Base):
    __tablename__ = "ingest_jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_id)
    file_id: Mapped[str] = mapped_column(ForeignKey("ticket_files.id"))
    status: Mapped[IngestJobStatus] = mapped_column(_enum(IngestJobStatus), default=IngestJobStatus.QUEUED, index=True)
    step: Mapped[IngestStep] = mapped_column(_enum(IngestStep), default=IngestStep.UPLOADED)
    error_code: Mapped[str | None] = mapped_column(String(64))
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_id)
    file_id: Mapped[str | None] = mapped_column(ForeignKey("ticket_files.id"))  # None với TEXT / MANUAL
    source_type: Mapped[TicketSourceType] = mapped_column(_enum(TicketSourceType))
    raw_text: Mapped[str | None] = mapped_column(Text)
    page_from: Mapped[int | None] = mapped_column(Integer)
    page_to: Mapped[int | None] = mapped_column(Integer)
    # Order Agent không chắc ranh giới ticket trong file nhiều ticket → REVIEW (BR-12)
    boundary_uncertain: Mapped[bool] = mapped_column(Boolean, default=False)


class WorkOrder(Base):
    __tablename__ = "work_orders"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_id)
    ticket_id: Mapped[str] = mapped_column(ForeignKey("tickets.id"), unique=True)  # 1 ticket → 1 work order
    review_status: Mapped[ReviewStatus | None] = mapped_column(_enum(ReviewStatus), index=True)
    # 8 trường đã chuẩn hóa (cm, kg, kGy) — None khi nguồn không có (BR-01 xử lý ở validator)
    product_name: Mapped[str | None] = mapped_column(Text)
    product_group: Mapped[str | None] = mapped_column(String(64))  # gán ở ADC-002
    quantity: Mapped[int | None] = mapped_column(Integer)
    pkg_length_cm: Mapped[float | None] = mapped_column(Float)
    pkg_width_cm: Mapped[float | None] = mapped_column(Float)
    pkg_height_cm: Mapped[float | None] = mapped_column(Float)
    pkg_weight_kg: Mapped[float | None] = mapped_column(Float)
    required_dose_kgy: Mapped[float | None] = mapped_column(Float)
    priority: Mapped[Priority | None] = mapped_column(_enum(Priority))
    expected_arrival: Mapped[datetime | None] = mapped_column(UTCDateTime)
    requested_return: Mapped[datetime | None] = mapped_column(UTCDateTime, index=True)
    state: Mapped[WorkOrderState] = mapped_column(_enum(WorkOrderState), default=WorkOrderState.DRAFT, index=True)
    # Ước tính thời lượng (ADC-002) — tính khi vào FEASIBILITY_CHECK; None = chưa tính được (BR-02)
    estimated_duration_min: Mapped[int | None] = mapped_column(Integer)
    estimate_breakdown: Mapped[dict | None] = mapped_column(
        JSON
    )  # {setup, weight_load, volume_load, dose_load, buffer}
    config_version: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class FieldExtraction(Base):
    """Nguồn gốc từng trường: nhãn nguồn + trang/vùng trên PDF để highlight."""

    __tablename__ = "field_extractions"
    __table_args__ = (Index("ix_field_extractions_work_order_id_field", "work_order_id", "field"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    work_order_id: Mapped[str] = mapped_column(ForeignKey("work_orders.id"))
    field: Mapped[str] = mapped_column(String(64))
    value: Mapped[object | None] = mapped_column(JSON)  # giá trị đã chuẩn hóa, vd {"length":40,...} cho quy cách
    source_kind: Mapped[SourceKind] = mapped_column(_enum(SourceKind))
    page: Mapped[int | None] = mapped_column(Integer)
    bbox: Mapped[list[float] | None] = mapped_column(JSON)  # [x0, y0, x1, y1] theo toạ độ trang PDF
    snippet: Mapped[str | None] = mapped_column(Text)
    # Độ tin cậy OCR của vùng nguồn do code gắn, không phải LLM tự khai (ADR-0007); None = text layer / nhập tay
    confidence: Mapped[float | None] = mapped_column(Float)


class ClarificationRequest(Base):
    __tablename__ = "clarification_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    work_order_id: Mapped[str] = mapped_column(ForeignKey("work_orders.id"), index=True)
    field: Mapped[str] = mapped_column(String(64))
    question: Mapped[str] = mapped_column(Text)
    status: Mapped[ClarificationStatus] = mapped_column(_enum(ClarificationStatus), default=ClarificationStatus.OPEN)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    answered_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class IntakeWarning(Base):
    __tablename__ = "intake_warnings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    work_order_id: Mapped[str] = mapped_column(ForeignKey("work_orders.id"), index=True)
    field: Mapped[str | None] = mapped_column(String(64))  # None = cảnh báo cấp ticket (vd file trùng)
    code: Mapped[FlagCode] = mapped_column(_enum(FlagCode))
    status: Mapped[WarningStatus] = mapped_column(_enum(WarningStatus), default=WarningStatus.OPEN, index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)  # GET /api/intake-warnings trả về
    acknowledged_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    acknowledged_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    note: Mapped[str | None] = mapped_column(Text)
