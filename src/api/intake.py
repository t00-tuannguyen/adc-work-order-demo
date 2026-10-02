"""Intake API — ADC-001, specs/api-contracts.md §1 (T-018 upload + job; T-021 dán nội dung / nhập tay, file gốc)."""

from collections.abc import Sequence
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session, sessionmaker

from src.agents.graph import get_throughput_config
from src.agents.intake_pipeline import GateConfig, OrderAgentPipeline, create_tickets, create_work_orders
from src.agents.order_agent import ExtractionFailedError, GeminiOrderAgent, PdfExtractor
from src.api.deps import require
from src.modules.identity import Action, User
from src.modules.intake import (
    PROGRESS,
    IngestJobStatus,
    IngestStage,
    IngestStep,
    InvalidPdfError,
    NotPdfError,
    ReviewStatus,
    ReviewThresholds,
    Ticket,
    TicketFile,
    TicketSourceType,
    WorkOrder,
    WorkOrderFields,
    create_ingest,
    job_work_orders,
    record_gate,
    run_gate,
    run_ingest_job,
)
from src.modules.intake.models import IngestJob
from src.modules.orchestration import ActorType, AuditAction, WorkOrderState, record, record_created
from src.services.db import get_db, get_session_factory, utcnow
from src.services.gemini import get_gemini_client
from src.services.storage import FileTooLargeError
from src.settings import Settings, get_settings

# Kinh doanh / Điều phối (specs/user-roles.md §2)
router = APIRouter(tags=["intake"])


def get_order_agent(settings: Settings = Depends(get_settings)) -> PdfExtractor | None:
    """Order Agent (Gemini, ADR-0010). Chưa cấu hình GEMINI_API_KEY → None."""
    if not settings.gemini_api_key:
        return None
    return GeminiOrderAgent(get_gemini_client(), settings.gemini_model)


def gate_config() -> GateConfig:
    return GateConfig(ReviewThresholds.from_config(get_throughput_config().raw), allowed_doses())


def get_ingest_stages(
    settings: Settings = Depends(get_settings), agent: PdfExtractor | None = Depends(get_order_agent)
) -> Sequence[IngestStage] | None:
    """Các bước xử lý sau upload: Gemini đọc/OCR + trích xuất. Mỗi request 1 pipeline mới.

    Chưa có Order Agent → None: job nằm ở QUEUED/UPLOADED, không chạy nền.
    """
    if agent is None:
        return None
    cfg = gate_config()
    return OrderAgentPipeline(
        agent, cfg.thresholds, ocr_enabled=settings.feature_ocr, allowed_doses=cfg.allowed_doses
    ).stages()


def allowed_doses() -> list[str]:
    """Liều có trong danh mục cấu hình — liều khác cần khách xác nhận (ADC-001, BR-02)."""
    return [k for k, v in get_throughput_config().dose_factor.items() if v is not None]


class UploadAccepted(BaseModel):
    job_id: str
    file_id: str


class JobWorkOrder(BaseModel):
    id: str
    review_status: ReviewStatus | None
    state: WorkOrderState


class IngestJobOut(BaseModel):
    status: IngestJobStatus
    step: IngestStep
    progress: int
    work_orders: list[JobWorkOrder]
    error_code: str | None


@router.post("/tickets/upload", status_code=202, response_model=UploadAccepted)
def upload_ticket(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    channel: str | None = Form(None, max_length=32),
    received_at: datetime | None = Form(None),
    user: User = Depends(require(Action.UPLOAD_TICKET)),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    session_factory: sessionmaker[Session] = Depends(get_session_factory),
    stages: Sequence[IngestStage] | None = Depends(get_ingest_stages),
) -> UploadAccepted:
    if received_at is not None and received_at.tzinfo is None:
        raise HTTPException(status_code=422, detail="received_at phải có múi giờ (ISO 8601)")
    try:
        ticket_file, job = create_ingest(
            db,
            file.file,
            file_name=file.filename or "",
            upload_dir=Path(settings.upload_dir),
            max_bytes=settings.max_upload_mb * 1024 * 1024,
            max_pages=settings.max_pdf_pages,
            uploaded_by=user.id,
            channel=channel,
            received_at=received_at or utcnow(),
        )
    except FileTooLargeError:
        raise HTTPException(status_code=413, detail=f"File vượt {settings.max_upload_mb} MB") from None
    except NotPdfError:
        raise HTTPException(status_code=415, detail="Chỉ nhận file PDF") from None
    except InvalidPdfError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    record(
        db,
        user.id,
        AuditAction.TICKET_UPLOADED,
        {
            "file_id": ticket_file.id,
            "job_id": job.id,
            "sha256": ticket_file.sha256,
            "size_bytes": ticket_file.size_bytes,
        },
        now=utcnow(),
    )
    if stages is not None:
        background.add_task(run_ingest_job, session_factory, job.id, stages, now=utcnow)
    return UploadAccepted(job_id=job.id, file_id=ticket_file.id)


