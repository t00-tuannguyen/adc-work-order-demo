"""ADC-004 T-034 — Scheduler Agent giải thích phương án sự cố: validator giờ/line, bản deterministic khi LLM lỗi/tắt."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from src.agents.scheduler_agent import (
    ExplanationSource,
    PlanFacts,
    SchedulerAgent,
    check_explanation,
    explain_plan,
    payload,
    template,
)
from src.agents.schemas import ScheduleExplanation
from src.modules.scheduling import MoveSummary, Slot
from src.modules.types import Line, Priority

TZ = timezone(timedelta(hours=7))


def at(hour: int, minute: int = 0) -> datetime:
    """Giờ +07 ngày 03/10/2026 → UTC."""
    return datetime(2026, 10, 3, hour, minute, tzinfo=TZ).astimezone(UTC)


# Line A dừng 09:00–12:00: VIP sang B kịp giờ; đơn Thường trên B bị đẩy lùi, trễ 30 phút
FACTS = PlanFacts(
    line=Line.A,
    start=at(9),
    end=at(12),
    moves=[
        MoveSummary(
            "Hạt tiêu", Priority.VIP, Slot("V", Line.A, at(8), at(11)), Slot("V", Line.B, at(8), at(11)), at(13), False
        ),
        MoveSummary(
            "Quế",
            Priority.NORMAL,
            Slot("N", Line.B, at(8), at(10)),
            Slot("N", Line.B, at(11), at(13)),
            at(12, 30),
            True,
        ),
    ],
)
GOOD = (
    "Line A dừng 09:00–12:00 nên 2 đơn phải xếp lại. Hạt tiêu (VIP) chuyển từ Line A 08:00 sang Line B 08:00–11:00, "
    "kịp giờ trả 13:00. Quế (Thường) bị đẩy lùi để nhường đơn VIP: Line B 08:00 → Line B 11:00–13:00, trễ giờ trả "
    "12:30 30 phút. Phương án đang chờ duyệt, lịch đang chạy chưa đổi; kinh doanh cần báo khách đơn trễ."
)


class FakeLLM:
    def __init__(self, reply):
        self.reply, self.calls, self.schema = reply, [], None

    def with_structured_output(self, schema):
        self.schema = schema
        return self

    def invoke(self, messages):
        self.calls.append(messages)
        if isinstance(self.reply, Exception):
            raise self.reply
        return ScheduleExplanation(text=self.reply)


def test_valid_llm_explanation_is_used_and_prompt_has_plan_data():
    llm = FakeLLM(GOOD)
    e = SchedulerAgent(llm, TZ).explain(FACTS)
    assert (e.source, e.text, e.issues) == (ExplanationSource.LLM, GOOD, ())
    assert llm.schema is ScheduleExplanation
    human = llm.calls[0][1][1]
    assert '"khung_dung": "09:00 03/10 – 12:00 03/10"' in human
    assert '"lich_moi": "Line B 11:00 03/10 – 13:00 03/10"' in human
    assert '"ket_qua": "trễ giờ trả 30 phút"' in human


def test_payload_keeps_processing_order_and_reasons():
    p = payload(FACTS, TZ)
    assert [d["ten"] for d in p["don"]] == ["Hạt tiêu", "Quế"]
    assert [d["ly_do"] for d in p["don"]] == ["sang line còn lại", "bị đẩy lùi để nhường đơn ưu tiên cao hơn đang trễ"]


@pytest.mark.parametrize(
    ("reply", "issue"),
    [
        # Giờ không có trong dữ liệu
        (GOOD.replace("11:00–13:00", "11:00–13:15"), "giờ 13:15 không có trong dữ liệu"),
        # Giờ có trong dữ liệu (13:00 trên Line B) nhưng gắn sai line
        (GOOD.replace("sang Line B 08:00–11:00", "sang Line A 13:00"), "Line A 13:00 không khớp slot / khung dừng"),
        (GOOD.replace("30 phút", "45 phút"), "45 phút không có trong dữ liệu"),
        (GOOD.replace("Quế (Thường)", "Đơn Thường"), "thiếu đơn Quế"),
        (GOOD.replace("đang chờ duyệt", "đã được duyệt"), "nội dung cấm: đã được duyệt"),
        (GOOD + " Liều chiếu giữ nguyên.", "nội dung cấm: Liều"),
        (GOOD.replace("09:00–12:00", "09:00–12:00 04/10"), "ngày 04/10 không có trong dữ liệu"),
    ],
)
def test_explanation_not_matching_data_falls_back_to_template(reply, issue):
    """TC: giờ và line trong câu giải thích phải khớp dữ liệu."""
    e = SchedulerAgent(FakeLLM(reply), TZ).explain(FACTS)
    assert e.source == ExplanationSource.TEMPLATE and e.text == template(FACTS, TZ)
    assert issue in e.issues


def test_llm_error_disabled_or_nothing_to_explain_uses_template():
    e = SchedulerAgent(FakeLLM(TimeoutError("chậm")), TZ).explain(FACTS)
    assert (e.source, e.issues) == (ExplanationSource.TEMPLATE, ("LLM lỗi: TimeoutError",))
    assert explain_plan(FACTS, None, TZ).source == ExplanationSource.TEMPLATE
    llm = FakeLLM(GOOD)
    empty = PlanFacts(Line.A, at(9), at(12), [])
    assert (
        SchedulerAgent(llm, TZ).explain(empty).text == "Line A dừng 09:00–12:00 (dự kiến): không có đơn bị ảnh hưởng."
    )
    assert llm.calls == []  # không gọi LLM khi không có đơn


def test_template_satisfies_its_own_constraints():
    assert check_explanation(template(FACTS, TZ), FACTS, TZ) == []


def test_pulled_forward_order_explained_separately():
    """T-058: đơn không bị ảnh hưởng được kéo sớm — đếm riêng, lý do riêng, bản deterministic vẫn qua validator."""
    pulled = MoveSummary(
        "Ớt", Priority.NORMAL, Slot("C", Line.A, at(13), at(15)), Slot("C", Line.A, at(12), at(14)), at(18), False, True
    )
    facts = PlanFacts(Line.A, at(9), at(12), [*FACTS.moves, pulled])
    p = payload(facts, TZ)
    assert (p["so_don_phai_xep_lai"], p["so_don_keo_som"]) == (2, 1)
    assert p["don"][-1]["ly_do"] == "không bị ảnh hưởng, được kéo sớm để lấp khe trống"
    text = template(facts, TZ)
    assert "1 đơn khác được kéo sớm để lấp khe trống" in text and "- Ớt (Thường) được kéo sớm lấp khe trống" in text
    assert check_explanation(text, facts, TZ) == []
