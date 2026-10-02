"""ADC-001 T-018 — POST /api/tickets/upload, GET /api/ingest-jobs/{job_id}."""

import hashlib
from pathlib import Path

import pytest
from sqlalchemy import select

from src.api.intake import get_ingest_stages
from src.main import app
from src.modules.identity import Role
from src.modules.intake import IngestError, IngestStage, IngestStep, Ticket, TicketFile, TicketSourceType, WorkOrder
from src.modules.intake.models import IngestJob
from src.modules.orchestration import AuditLog
from tests.pdf_samples import SCAN_PDF, TEXT_PDF, TICKET_TEXT, make_pdf

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("no_auto_schedule")]

PDF = TEXT_PDF


def upload(client, content=PDF, name="phieu.pdf", ctype="application/pdf", **form):
    return client.post("/api/tickets/upload", files={"file": (name, content, ctype)}, data=form)


@pytest.fixture
def stages():
    """Cắm pipeline giả vào job (pipeline thật là T-048 / T-019)."""

    def _set(value):
        app.dependency_overrides[get_ingest_stages] = lambda: value

    yield _set
    app.dependency_overrides.pop(get_ingest_stages, None)


async def test_upload_requires_sales(client, sign_in):
    assert (await upload(client)).status_code == 401
    assert (await client.get("/api/ingest-jobs/x")).status_code == 401
    for role in (Role.PLANNER, Role.OPS_MANAGER, Role.ADMIN):  # chỉ Kinh doanh tiếp nhận ticket
        sign_in(role)
        assert (await upload(client)).status_code == 403
        assert (await client.get("/api/ingest-jobs/x")).status_code == 403


async def test_upload_stores_file_and_creates_job(client, sign_in, db):
    user = sign_in(Role.SALES)
    res = await upload(client, channel="EMAIL", received_at="2026-10-01T08:30:00+07:00")
    assert res.status_code == 202
    body = res.json()

    f = db.get(TicketFile, body["file_id"])
    assert Path(f.storage_path).read_bytes() == PDF
    assert (f.sha256, f.size_bytes, f.file_name, f.channel) == (
        hashlib.sha256(PDF).hexdigest(),
        len(PDF),
        "phieu.pdf",
        "EMAIL",
    )
    assert f.uploaded_by == user.id and f.received_at.isoformat() == "2026-10-01T01:30:00+00:00"

    audit = db.scalars(select(AuditLog).where(AuditLog.action == "TICKET_UPLOADED")).one()
    assert (audit.actor_id, audit.payload["file_id"], audit.payload["job_id"]) == (user.id, f.id, body["job_id"])

    job = (await client.get(f"/api/ingest-jobs/{body['job_id']}")).json()
    assert job == {"status": "QUEUED", "step": "UPLOADED", "progress": 25, "work_orders": [], "error_code": None}


async def test_upload_keeps_only_basename_of_file_name(client, sign_in, db):
    sign_in(Role.SALES)
    body = (await upload(client, name="../../etc/phieu.pdf")).json()
    f = db.get(TicketFile, body["file_id"])
    assert f.file_name == "phieu.pdf"
    assert Path(f.storage_path).name == f"{f.id}.pdf"


async def test_tc5_file_over_limit_is_413_and_nothing_kept(client, sign_in, db, test_settings):
    sign_in(Role.SALES)
    test_settings.max_upload_mb = 1
    res = await upload(client, content=PDF + b"0" * (1024 * 1024))
    assert res.status_code == 413
    assert db.query(TicketFile).count() == 0 and db.query(IngestJob).count() == 0
    assert list(Path(test_settings.upload_dir).iterdir()) == []


@pytest.mark.parametrize(
    ("content", "ctype"),
    [
        (b"\x89PNG\r\n\x1a\n" + b"0" * 100, "application/pdf"),  # đuôi/khai báo PDF nhưng nội dung PNG
        (b"hello", "text/plain"),
    ],
)
async def test_tc5_not_pdf_is_415(client, sign_in, db, test_settings, content, ctype):
    sign_in(Role.SALES)
    assert (await upload(client, content=content, ctype=ctype)).status_code == 415
    assert db.query(TicketFile).count() == 0
    assert list(Path(test_settings.upload_dir).iterdir()) == []


