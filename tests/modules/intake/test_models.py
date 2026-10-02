"""T-017 — schema tiếp nhận ADC-001 §Mô hình dữ liệu."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError, StatementError

from src.modules.identity import Role, User, UserStatus
from src.modules.intake import (
    ClarificationRequest,
    ClarificationStatus,
    FieldExtraction,
    FlagCode,
    IngestJob,
    IngestJobStatus,
    IngestStep,
    IntakeWarning,
    ReviewStatus,
    SourceKind,
    Ticket,
    TicketFile,
    TicketSourceType,
    WarningStatus,
    WorkOrder,
)
from src.modules.orchestration import WorkOrderState
from src.modules.types import Priority

ARRIVAL = datetime(2026, 10, 1, 9, tzinfo=UTC)
RETURN = datetime(2026, 10, 1, 16, tzinfo=UTC)


@pytest.fixture
def user(db):
    u = User(google_sub="s", email="sales@adc.test", email_domain="adc.test", role=Role.SALES, status=UserStatus.ACTIVE)
    db.add(u)
    db.commit()
    return u


def _file(db, user, sha="a" * 64) -> TicketFile:
    f = TicketFile(
        file_name="phieu.pdf", storage_path="data/files/x.pdf", sha256=sha, size_bytes=1024, uploaded_by=user.id
    )
    db.add(f)
    db.commit()
    return f


def _order(db, ticket: Ticket | None = None, **fields) -> WorkOrder:
    ticket = ticket or Ticket(source_type=TicketSourceType.TEXT, raw_text="...")
    db.add(ticket)
    db.flush()
    wo = WorkOrder(ticket_id=ticket.id, **fields)
    db.add(wo)
    db.commit()
    return wo


def test_pdf_file_with_two_tickets_and_job(db, user):
    """TC1/TC4: 1 file → nhiều ticket (mỗi ticket 1 khoảng trang) + 1 job xử lý."""
    f = _file(db, user)
    job = IngestJob(file_id=f.id)
    t1 = Ticket(file_id=f.id, source_type=TicketSourceType.PDF, page_from=1, page_to=1)
    t2 = Ticket(file_id=f.id, source_type=TicketSourceType.PDF, page_from=2, page_to=3)
    db.add_all([job, t1, t2])
    db.commit()
    assert (job.status, job.step, f.ocr_used) == (IngestJobStatus.QUEUED, IngestStep.UPLOADED, False)
    assert db.query(Ticket).filter_by(file_id=f.id).count() == 2


def test_duplicate_sha256_is_allowed(db, user):
    """File trùng chỉ cảnh báo, không chặn (BR-13)."""
    _file(db, user)
    _file(db, user)
    assert db.query(TicketFile).filter_by(sha256="a" * 64).count() == 2


def test_work_order_defaults_to_draft_and_keeps_fields(db):
    wo = _order(
        db,
        product_name="Gia vị",
        quantity=120,
        pkg_length_cm=40,
        pkg_width_cm=30,
        pkg_height_cm=25,
        pkg_weight_kg=8,
        required_dose_kgy=10,
        priority=Priority.URGENT,
        expected_arrival=ARRIVAL,
        requested_return=RETURN,
    )
    db.expire_all()
    got = db.get(WorkOrder, wo.id)
    assert got.state == WorkOrderState.DRAFT
    assert got.review_status is None and got.product_group is None
    assert (got.priority, got.expected_arrival, got.requested_return) == (Priority.URGENT, ARRIVAL, RETURN)
    assert got.created_at.tzinfo is not None


def test_missing_fields_are_stored_as_null(db):
    """TC3: nguồn thiếu liều + giờ trả → lưu NULL, không đoán."""
    wo = _order(db, product_name="Hải sản", review_status=ReviewStatus.NEEDS_CLARIFICATION)
    db.add_all(
        [
            ClarificationRequest(work_order_id=wo.id, field="required_dose_kgy", question="Liều chiếu bao nhiêu kGy?"),
            ClarificationRequest(work_order_id=wo.id, field="requested_return", question="Giờ trả mong muốn?"),
        ]
    )
    db.commit()
    db.expire_all()
    got = db.get(WorkOrder, wo.id)
    assert got.required_dose_kgy is None and got.requested_return is None
    reqs = db.query(ClarificationRequest).filter_by(work_order_id=wo.id).all()
    assert {r.field for r in reqs} == {"required_dose_kgy", "requested_return"}
    assert all(r.status == ClarificationStatus.OPEN and r.answered_at is None for r in reqs)


def test_one_ticket_creates_only_one_work_order(db):
    ticket = Ticket(source_type=TicketSourceType.MANUAL)
    _order(db, ticket=ticket)
    db.add(WorkOrder(ticket_id=ticket.id))
    with pytest.raises(IntegrityError):
        db.commit()


def test_field_extraction_keeps_source_region(db):
    """TC1/TC2: mỗi trường có nhãn nguồn, trang, vùng bbox, snippet, độ tin cậy OCR."""
    wo = _order(db)
    db.add(
        FieldExtraction(
            work_order_id=wo.id,
            field="package_dimensions_cm",
            value={"length": 40, "width": 30, "height": 25},
            source_kind=SourceKind.OCR_LOW,
            page=2,
            bbox=[72.0, 140.5, 310.2, 158.0],
            snippet="Quy cách: 40x30x25 cm",
            confidence=0.72,
        )
    )
    db.commit()
    db.expire_all()
    fe = db.query(FieldExtraction).filter_by(work_order_id=wo.id).one()
    assert fe.value == {"length": 40, "width": 30, "height": 25}
    assert (fe.source_kind, fe.page, fe.bbox, fe.confidence) == (
        SourceKind.OCR_LOW,
        2,
        [72.0, 140.5, 310.2, 158.0],
        0.72,
    )


def test_intake_warning_open_then_acknowledged(db, user):
    """TC12: cảnh báo tiếp nhận mở, người xem xác nhận đã đọc."""
    wo = _order(db, review_status=ReviewStatus.ACCEPTED_WITH_WARNINGS)
    w = IntakeWarning(work_order_id=wo.id, field="priority", code=FlagCode.INFERRED_VALUE)
    db.add(w)
    db.commit()
    assert (w.status, w.created_at.tzinfo) == (WarningStatus.OPEN, UTC)
    w.status, w.acknowledged_by, w.acknowledged_at, w.note = WarningStatus.ACKNOWLEDGED, user.id, RETURN, "đã gọi khách"
    db.commit()
    assert db.query(IntakeWarning).filter_by(status=WarningStatus.OPEN).count() == 0


def test_unknown_enum_value_is_rejected(db):
    db.add(Ticket(source_type="EMAIL"))
    with pytest.raises(StatementError):
        db.commit()


def test_indexes_from_spec(db):
    insp = inspect(db.get_bind())

    def indexed(table):
        return {tuple(ix["column_names"]) for ix in insp.get_indexes(table)}

    assert {("state",), ("requested_return",), ("review_status",)} <= indexed("work_orders")
    assert ("status",) in indexed("intake_warnings")
    assert ("status",) in indexed("ingest_jobs")
    assert ("sha256",) in indexed("ticket_files")
