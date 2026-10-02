"""T-019 — Order Agent (Gemini, ADR-0010): gọi có schema, thử lại 1 lần, chuẩn hóa deterministic."""

import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from google.genai import errors

from src.agents.order_agent import LOCAL_TZ, ExtractionFailedError, GeminiOrderAgent, normalize
from src.agents.schemas import DocumentExtraction, TicketExtraction
from src.modules.intake import FlagCode, ReviewDecision, ReviewThresholds, SourceKind, assess
from src.modules.types import Priority

RECEIVED = datetime(2026, 10, 1, 1, tzinfo=UTC)
TH = ReviewThresholds()


def field(value, kind="VERBATIM", page=1, conf=0.97, box=(100, 50, 120, 400), snippet="..."):
    return {
        "value": value,
        "source_kind": kind,
        "page": page,
        "snippet": snippet,
        "box_2d": list(box),
        "confidence": conf,
    }


def full_ticket(**overrides) -> dict:
    fields = {
        "product_name": field("Bột ớt xay"),
        "quantity": field(120, snippet="Số lượng: 120 thùng"),
        "package_dimensions_cm": field({"length": 40, "width": 30, "height": 25}),
        "pkg_weight_kg": field(8),
        "required_dose_kgy": field(10),
        "priority": field("URGENT"),
        "expected_arrival": field("2026-10-02T09:00"),
        "requested_return": field("2026-10-02T16:00"),
    }
    fields.update(overrides)
    return {"page_from": 1, "page_to": 1, "boundary_uncertain": False, "fields": fields}


def doc_json(*tickets) -> str:
    return json.dumps({"tickets": list(tickets)})


class FakeModels:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    def generate_content(self, *, model, contents, config):
        self.calls.append(SimpleNamespace(model=model, contents=contents, config=config))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return SimpleNamespace(text=reply)


def agent(*replies, sleeps=None):
    models = FakeModels(replies)
    sleep = sleeps.append if sleeps is not None else lambda s: None
    return GeminiOrderAgent(SimpleNamespace(models=models), "gemini-test", sleep=sleep), models


def overloaded(code=503):
    return errors.APIError(code, {"error": {"code": code, "message": "high demand", "status": "UNAVAILABLE"}})


def test_calls_gemini_with_pdf_schema_and_temperature_0():
    a, models = agent(doc_json(full_ticket()))
    doc = a.extract_pdf(b"%PDF-", page_count=1, received_at=RECEIVED)
    assert len(doc.tickets) == 1
    call = models.calls[0]
    assert call.model == "gemini-test"
    assert call.config.temperature == 0 and call.config.response_schema is DocumentExtraction
    assert call.config.automatic_function_calling.disable is True
    assert call.contents[0].inline_data.mime_type == "application/pdf"
    assert "2026-10-01 08:00" in call.contents[1]  # ngày nhận theo giờ Việt Nam cho ngày tương đối


@pytest.mark.parametrize(
    "bad",
    [
        "không phải json",
        doc_json({"page_from": 1, "page_to": 3, "fields": {}}),  # trang ngoài file
        doc_json(full_ticket(quantity=field(120, page=5))),  # trang nguồn ngoài file
        ValueError("timeout"),
    ],
)
def test_retries_once_then_succeeds(bad):
    a, models = agent(bad, doc_json(full_ticket()))
    assert len(a.extract_pdf(b"", page_count=1, received_at=RECEIVED).tickets) == 1
    assert len(models.calls) == 2


def test_tc9_fails_after_3_retries_without_waiting_on_schema_errors():
    sleeps = []
    a, models = agent("{", "{", "{", "{", sleeps=sleeps)
    with pytest.raises(ExtractionFailedError):
        a.extract_pdf(b"", page_count=1, received_at=RECEIVED)
    assert len(models.calls) == 4 and sleeps == []


def test_overloaded_waits_with_backoff_then_succeeds():
    sleeps = []
    a, models = agent(overloaded(503), overloaded(429), overloaded(500), doc_json(full_ticket()), sleeps=sleeps)
    assert len(a.extract_pdf(b"", page_count=1, received_at=RECEIVED).tickets) == 1
    assert len(models.calls) == 4 and sleeps == [1.0, 2.0, 4.0]


def test_overloaded_every_time_fails_without_waiting_after_last_attempt():
    sleeps = []
    a, models = agent(*(overloaded() for _ in range(4)), sleeps=sleeps)
    with pytest.raises(ExtractionFailedError) as e:
        a.extract_pdf(b"", page_count=1, received_at=RECEIVED)
    assert isinstance(e.value.__cause__, errors.APIError)
    assert len(models.calls) == 4 and sleeps == [1.0, 2.0, 4.0]