@router.get(
    "/ingest-jobs/{job_id}",
    response_model=IngestJobOut,
    dependencies=[Depends(require(Action.UPLOAD_TICKET))],
)
def get_ingest_job(job_id: str, db: Session = Depends(get_db)) -> IngestJobOut:
    job = db.get(IngestJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy job")
    return IngestJobOut(
        status=job.status,
        step=job.step,
        progress=PROGRESS[job.step],
        work_orders=[
            JobWorkOrder(id=wo.id, review_status=wo.review_status, state=wo.state) for wo in job_work_orders(db, job)
        ],
        error_code=job.error_code,
    )


class TicketSource(StrEnum):
    TEXT = "TEXT"
    MANUAL = "MANUAL"


class TicketCreate(BaseModel):
    raw_text: str | None = Field(default=None, max_length=20_000)
    source: TicketSource
    received_at: datetime | None = None

    @field_validator("received_at")
    @classmethod
    def _tz_aware(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            raise ValueError("received_at phải có múi giờ (ISO 8601)")
        return v


class TicketCreated(BaseModel):
    work_orders: list[JobWorkOrder]


@router.post("/tickets", status_code=201, response_model=TicketCreated)
def create_ticket(
    body: TicketCreate,
    user: User = Depends(require(Action.UPLOAD_TICKET)),
    db: Session = Depends(get_db),
    agent: PdfExtractor | None = Depends(get_order_agent),
) -> TicketCreated:
    """Tab "Dán nội dung" (TEXT) và chế độ nhập tay (MANUAL) — dự phòng khi PDF/OCR lỗi (ADC-001)."""
    now = utcnow()
    if body.source == TicketSource.MANUAL:
        orders = [_manual_work_order(db, user.id, now)]
    else:
        if not (body.raw_text or "").strip():
            raise HTTPException(status_code=422, detail="Nội dung dán đang trống")
        if agent is None:
            raise HTTPException(status_code=503, detail="Chưa cấu hình Order Agent (GEMINI_API_KEY)")
        try:
            doc = agent.extract_text(body.raw_text, received_at=body.received_at or now)
        except ExtractionFailedError:
            raise HTTPException(status_code=502, detail="Order Agent không trích xuất được, hãy nhập tay") from None
        if not doc.tickets:
            raise HTTPException(status_code=422, detail="Không nhận ra ticket nào trong nội dung dán")
        tickets = create_tickets(db, doc, source_type=TicketSourceType.TEXT, raw_text=body.raw_text)
        orders = create_work_orders(db, tickets, doc, gate_config(), actor_id=user.id, now=now)
    record(
        db,
        user.id,
        AuditAction.TICKET_CREATED,
        {"source": body.source.value, "work_orders": [wo.id for wo in orders]},
        now=now,
    )
    return TicketCreated(
        work_orders=[JobWorkOrder(id=wo.id, review_status=wo.review_status, state=wo.state) for wo in orders]
    )


def _manual_work_order(db: Session, actor_id: str, now: datetime) -> WorkOrder:
    """Lệnh DRAFT trống: mọi trường bắt buộc thiếu → NEEDS_CLARIFICATION, người nhập qua PATCH rồi submit."""
    ticket = Ticket(source_type=TicketSourceType.MANUAL)
    db.add(ticket)
    db.flush()
    wo = WorkOrder(ticket_id=ticket.id)
    db.add(wo)
    db.flush()
    record_created(db, wo.id, actor_id=actor_id, actor_type=ActorType.USER, reason="nhập tay", now=now)
    cfg = gate_config()
    record_gate(
        db, wo, run_gate(WorkOrderFields(), {}, cfg.thresholds, allowed_doses=cfg.allowed_doses), now=now, auto=False
    )
    db.commit()
    return wo


@router.get("/files/{file_id}", dependencies=[Depends(require(Action.UPLOAD_TICKET))])
def get_file(file_id: str, db: Session = Depends(get_db)) -> FileResponse:
    """File PDF gốc để nhúng trình xem PDF của trình duyệt (không highlight — T-021)."""
    f = db.get(TicketFile, file_id)
    if f is None or not Path(f.storage_path).is_file():
        raise HTTPException(status_code=404, detail="Không tìm thấy file")
    return FileResponse(
        f.storage_path,
        media_type="application/pdf",
        filename=f.file_name,
        content_disposition_type="inline",
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"},
    )
