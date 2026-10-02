"""Tiếp nhận file PDF + job xử lý bất đồng bộ — ADC-001 §Kiến trúc, T-018.

Upload kiểm tra dung lượng, chữ ký PDF và cấu trúc file (pypdf, ADR-0010) rồi lưu file, tạo `ticket_files` + `ingest_jobs`.
Các bước đọc/OCR và trích xuất (T-019, Gemini) cắm vào `run_ingest_job` dưới dạng `IngestStage`.
"""

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import BinaryIO

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from src.modules.intake.models import IngestJob, IngestJobStatus, IngestStep, Ticket, TicketFile, WorkOrder, _new_id
from src.modules.intake.pdf import InvalidPdfError, inspect_pdf
from src.services.storage import store_stream

logger = logging.getLogger(__name__)

# PDF 1.x/2.0 bắt đầu bằng "%PDF-"; chuẩn cho phép có rác phía trước trong 1024 byte đầu
PDF_MAGIC = b"%PDF-"
PDF_MAGIC_WINDOW = 1024

# Tiến độ (%) theo bước đã tới — 4 bước UI: Tải lên → Đọc PDF/OCR → Nhận diện ticket → Trích xuất
PROGRESS: dict[IngestStep, int] = {
    IngestStep.UPLOADED: 25,
    IngestStep.READING: 50,
    IngestStep.DETECTING: 75,
    IngestStep.EXTRACTING: 90,
    IngestStep.DONE: 100,
    IngestStep.FAILED: 100,
}


class NotPdfError(Exception):
    pass


class IngestError(Exception):
    """Lỗi nghiệp vụ trong 1 bước job → job FAILED kèm `error_code` cho UI (vd OCR_FAILED)."""

    def __init__(self, error_code: str, message: str = ""):
        super().__init__(message or error_code)
        self.error_code = error_code


@dataclass(frozen=True)
class IngestStage:
    step: IngestStep
    run: Callable[[Session, IngestJob], None]


def is_pdf(head: bytes) -> bool:
    return PDF_MAGIC in head[:PDF_MAGIC_WINDOW]


def create_ingest(
    db: Session,
    src: BinaryIO,
    *,
    file_name: str,
    upload_dir: Path,
    max_bytes: int,
    max_pages: int,
    uploaded_by: str,
    channel: str | None,
    received_at: datetime,
) -> tuple[TicketFile, IngestJob]:
    """Lưu file + tạo job ở bước UPLOADED.

    Lỗi (FileTooLargeError / NotPdfError / InvalidPdfError) → không tạo gì, không để lại file.
    """
    file_id = _new_id()
    stored = store_stream(src, upload_dir / f"{file_id}.pdf", max_bytes=max_bytes, head_bytes=PDF_MAGIC_WINDOW)
    if not is_pdf(stored.head):
        stored.path.unlink(missing_ok=True)
        raise NotPdfError("nội dung file không phải PDF")
    try:
        info = inspect_pdf(stored.path, max_pages=max_pages)
    except InvalidPdfError:
        stored.path.unlink(missing_ok=True)
        raise
    ticket_file = TicketFile(
        id=file_id,
        file_name=Path(file_name).name[:255] or "upload.pdf",
        storage_path=str(stored.path),
        sha256=stored.sha256,
        size_bytes=stored.size_bytes,
        page_count=info.page_count,
        has_text_layer=info.has_text_layer,
        ocr_used=info.needs_ocr,
        channel=channel,
        received_at=received_at,
        uploaded_by=uploaded_by,
    )
    job = IngestJob(file_id=file_id, status=IngestJobStatus.QUEUED, step=IngestStep.UPLOADED)
    db.add_all([ticket_file, job])
    db.commit()
    return ticket_file, job


def run_ingest_job(
    session_factory: sessionmaker[Session], job_id: str, stages: Sequence[IngestStage], *, now: Callable[[], datetime]
) -> None:
    """Chạy lần lượt các bước; mỗi bước commit `step` trước khi chạy để UI thấy tiến độ.

    Chạy trong BackgroundTasks → mở session riêng, không dùng session của request.
    """
    with session_factory() as db:
        job = db.get(IngestJob, job_id)
        if job is None:
            logger.warning("ingest job %s không tồn tại", job_id)
            return
        job.status, job.started_at = IngestJobStatus.RUNNING, now()
        db.commit()
        try:
            for stage in stages:
                job.step = stage.step
                db.commit()
                stage.run(db, job)
        except IngestError as e:
            db.rollback()
            _finish(db, job, IngestJobStatus.FAILED, now(), e.error_code)
            return
        except Exception:
            logger.exception("ingest job %s lỗi không mong đợi", job_id)
            db.rollback()
            _finish(db, job, IngestJobStatus.FAILED, now(), None)
            return
        _finish(db, job, IngestJobStatus.SUCCEEDED, now(), None)


def _finish(db: Session, job: IngestJob, status: IngestJobStatus, at: datetime, error_code: str | None) -> None:
    job.status, job.finished_at, job.error_code = status, at, error_code
    job.step = IngestStep.DONE if status == IngestJobStatus.SUCCEEDED else IngestStep.FAILED
    db.commit()


def job_work_orders(db: Session, job: IngestJob) -> list[WorkOrder]:
    """Work order tạo từ file của job (mỗi ticket trong file → 1 lệnh)."""
    stmt = select(WorkOrder).join(Ticket).where(Ticket.file_id == job.file_id).order_by(Ticket.page_from, WorkOrder.id)
    return list(db.scalars(stmt))


def check_ocr_allowed(ticket_file: TicketFile, *, enabled: bool) -> None:
    """FEATURE_OCR tắt (ADC-001 §Kế hoạch triển khai) → file có trang scan chuyển nhập tay, PDF văn bản số vẫn đọc."""
    if ticket_file.ocr_used and not enabled:
        raise IngestError("OCR_FAILED", "OCR đang tắt (FEATURE_OCR=false), file có trang scan")
