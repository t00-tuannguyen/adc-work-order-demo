"""Xác nhận / sửa kết quả tiếp nhận — ADC-001, specs/api-contracts.md §1 (T-020).

PATCH trường → MANUAL + chạy lại validator & cổng tin cậy; submit đơn DRAFT → FEASIBILITY_CHECK;
xóa lệnh nháp; hàng đợi cảnh báo tiếp nhận + xác nhận đã xem. Mọi thao tác ghi audit gắn người dùng thật.
"""

from datetime import datetime
from enum import StrEnum

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.agents.graph import get_throughput_config
from src.agents.intake_pipeline import auto_schedule
from src.api.deps import require
from src.api.estimation import BreakdownOut, EstimateResponse
from src.modules.identity import Action, User
from src.modules.intake import (
    COLUMN_TO_EXTRACTION,
    EXTRACTION_COLUMNS,
    ClarificationRequest,
    ClarificationStatus,
    FieldExtraction,
    FlagCode,
    GateResult,
    IntakeWarning,
    ReviewStatus,
    ReviewThresholds,
    SourceKind,
    Ticket,
    TicketFile,
    TicketSignal,
    TicketSourceType,
    WarningStatus,
    WorkOrder,
    WorkOrderFields,
    apply_estimate,
    record_gate,
    run_gate,
    signals_from_extractions,
    try_estimate,
)
from src.modules.orchestration import AuditAction, StateHistory, WorkOrderState, record, transition_work_order
from src.modules.types import Priority
from src.services.db import get_db, utcnow

router = APIRouter(tags=["intake"], dependencies=[Depends(require(Action.UPLOAD_TICKET))])