async def test_received_at_without_timezone_is_422(client, sign_in):
    sign_in(Role.SALES)
    assert (await upload(client, received_at="2026-10-01T08:30:00")).status_code == 422


async def test_unknown_job_is_404(client, sign_in):
    sign_in(Role.SALES)
    assert (await client.get("/api/ingest-jobs/khong-co")).status_code == 404


async def test_job_runs_stages_in_background_and_lists_work_orders(client, sign_in, stages):
    """TC4: file 2 ticket → job DONE, trả 2 work order DRAFT."""
    seen = []

    def detect(db, job):
        for page in (1, 2):
            t = Ticket(file_id=job.file_id, source_type=TicketSourceType.PDF, page_from=page, page_to=page)
            db.add(t)
            db.flush()
            db.add(WorkOrder(ticket_id=t.id))
        db.commit()

    stages(
        [
            IngestStage(IngestStep.READING, lambda db, job: seen.append(job.step)),
            IngestStage(IngestStep.DETECTING, detect),
            IngestStage(IngestStep.EXTRACTING, lambda db, job: seen.append(job.step)),
        ]
    )
    sign_in(Role.SALES)
    job_id = (await upload(client)).json()["job_id"]
    job = (await client.get(f"/api/ingest-jobs/{job_id}")).json()
    assert seen == [IngestStep.READING, IngestStep.EXTRACTING]
    assert (job["status"], job["step"], job["progress"], job["error_code"]) == ("SUCCEEDED", "DONE", 100, None)
    assert [(w["state"], w["review_status"]) for w in job["work_orders"]] == [("DRAFT", None), ("DRAFT", None)]


async def test_tc6_stage_error_marks_job_failed_with_code(client, sign_in, stages):
    def ocr(db, job):
        raise IngestError("OCR_FAILED")

    stages([IngestStage(IngestStep.READING, ocr)])
    sign_in(Role.SALES)
    body = (await upload(client)).json()
    job = (await client.get(f"/api/ingest-jobs/{body['job_id']}")).json()
    assert (job["status"], job["step"], job["error_code"]) == ("FAILED", "FAILED", "OCR_FAILED")


async def test_unexpected_stage_error_fails_job_without_code(client, sign_in, stages):
    stages([IngestStage(IngestStep.READING, lambda db, job: 1 / 0)])
    sign_in(Role.SALES)
    body = (await upload(client)).json()
    job = (await client.get(f"/api/ingest-jobs/{body['job_id']}")).json()
    assert (job["status"], job["error_code"]) == ("FAILED", None)


async def test_upload_records_text_layer_and_ocr_need(client, sign_in, db):
    sign_in(Role.SALES)
    text = db.get(TicketFile, (await upload(client)).json()["file_id"])
    scan = db.get(TicketFile, (await upload(client, content=SCAN_PDF)).json()["file_id"])
    mixed = db.get(TicketFile, (await upload(client, content=make_pdf([TICKET_TEXT, None]))).json()["file_id"])
    assert (text.page_count, text.has_text_layer, text.ocr_used) == (1, True, False)
    assert (scan.page_count, scan.has_text_layer, scan.ocr_used) == (1, False, True)
    assert (mixed.page_count, mixed.has_text_layer, mixed.ocr_used) == (2, False, True)


@pytest.mark.parametrize(
    "content",
    [
        make_pdf([TICKET_TEXT], password="bi-mat"),  # có mật khẩu
        TEXT_PDF[: len(TEXT_PDF) // 3],  # hỏng (bị cắt)
        b"%PDF-1.7\nkhong phai pdf that\n",  # chữ ký đúng nhưng cấu trúc hỏng
        make_pdf([TICKET_TEXT] * 21),  # > 20 trang
    ],
    ids=["encrypted", "truncated", "garbage", "too-many-pages"],
)
async def test_tc5_unreadable_pdf_is_422_and_nothing_kept(client, sign_in, db, test_settings, content):
    sign_in(Role.SALES)
    res = await upload(client, content=content)
    assert res.status_code == 422
    assert db.query(TicketFile).count() == 0 and db.query(IngestJob).count() == 0
    assert list(Path(test_settings.upload_dir).iterdir()) == []
