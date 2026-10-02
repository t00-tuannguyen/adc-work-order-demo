"""ADC-005 T-038 — Risk Agent soạn nháp: ràng buộc giờ/nội dung, mẫu soạn sẵn khi LLM lỗi hoặc tắt."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from src.agents.risk_agent import DelayEvent, DraftSource, RiskAgent, check_draft, draft_message, template_message
from src.agents.schemas import EscalationDraft
from src.modules.types import Priority

TZ = timezone(timedelta(hours=7))
EVENT = DelayEvent(
    product_name="Bột ớt",
    priority=Priority.NORMAL,
    requested_return=datetime(2026, 10, 1, 7, 0, tzinfo=UTC),  # 14:00 +07
    expected_finish=datetime(2026, 10, 1, 9, 30, tzinfo=UTC),  # 16:30 +07
    cause="sự cố kỹ thuật trên dây chuyền chiếu xạ",
)
GOOD = (
    "Kính gửi Quý khách, ADC xin lỗi vì đơn Bột ớt không kịp giờ trả 14:00 ngày 01/10/2026 do sự cố kỹ thuật. "
    "Giờ trả mới đề xuất: 16:30 ngày 01/10/2026. Vui lòng liên hệ Bộ phận Kinh doanh ADC."
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
        return EscalationDraft(message=self.reply)


def test_valid_llm_draft_is_used_and_prompt_has_only_event_data():
    llm = FakeLLM(GOOD)
    d = RiskAgent(llm, TZ).draft(EVENT)
    assert (d.source, d.message, d.issues) == (DraftSource.LLM, GOOD, ())
    assert llm.schema is EscalationDraft
    human = llm.calls[0][1][1]
    assert '"gio_tra_da_hen": "14:00 ngày 01/10/2026"' in human
    assert '"gio_tra_moi_de_xuat": "16:30 ngày 01/10/2026"' in human


@pytest.mark.parametrize(
    ("reply", "issue"),
    [
        (GOOD.replace("16:30", "15:00"), "giờ 15:00 không có trong dữ liệu"),  # hứa giờ khác dữ liệu
        (GOOD.replace("16:30 ngày 01/10/2026", "chiều mai"), "thiếu giờ trả mới đề xuất"),
        (GOOD + " Hàng vẫn đảm bảo an toàn.", "nhắc tới nội dung cấm: an toàn"),
        (GOOD + " Liều 10 kGy giữ nguyên.", "nhắc tới nội dung cấm: Liều"),
        (GOOD.replace("01/10/2026. Vui", "02/10/2026. Vui"), "ngày 02/10 không có trong dữ liệu"),
    ],
)
def test_draft_violating_constraints_falls_back_to_template(reply, issue):
    """TC: nháp không chứa giờ sai so với dữ liệu."""
    d = RiskAgent(FakeLLM(reply), TZ).draft(EVENT)
    assert d.source == DraftSource.TEMPLATE and d.message == template_message(EVENT, TZ)
    assert issue in d.issues


def test_llm_error_or_disabled_uses_template():
    d = RiskAgent(FakeLLM(TimeoutError("chậm")), TZ).draft(EVENT)
    assert (d.source, d.issues) == (DraftSource.TEMPLATE, ("LLM lỗi: TimeoutError",))
    assert draft_message(EVENT, None, TZ).source == DraftSource.TEMPLATE


def test_template_satisfies_its_own_constraints():
    message = template_message(EVENT, TZ)
    assert check_draft(message, EVENT, TZ) == []
    assert "14:00 ngày 01/10/2026" in message and "16:30 ngày 01/10/2026" in message