class FieldsPatch(BaseModel):
    """Chỉ các trường gửi lên mới được sửa; gửi đúng giá trị cũ = xác nhận trường (→ MANUAL)."""

    model_config = ConfigDict(extra="forbid")

    product_name: str | None = Field(default=None, max_length=500)
    quantity: int | None = None
    pkg_length_cm: float | None = None
    pkg_width_cm: float | None = None
    pkg_height_cm: float | None = None
    pkg_weight_kg: float | None = None
    required_dose_kgy: float | None = None
    priority: Priority | None = None
    expected_arrival: datetime | None = None
    requested_return: datetime | None = None

    @field_validator("expected_arrival", "requested_return")
    @classmethod
    def _tz_aware(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            raise ValueError("thời gian phải có múi giờ (ISO 8601)")
        return v


class PatchRequest(BaseModel):
    fields: FieldsPatch


class ErrorOut(BaseModel):
    field: str
    code: str


class ExtractionOut(BaseModel):
    field: str
    value: object | None
    source_kind: SourceKind
    page: int | None
    bbox: list[float] | None
    snippet: str | None
    confidence: float | None


class ClarificationOut(BaseModel):
    field: str
    question: str
    status: ClarificationStatus


class ReviewWarningOut(BaseModel):
    id: int
    field: str | None
    code: FlagCode
    status: WarningStatus


class SourceOut(BaseModel):
    type: TicketSourceType
    file_id: str | None
    file_name: str | None
    page_count: int | None
    page_from: int | None
    page_to: int | None
    ocr_used: bool | None
    channel: str | None
    received_at: datetime | None
    raw_text: str | None


class WorkOrderReview(BaseModel):
    id: str
    state: WorkOrderState
    review_status: ReviewStatus | None
    fields: WorkOrderFields
    boundary_uncertain: bool
    errors: list[ErrorOut]
    unconfirmed_fields: list[str]
    can_submit: bool
    extractions: list[ExtractionOut]
    clarifications: list[ClarificationOut]
    warnings: list[ReviewWarningOut]
    source: SourceOut
    estimate: EstimateResponse | None = None  # ADC-002 — có khi lệnh đã vào FEASIBILITY_CHECK
    estimate_error: str | None = None  # lý do chưa ước tính được (BR-02)


class WarningFilter(StrEnum):
    open = "open"
    acknowledged = "acknowledged"


class WarningOut(BaseModel):
    id: int
    work_order_id: str
    field: str | None
    code: FlagCode
    created_at: datetime


class AckRequest(BaseModel):
    note: str | None = Field(default=None, max_length=2000)


def _get(db: Session, work_order_id: str) -> WorkOrder:
    wo = db.get(WorkOrder, work_order_id)
    if wo is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy lệnh")
    return wo


def _fields(wo: WorkOrder) -> WorkOrderFields:
    return WorkOrderFields(**{name: getattr(wo, name) for name in WorkOrderFields.model_fields})


def _extractions(db: Session, wo: WorkOrder) -> list[FieldExtraction]:
    return list(db.scalars(select(FieldExtraction).where(FieldExtraction.work_order_id == wo.id)))


def _gate(db: Session, wo: WorkOrder) -> tuple[GateResult, Ticket]:
    ticket = db.get(Ticket, wo.ticket_id)
    gate = run_gate(
        _fields(wo),
        signals_from_extractions(_extractions(db, wo)),
        ReviewThresholds.from_config(get_throughput_config().raw),
        ticket=TicketSignal(boundary_uncertain=ticket.boundary_uncertain),
    )
    return gate, ticket


def _review(db: Session, wo: WorkOrder) -> WorkOrderReview:
    gate, ticket = _gate(db, wo)
    clarifications = db.scalars(
        select(ClarificationRequest)
        .where(ClarificationRequest.work_order_id == wo.id)
        .order_by(ClarificationRequest.id)
    )
    warnings = db.scalars(select(IntakeWarning).where(IntakeWarning.work_order_id == wo.id).order_by(IntakeWarning.id))
    f = db.get(TicketFile, ticket.file_id) if ticket.file_id else None
    is_draft = wo.state == WorkOrderState.DRAFT
    estimate, estimate_error = _estimate(wo, is_draft)
    return WorkOrderReview(
        id=wo.id,
        state=wo.state,
        review_status=wo.review_status,
        fields=_fields(wo),
        boundary_uncertain=ticket.boundary_uncertain,
        errors=[ErrorOut(field=e.field, code=e.code) for e in gate.errors],
        unconfirmed_fields=gate.unconfirmed_fields if is_draft else [],
        can_submit=is_draft and not gate.errors and not gate.unconfirmed_fields,
        extractions=[ExtractionOut.model_validate(e, from_attributes=True) for e in _extractions(db, wo)],
        clarifications=[ClarificationOut.model_validate(c, from_attributes=True) for c in clarifications],
        warnings=[ReviewWarningOut.model_validate(w, from_attributes=True) for w in warnings],
        source=SourceOut(
            type=ticket.source_type,
            file_id=f.id if f else None,
            file_name=f.file_name if f else None,
            page_count=f.page_count if f else None,
            page_from=ticket.page_from,
            page_to=ticket.page_to,
            ocr_used=f.ocr_used if f else None,
            channel=f.channel if f else None,
            received_at=f.received_at if f else None,
            raw_text=ticket.raw_text,
        ),
        estimate=estimate,
        estimate_error=estimate_error,
    )


def _estimate(wo: WorkOrder, is_draft: bool) -> tuple[EstimateResponse | None, str | None]:
    if wo.estimated_duration_min is not None:
        return (
            EstimateResponse(
                duration_min=wo.estimated_duration_min,
                breakdown=BreakdownOut(**wo.estimate_breakdown),
                config_version=wo.config_version,
            ),
            None,
        )
    if is_draft:
        return None, None
    result = try_estimate(wo, get_throughput_config())
    return None, result if isinstance(result, str) else None


@router.get("/work-orders/{work_order_id}/intake", response_model=WorkOrderReview)
def get_work_order_intake(work_order_id: str, db: Session = Depends(get_db)) -> WorkOrderReview:
    """Dữ liệu màn xác nhận ticket (T-021)."""
    return _review(db, _get(db, work_order_id))


@router.patch("/work-orders/{work_order_id}", response_model=WorkOrderReview)
def patch_work_order(
    work_order_id: str,
    body: PatchRequest,
    user: User = Depends(require(Action.UPLOAD_TICKET)),
    db: Session = Depends(get_db),
) -> WorkOrderReview:
    wo = _get(db, work_order_id)
    if wo.state != WorkOrderState.DRAFT:
        # TODO(ADC-003/006): sửa đơn đã qua tiếp nhận → plan version mới theo luật duyệt ADR-0005
        raise HTTPException(status_code=409, detail="Chỉ sửa được lệnh đang ở DRAFT")
    changes = body.fields.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=422, detail="Không có trường nào để sửa")
    before = {c: getattr(wo, c) for c in changes}
    for column, value in changes.items():
        setattr(wo, column, value)

    rows = {r.field: r for r in _extractions(db, wo)}
    for name in dict.fromkeys(COLUMN_TO_EXTRACTION[c] for c in changes):
        value = _extraction_value(wo, name)
        row = rows.get(name) or FieldExtraction(work_order_id=wo.id, field=name)
        # Người đã nhập / xác nhận → MANUAL, bỏ độ tin cậy OCR; giữ trang / vùng nguồn để còn đối chiếu
        row.value, row.source_kind, row.confidence = value, SourceKind.MANUAL, None
        db.add(row)
    db.flush()

    now = utcnow()
    gate, _ = _gate(db, wo)
    record_gate(db, wo, gate, now=now, auto=False)
    db.commit()
    record(
        db,
        user.id,
        AuditAction.WORK_ORDER_FIELDS_EDITED,
        {
            "work_order_id": wo.id,
            "changes": jsonable_encoder({c: [before[c], changes[c]] for c in changes}),
        },
        now=now,
    )
    return _review(db, wo)