def test_client_error_is_retried_without_waiting():
    sleeps = []
    a, models = agent(overloaded(400), doc_json(full_ticket()), sleeps=sleeps)
    a.extract_pdf(b"", page_count=1, received_at=RECEIVED)
    assert sleeps == []


def test_prompt_defines_source_kind_rules():
    from src.agents.order_agent import SYSTEM_PROMPT

    assert "CHỈ khi đổi đơn vị đo" in SYSTEM_PROMPT and '"Thường" → NORMAL' in SYSTEM_PROMPT


def test_tc1_normalizes_all_fields_with_source():
    n = normalize(TicketExtraction.model_validate(full_ticket()), TH)
    f = n.fields
    assert (f.product_name, f.quantity, f.pkg_weight_kg, f.required_dose_kgy, f.priority) == (
        "Bột ớt xay",
        120,
        8,
        10,
        Priority.URGENT,
    )
    assert (f.pkg_length_cm, f.pkg_width_cm, f.pkg_height_cm) == (40, 30, 25)
    assert f.expected_arrival == datetime(2026, 10, 2, 9, tzinfo=LOCAL_TZ)
    assert f.requested_return.astimezone(UTC) == datetime(2026, 10, 2, 9, tzinfo=UTC)
    assert len(n.sources) == 8 and all(s.page == 1 and s.bbox == [0.05, 0.1, 0.4, 0.12] for s in n.sources)
    dims = next(s for s in n.sources if s.field == "package_dimensions_cm")
    assert dims.value == {"length": 40, "width": 30, "height": 25}
    assert next(s for s in n.sources if s.field == "priority").value == "URGENT"
    assert set(n.signals) == set(f.model_dump())


def test_tc3_missing_fields_are_not_guessed():
    t = full_ticket(required_dose_kgy=field(None), requested_return={"value": None})
    n = normalize(TicketExtraction.model_validate(t), TH)
    assert n.fields.required_dose_kgy is None and n.fields.requested_return is None
    assert "required_dose_kgy" not in n.signals and len(n.sources) == 6


def test_invalid_datetime_is_treated_as_missing():
    n = normalize(TicketExtraction.model_validate(full_ticket(requested_return=field("chiều mai"))), TH)
    assert n.fields.requested_return is None


def test_tc7_converted_units_keep_label():
    t = full_ticket(pkg_weight_kg=field(3.63, kind="CONVERTED", snippet="8 lb"))
    n = normalize(TicketExtraction.model_validate(t), TH)
    assert n.signals["pkg_weight_kg"].source_kind == SourceKind.CONVERTED


def test_tc2_low_confidence_becomes_ocr_low_and_review():
    t = full_ticket(quantity=field(120, conf=0.6))
    n = normalize(TicketExtraction.model_validate(t), TH)
    assert next(s for s in n.sources if s.field == "quantity").source_kind == SourceKind.OCR_LOW
    result = assess(n.signals, TH)
    assert result.decision == ReviewDecision.REVIEW
    assert [(x.code, x.field) for x in result.review_flags] == [(FlagCode.LOW_CONFIDENCE, "quantity")]


def test_tc11_clear_ticket_is_auto():
    assert assess(normalize(TicketExtraction.model_validate(full_ticket()), TH).signals, TH).decision == "AUTO"


def test_tc12_grey_zone_or_inferred_is_warn():
    for override in ({"pkg_weight_kg": field(8, conf=0.85)}, {"priority": field("URGENT", kind="INFERRED")}):
        n = normalize(TicketExtraction.model_validate(full_ticket(**override)), TH)
        assert assess(n.signals, TH).decision == ReviewDecision.WARN


@pytest.mark.parametrize("box", [None, [1, 2, 3], [500, 100, 400, 300]])
def test_bad_box_is_dropped(box):
    t = full_ticket(quantity={**field(120), "box_2d": box})
    n = normalize(TicketExtraction.model_validate(t), TH)
    assert next(s for s in n.sources if s.field == "quantity").bbox is None


def test_extract_text_sends_text_as_one_page():
    a, models = agent(doc_json(full_ticket()))
    doc = a.extract_text("Gửi 120 thùng bột ớt", received_at=RECEIVED)
    assert len(doc.tickets) == 1
    prompt, text = models.calls[0].contents
    assert "1 trang" in prompt and text == "Gửi 120 thùng bột ớt"
