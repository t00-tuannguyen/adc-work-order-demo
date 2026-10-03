"""T-020 — cổng tiếp nhận: validator (BR-01) + độ tin cậy (BR-12, BR-13), yêu cầu bổ sung, cảnh báo."""

from datetime import UTC, datetime

import pytest

from src.modules.intake import (
    ClarificationRequest,
    ClarificationStatus,
    FieldSignal,
    FlagCode,
    IntakeWarning,
    ReviewStatus,
    ReviewThresholds,
    SourceKind,
    Ticket,
    TicketSignal,
    TicketSourceType,
    WorkOrder,
    record_gate,
    run_gate,
)
from src.modules.intake.validator import ErrorCode
from tests.modules.intake.test_validator import COMPLETE

TH = ReviewThresholds()
NOW = datetime(2026, 10, 1, 8, tzinfo=UTC)
SURE = {name: FieldSignal(SourceKind.VERBATIM, 0.97) for name in COMPLETE.model_dump()}


def gate(fields=COMPLETE, signals=None, **kw):
    return run_gate(fields, SURE | (signals or {}), TH, **kw)


def test_tc11_clear_ticket_auto_accepted():
    g = gate()
    assert (g.review_status, g.proceeds, g.warnings, g.clarifications) == (ReviewStatus.AUTO_ACCEPTED, True, [], [])


def test_tc12_grey_zone_and_inferred_proceed_with_warnings():
    g = gate(
        signals={
            "pkg_length_cm": FieldSignal(SourceKind.VERBATIM, 0.85),
            "pkg_width_cm": FieldSignal(SourceKind.VERBATIM, 0.85),
            "priority": FieldSignal(SourceKind.INFERRED, 0.95),
        }
    )
    assert (g.review_status, g.proceeds) == (ReviewStatus.ACCEPTED_WITH_WARNINGS, True)
    # 3 cột kích thước dùng chung 1 nguồn → 1 cảnh báo cho package_dimensions_cm
    assert {(w.field, w.code) for w in g.warnings} == {
        ("package_dimensions_cm", FlagCode.AMBIGUOUS_OCR),
        ("priority", FlagCode.INFERRED_VALUE),
    }


def test_duplicate_file_is_ticket_level_warning():
    g = gate(ticket=TicketSignal(possible_duplicate=True))
    assert [(w.field, w.code) for w in g.warnings] == [(None, FlagCode.POSSIBLE_DUPLICATE)]


def test_tc2_low_confidence_needs_review_and_lists_field():
    g = gate(signals={"quantity": FieldSignal(SourceKind.OCR_LOW, 0.6)})
    assert (g.review_status, g.proceeds, g.unconfirmed_fields) == (ReviewStatus.NEEDS_REVIEW, False, ["quantity"])


def test_tc14_uncertain_boundary_needs_review_but_no_field_to_confirm():
    g = gate(ticket=TicketSignal(boundary_uncertain=True))
    assert (g.review_status, g.unconfirmed_fields) == (ReviewStatus.NEEDS_REVIEW, [])


def test_tc3_missing_dose_and_return_ask_exactly_two_questions():
    g = gate(COMPLETE.model_copy(update={"required_dose_kgy": None, "requested_return": None}))
    assert g.review_status == ReviewStatus.NEEDS_CLARIFICATION and not g.proceeds
    assert [(c.field, c.code) for c in g.clarifications] == [
        ("required_dose_kgy", ErrorCode.MISSING),
        ("requested_return", ErrorCode.MISSING),
    ]
    assert "liều chiếu" in g.clarifications[0].question


def test_missing_dimensions_is_one_question():
    g = gate(COMPLETE.model_copy(update={"pkg_length_cm": None, "pkg_height_cm": None}))
    assert [c.field for c in g.clarifications] == ["package_dimensions_cm"]


def test_tc8_return_before_arrival_is_error():
    fields = COMPLETE.model_copy(update={"requested_return": COMPLETE.expected_arrival})
    assert [(c.field, c.code) for c in gate(fields).clarifications] == [
        ("requested_return", ErrorCode.RETURN_NOT_AFTER_ARRIVAL)
    ]


def test_dose_outside_catalog_needs_no_clarification():
    assert gate(COMPLETE.model_copy(update={"required_dose_kgy": 7})).clarifications == []


def test_dose_above_25_needs_clarification():
    g = gate(COMPLETE.model_copy(update={"required_dose_kgy": 30}))
    assert [(c.field, c.code) for c in g.clarifications] == [("required_dose_kgy", ErrorCode.DOSE_OUT_OF_RANGE)]


def test_missing_fields_dominate_low_confidence():
    g = gate(
        COMPLETE.model_copy(update={"required_dose_kgy": None}),
        signals={"quantity": FieldSignal(SourceKind.OCR_LOW, 0.5)},
    )
    assert g.review_status == ReviewStatus.NEEDS_CLARIFICATION and g.unconfirmed_fields == ["quantity"]


@pytest.fixture
def wo(db):
    t = Ticket(source_type=TicketSourceType.MANUAL)
    db.add(t)
    db.flush()
    w = WorkOrder(ticket_id=t.id)
    db.add(w)
    db.flush()
    return w


def _open(db, wo):
    return {r.field for r in db.query(ClarificationRequest).filter_by(work_order_id=wo.id, status="OPEN")}


def test_record_gate_opens_and_closes_clarifications(db, wo):
    missing = gate(COMPLETE.model_copy(update={"required_dose_kgy": None, "requested_return": None}))
    record_gate(db, wo, missing, now=NOW)
    record_gate(db, wo, missing, now=NOW)  # chạy lại không nhân đôi câu hỏi
    db.commit()
    assert _open(db, wo) == {"required_dose_kgy", "requested_return"}

    one_left = gate(COMPLETE.model_copy(update={"requested_return": None}))
    record_gate(db, wo, one_left, now=NOW, auto=False)
    db.commit()
    assert _open(db, wo) == {"requested_return"}
    answered = db.query(ClarificationRequest).filter_by(field="required_dose_kgy").one()
    assert (answered.status, answered.answered_at) == (ClarificationStatus.ANSWERED, NOW)


def test_record_gate_creates_warnings_only_when_proceeding(db, wo):
    warn = gate(signals={"priority": FieldSignal(SourceKind.INFERRED, 0.95)})
    record_gate(db, wo, warn, now=NOW, auto=False)
    db.commit()
    assert (wo.review_status, db.query(IntakeWarning).count()) == (ReviewStatus.NEEDS_REVIEW, 0)
    record_gate(db, wo, warn, now=NOW)
    db.commit()
    assert wo.review_status == ReviewStatus.ACCEPTED_WITH_WARNINGS
    assert [(w.field, w.code, w.status) for w in db.query(IntakeWarning)] == [("priority", "INFERRED_VALUE", "OPEN")]