@router.delete("/work-orders/{work_order_id}", status_code=204)
def delete_work_order(
    work_order_id: str,
    user: User = Depends(require(Action.UPLOAD_TICKET)),
    db: Session = Depends(get_db),
) -> Response:
    """Xóa lệnh nháp (nhập nhầm / ticket rác): lệnh + ticket + dữ liệu tiếp nhận; giữ file PDF gốc (có thể chứa ticket khác)."""
    wo = _get(db, work_order_id)
    if wo.state != WorkOrderState.DRAFT:
        # Lệnh đã qua tiếp nhận có thể đã vào lịch / ảnh hưởng khách → không xóa (BR-08)
        raise HTTPException(status_code=409, detail="Chỉ xóa được lệnh đang ở DRAFT")
    ticket = db.get(Ticket, wo.ticket_id)
    snapshot = jsonable_encoder(_fields(wo))
    # Lịch sử chỉ có dòng tạo lệnh; audit WORK_ORDER_DELETED giữ dấu vết
    for model in (FieldExtraction, ClarificationRequest, IntakeWarning, StateHistory):
        db.execute(delete(model).where(model.work_order_id == wo.id))
    db.delete(wo)
    db.flush()  # xóa lệnh trước ticket (khóa ngoại work_orders.ticket_id)
    db.delete(ticket)
    db.commit()
    record(
        db,
        user.id,
        AuditAction.WORK_ORDER_DELETED,
        {
            "work_order_id": work_order_id,
            "ticket_id": ticket.id,
            "source": ticket.source_type.value,
            "file_id": ticket.file_id,
            "fields": snapshot,
        },
        now=utcnow(),
    )
    return Response(status_code=204)


@router.post("/work-orders/{work_order_id}/submit", response_model=WorkOrderReview)
def submit_work_order(
    work_order_id: str,
    user: User = Depends(require(Action.UPLOAD_TICKET)),
    db: Session = Depends(get_db),
) -> WorkOrderReview:
    wo = _get(db, work_order_id)
    if wo.state != WorkOrderState.DRAFT:
        raise HTTPException(status_code=409, detail="Chỉ submit được lệnh đang ở DRAFT")
    gate, _ = _gate(db, wo)
    if gate.errors or gate.unconfirmed_fields:
        # BR-01: thiếu trường không vào FEASIBILITY_CHECK; BR-12: trường tin cậy thấp phải được người xác nhận
        raise HTTPException(
            status_code=422,
            detail={
                "errors": [{"field": e.field, "code": e.code} for e in gate.errors],
                "unconfirmed_fields": gate.unconfirmed_fields,
            },
        )
    apply_estimate(wo, get_throughput_config())  # ADC-002: commit cùng dòng audit chuyển trạng thái
    now = utcnow()
    transition_work_order(
        db, wo, WorkOrderState.FEASIBILITY_CHECK, actor_id=user.id, reason="người dùng xác nhận ticket", now=now
    )
    auto_schedule(db, wo, actor_id=user.id, now=now)  # ADC-003: hệ thống xếp lịch, Kinh doanh không sửa lịch
    return _review(db, wo)


@router.get("/intake-warnings", response_model=list[WarningOut])
def list_intake_warnings(
    status: WarningFilter = Query(WarningFilter.open), db: Session = Depends(get_db)
) -> list[IntakeWarning]:
    wanted = WarningStatus.OPEN if status == WarningFilter.open else WarningStatus.ACKNOWLEDGED
    stmt = select(IntakeWarning).where(IntakeWarning.status == wanted).order_by(IntakeWarning.created_at.desc())
    return list(db.scalars(stmt))


@router.post("/intake-warnings/{warning_id}/ack", response_model=WarningOut)
def ack_intake_warning(
    warning_id: int,
    body: AckRequest,
    user: User = Depends(require(Action.UPLOAD_TICKET)),
    db: Session = Depends(get_db),
) -> IntakeWarning:
    w = db.get(IntakeWarning, warning_id)
    if w is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy cảnh báo")
    if w.status == WarningStatus.ACKNOWLEDGED:
        raise HTTPException(status_code=409, detail="Cảnh báo đã được xác nhận")
    now = utcnow()
    w.status, w.acknowledged_by, w.acknowledged_at, w.note = WarningStatus.ACKNOWLEDGED, user.id, now, body.note
    db.commit()
    record(
        db,
        user.id,
        AuditAction.INTAKE_WARNING_ACKNOWLEDGED,
        {"warning_id": w.id, "work_order_id": w.work_order_id, "code": w.code, "note": body.note},
        now=now,
    )
    return w


def _extraction_value(wo: WorkOrder, name: str) -> object | None:
    columns = EXTRACTION_COLUMNS[name]
    if name == "package_dimensions_cm":
        length, width, height = (getattr(wo, c) for c in columns)
        return {"length": length, "width": width, "height": height}
    return jsonable_encoder(getattr(wo, columns[0]))
