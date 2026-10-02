"""ADC-001 — validator (TC3, TC8) và BR-01."""

from src.modules.intake import ErrorCode, WorkOrderFields, is_complete, validate
from src.modules.types import Priority
from tests.conftest import at

COMPLETE = WorkOrderFields(
    product_name="Gia vị",
    quantity=120,
    pkg_length_cm=40,
    pkg_width_cm=30,
    pkg_height_cm=25,
    pkg_weight_kg=8,
    required_dose_kgy=10,
    priority=Priority.NORMAL,
    expected_arrival=at(9),
    requested_return=at(16),
)


def test_complete_ticket_has_no_errors():
    assert validate(COMPLETE, allowed_doses=["10"]) == []
    assert is_complete(COMPLETE)


def test_missing_dose_and_return_time_yields_exactly_two_requests():
    fields = COMPLETE.model_copy(update={"required_dose_kgy": None, "requested_return": None})
    errors = validate(fields)
    assert {(e.field, e.code) for e in errors} == {
        ("required_dose_kgy", ErrorCode.MISSING),
        ("requested_return", ErrorCode.MISSING),
    }
    assert not is_complete(fields)


def test_return_not_after_arrival_is_error():
    fields = COMPLETE.model_copy(update={"requested_return": at(9)})
    assert [e.code for e in validate(fields)] == [ErrorCode.RETURN_NOT_AFTER_ARRIVAL]


def test_dose_outside_catalog_needs_confirmation():
    fields = COMPLETE.model_copy(update={"required_dose_kgy": 7})
    assert [e.code for e in validate(fields, allowed_doses=["10"])] == [ErrorCode.DOSE_NEEDS_CONFIRMATION]


def test_optional_fields_may_be_missing():
    fields = COMPLETE.model_copy(update={"priority": None, "expected_arrival": None})
    assert validate(fields) == []
