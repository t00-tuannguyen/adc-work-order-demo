"""Luồng tiếp nhận end-to-end (deterministic): ticket đủ trường → lịch; thiếu trường / tin cậy thấp → dừng ở DRAFT."""

import time

from src.agents.graph import intake_graph
from src.modules.intake import FieldSignal, FlagCode, ReviewDecision, SourceKind
from src.modules.types import Line
from tests.conftest import at
from tests.modules.intake.test_validator import COMPLETE


def test_normal_order_is_estimated_and_scheduled_under_5s():
    t0 = time.perf_counter()
    result = intake_graph.invoke({"fields": COMPLETE, "product_group": "spice", "now": at(8), "slots": []})
    assert time.perf_counter() - t0 < 5
    assert result["errors"] == []
    assert result["estimate"].duration_min == 180
    p = result["placement"]
    assert (p.line, p.start, p.end, p.sla_ok) == (Line.A, at(9), at(12), True)


def test_missing_fields_stop_before_estimation():
    fields = COMPLETE.model_copy(update={"required_dose_kgy": None})
    result = intake_graph.invoke({"fields": fields, "product_group": "spice", "now": at(8)})
    assert result["errors"]
    assert "estimate" not in result and "placement" not in result


def test_low_ocr_confidence_holds_for_human_review():
    signals = {"quantity": FieldSignal(SourceKind.VERBATIM, 0.6)}
    result = intake_graph.invoke({"fields": COMPLETE, "signals": signals, "product_group": "spice", "now": at(8)})
    assert result["errors"] == []
    assert result["assessment"].decision == ReviewDecision.REVIEW
    assert "estimate" not in result and "placement" not in result


def test_ambiguous_result_is_scheduled_with_warning():
    signals = {"quantity": FieldSignal(SourceKind.VERBATIM, 0.85), "priority": FieldSignal(SourceKind.INFERRED)}
    result = intake_graph.invoke(
        {"fields": COMPLETE, "signals": signals, "product_group": "spice", "now": at(8), "slots": []}
    )
    assert result["assessment"].decision == ReviewDecision.WARN
    assert {f.code for f in result["assessment"].warnings} == {FlagCode.AMBIGUOUS_OCR, FlagCode.INFERRED_VALUE}
    assert result["placement"].sla_ok
