"""Các bước của ingest job sau upload (ADC-001 §Kiến trúc): Đọc PDF/OCR → Nhận diện ticket → Trích xuất.

Gemini làm cả 3 việc trong 1 lời gọi (ADR-0010) ở bước READING; 2 bước sau chỉ ghi kết quả vào DB
để UI thấy tiến độ đúng 4 bước. Mỗi job dùng 1 instance (giữ kết quả giữa các bước).
EXTRACTING chạy validator + cổng tin cậy (T-020): AUTO/WARN tự vào FEASIBILITY_CHECK qua Orchestration,
thiếu trường / tin cậy thấp giữ DRAFT. Vào FEASIBILITY_CHECK → gắn ước tính thời lượng (ADC-002).
Vào FEASIBILITY_CHECK → hệ thống tự xếp lịch (`auto_schedule`, ADC-003): OK → SCHEDULED, WARN → PENDING_APPROVAL
chờ quản lý duyệt, BLOCK → BLOCK_NEW_ORDER; không xếp được → giữ FEASIBILITY_CHECK cho Điều phối xếp tay.
Tab "Dán nội dung" (T-021) dùng chung `create_tickets` + `create_work_orders`.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.agents.graph import get_shift_policy, get_throughput_config
from src.agents.order_agent import ExtractionFailedError, PdfExtractor, normalize
from src.agents.schemas import DocumentExtraction
from src.modules.intake import (
    FieldExtraction,
    IngestError,
    IngestJob,
    IngestStage,
    IngestStep,
    ReviewThresholds,
    Ticket,
    TicketFile,
    TicketSignal,
    TicketSourceType,
    WorkOrder,
    apply_estimate,
    check_ocr_allowed,
    record_gate,
    run_gate,
)
from src.modules.orchestration import (
    ActorType,
    AuditAction,
    MissingEstimateError,
    NewOrderBlockedError,
    NotSchedulableError,
    PlanConflictError,
    WorkOrderState,
    record,
    record_created,
    schedule_work_order,
    transition_work_order,
)
from src.modules.scheduling import UnschedulableError
from src.settings import get_settings


def auto_schedule(db: Session, wo: WorkOrder, *, actor_id: str, now: datetime) -> None:
    """Tự xếp lịch đơn vừa vào FEASIBILITY_CHECK theo luật earliest feasible + kiểm tra rủi ro (BR-07).

    Không ném lỗi: BLOCK đã chuyển đơn sang BLOCK_NEW_ORDER; thiếu ước tính / không có khe / xung đột lịch
    → giữ FEASIBILITY_CHECK để Điều phối xếp tay.
    """

    def load(ids):
        return {o.id: o for o in db.scalars(select(WorkOrder).where(WorkOrder.id.in_(list(ids))))}

    tz = get_settings().local_tz
    try:
        schedule_work_order(
            db,
            wo,
            actor_id=actor_id,
            now=now,
            tz=tz,
            load_orders=load,
            shifts=get_shift_policy(tz),
            actor_type=ActorType.SYSTEM,
        )
    except NewOrderBlockedError:
        pass
    except (NotSchedulableError, MissingEstimateError, UnschedulableError, PlanConflictError):
        db.rollback()


@dataclass(frozen=True)
class GateConfig:
    thresholds: ReviewThresholds
    allowed_doses: list[str] | None = None


def create_tickets(
    db: Session,
    doc: DocumentExtraction,
    *,
    source_type: TicketSourceType,
    file_id: str | None = None,
    raw_text: str | None = None,
) -> list[Ticket]:
    tickets = [
        Ticket(
            file_id=file_id,
            source_type=source_type,
            raw_text=raw_text,
            page_from=t.page_from,
            page_to=t.page_to,
            boundary_uncertain=t.boundary_uncertain,
        )
        for t in doc.tickets
    ]
    db.add_all(tickets)
    db.commit()
    return tickets


def create_work_orders(
    db: Session,
    tickets: list[Ticket],
    doc: DocumentExtraction,
    gate_config: GateConfig,
    *,
    actor_id: str,
    now: datetime,
    duplicate: bool = False,
) -> list[WorkOrder]:
    """Mỗi ticket → 1 work order DRAFT + nguồn từng trường; chạy cổng; AUTO/WARN tự vào FEASIBILITY_CHECK."""
    orders: list[WorkOrder] = []
    to_advance: list[WorkOrder] = []
    for ticket, extracted in zip(tickets, doc.tickets, strict=True):
        n = normalize(extracted, gate_config.thresholds)
        wo = WorkOrder(ticket_id=ticket.id, **n.fields.model_dump())
        db.add(wo)
        db.flush()
        record_created(
            db,
            wo.id,
            actor_id=actor_id,
            actor_type=ActorType.AGENT,
            reason=f"Order Agent trích xuất ticket {ticket.source_type.value}",
            now=now,
        )
        db.add_all(
            FieldExtraction(
                work_order_id=wo.id,
                field=s.field,
                value=s.value,
                source_kind=s.source_kind,
                page=s.page,
                bbox=s.bbox,
                snippet=s.snippet,
                confidence=s.confidence,
            )
            for s in n.sources
        )
        gate = run_gate(
            n.fields,
            n.signals,
            gate_config.thresholds,
            ticket=TicketSignal(boundary_uncertain=extracted.boundary_uncertain, possible_duplicate=duplicate),
            allowed_doses=gate_config.allowed_doses,
        )
        record_gate(db, wo, gate, now=now)
        orders.append(wo)
        if gate.proceeds:
            apply_estimate(wo, get_throughput_config())
            to_advance.append(wo)
    db.commit()
    # Rõ ràng / chỉ cần cảnh báo → tự đi tiếp, không chờ người (ADR-0007). Người gửi ticket là actor.
    for wo in to_advance:
        transition_work_order(
            db,
            wo,
            WorkOrderState.FEASIBILITY_CHECK,
            actor_id=actor_id,
            reason=f"tiếp nhận tự động: {wo.review_status}",
            now=now,
            actor_type=ActorType.SYSTEM,
        )
        auto_schedule(db, wo, actor_id=actor_id, now=now)
    return orders


class OrderAgentPipeline:
    def __init__(
        self,
        extractor: PdfExtractor,
        thresholds: ReviewThresholds,
        *,
        ocr_enabled: bool,
        allowed_doses: Iterable[str] | None = None,
        now=None,
    ):
        self.extractor, self.ocr_enabled = extractor, ocr_enabled
        self.gate = GateConfig(thresholds, list(allowed_doses) if allowed_doses is not None else None)
        self.now = now or (lambda: datetime.now().astimezone())
        self.document: DocumentExtraction | None = None
        self.tickets: list[Ticket] = []

    def stages(self) -> list[IngestStage]:
        return [
            IngestStage(IngestStep.READING, self.read),
            IngestStage(IngestStep.DETECTING, self.detect),
            IngestStage(IngestStep.EXTRACTING, self.extract),
        ]

    def read(self, db: Session, job: IngestJob) -> None:
        f = db.get(TicketFile, job.file_id)
        check_ocr_allowed(f, enabled=self.ocr_enabled)
        try:
            doc = self.extractor.extract_pdf(
                Path(f.storage_path).read_bytes(), page_count=f.page_count or 1, received_at=f.received_at or self.now()
            )
        except ExtractionFailedError as e:
            # Sai schema / timeout sau khi đã thử lại → UI chuyển nhập tay, vẫn xem được file gốc (TC6, TC9)
            raise IngestError("OCR_FAILED", str(e)) from e
        if not doc.tickets:
            raise IngestError("OCR_FAILED", "không đọc được ticket nào trong file")
        self.document = doc

    def detect(self, db: Session, job: IngestJob) -> None:
        self.tickets = create_tickets(db, self.document, source_type=TicketSourceType.PDF, file_id=job.file_id)

    def extract(self, db: Session, job: IngestJob) -> None:
        f = db.get(TicketFile, job.file_id)
        duplicate = (
            db.scalar(select(TicketFile.id).where(TicketFile.sha256 == f.sha256, TicketFile.id != f.id).limit(1))
            is not None
        )
        now = self.now()
        create_work_orders(
            db, self.tickets, self.document, self.gate, actor_id=f.uploaded_by, now=now, duplicate=duplicate
        )
        # Người tải file là người khởi tạo job → gắn audit cho họ (T-053: không ghi tài khoản chung)
        record(
            db,
            f.uploaded_by,
            AuditAction.TICKET_EXTRACTED,
            {
                "job_id": job.id,
                "file_id": f.id,
                "tickets": len(self.tickets),
                "boundary_uncertain": [t.boundary_uncertain for t in self.document.tickets],
            },
            now=now,
        )
