"""T-022 — chấm điểm trích xuất (thuần) + bộ mẫu nhất quán với đáp án."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from eval.intake.samples import SCAN_SAMPLES, TEXT_SAMPLES, answer_key
from eval.intake.scoring import FIELDS, SampleScore, comparable, field_ok, local_minute, score_ticket, summarize
from src.modules.intake import WorkOrderFields, inspect_pdf
from src.modules.types import Priority

EXP = {
    "page_from": 1,
    "page_to": 1,
    "fields": {
        "product_name": "Bột ớt xay khô",
        "quantity": 120,
        "package_dimensions_cm": [40, 30, 25],
        "pkg_weight_kg": 8,
        "required_dose_kgy": None,
        "priority": "NORMAL",
        "expected_arrival": "2026-10-02T09:00",
        "requested_return": None,
    },
}


@pytest.mark.parametrize(
    ("name", "expected", "got", "ok"),
    [
        ("product_name", "Bột ớt  xay khô", "bột ớt xay khô", True),
        ("product_name", "Bột ớt", "Bột ớt xay", False),
        ("pkg_weight_kg", 9.98, 9.9790, True),  # 22 lb, sai số làm tròn
        ("pkg_weight_kg", 9.98, 9.5, False),
        ("package_dimensions_cm", [50.8, 40.64, 30.48], [50.8, 40.6, 30.5], True),
        ("package_dimensions_cm", [40, 30, 25], [30, 40, 25], False),  # đảo thứ tự D × R
        ("expected_arrival", "2026-10-02T09:00", "2026-10-02T02:00:00+00:00", True),
        ("requested_return", None, None, True),  # thiếu đúng
        ("requested_return", None, "2026-10-02T16:00", False),  # tự đoán
        ("required_dose_kgy", 10, None, False),  # bỏ sót
    ],
)
def test_field_ok(name, expected, got, ok):
    assert field_ok(name, expected, got) is ok


def test_local_minute_converts_to_vietnam_time():
    assert local_minute(datetime(2026, 10, 2, 2, tzinfo=UTC)) == "2026-10-02T09:00"
    assert local_minute("2026-10-02T09:00") == "2026-10-02T09:00"


def test_comparable_merges_dimensions():
    f = WorkOrderFields(pkg_length_cm=40, pkg_width_cm=30, pkg_height_cm=25, priority=Priority.VIP)
    c = comparable(f)
    assert c["package_dimensions_cm"] == [40, 30, 25] and c["priority"] == "VIP" and c["quantity"] is None
    assert comparable(WorkOrderFields())["package_dimensions_cm"] is None


def test_score_ticket_counts_missing_and_pages():
    got = {**EXP["fields"], "expected_arrival": "2026-10-02T09:00"}
    ts = score_ticket(EXP, got, {"quantity": 1, "product_name": 2}, (1, 1))
    assert ts.all_ok and ts.pages_range_ok
    assert (ts.missing_expected, ts.missing_detected) == (2, 2)
    assert (ts.pages_checked, ts.pages_ok) == (2, 1)


def test_missed_ticket_is_all_wrong():
    ts = score_ticket(EXP, None, {}, None)
    assert not any(ts.fields_ok.values()) and ts.missing_detected == 0


def test_summarize_auto_wrong_rate():
    ok = score_ticket(EXP, dict(EXP["fields"]), {}, (1, 1))
    ok.decision = "AUTO"
    bad = score_ticket(EXP, {**EXP["fields"], "quantity": 12}, {}, (1, 1))
    bad.decision = "AUTO"
    review = score_ticket(EXP, {**EXP["fields"], "quantity": 12}, {}, (1, 1))
    review.decision = "REVIEW"
    s = summarize([SampleScore("a", "text", 3, 3, [ok, bad, review]), SampleScore("b", "scan", 1, 0, [])])
    assert s["text"]["auto_tickets"] == 2 and s["text"]["auto_wrong"] == 1 and s["text"]["auto_wrong_rate"] == 0.5
    assert s["text"]["field_accuracy"] == round(22 / 24, 3)
    assert s["scan"]["field_accuracy"] is None and s["all"]["samples"] == 2


def test_dataset_matches_answers_and_files():
    """≥ 15 PDF, ≥ 5 scan; answers.json khớp định nghĩa; file scan không có text layer, trang khớp đáp án."""
    pdfs = Path("src/seed/pdfs")
    committed = json.loads((pdfs / "answers.json").read_text())["samples"]
    assert committed == json.loads(json.dumps(answer_key(), ensure_ascii=False))
    assert len(committed) >= 15 and sum(v["kind"] == "scan" for v in committed.values()) >= 5
    for sid, ans in committed.items():
        info = inspect_pdf(pdfs / f"{sid}.pdf", max_pages=20)
        assert info.page_count == max(t["page_to"] for t in ans["tickets"]), sid
        assert info.needs_ocr is (ans["kind"] == "scan"), sid
        for t in ans["tickets"]:
            assert set(t["fields"]) == set(FIELDS)
    assert {s["source"] for s in SCAN_SAMPLES} <= {s["id"] for s in TEXT_SAMPLES}
