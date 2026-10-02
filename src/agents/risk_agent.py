"""Risk & Escalation Agent — soạn NHÁP thông điệp cho kinh doanh / khách về đơn trễ (ADC-005, T-038).

LLM chỉ viết câu chữ từ dữ liệu deterministic (giờ trả cũ, giờ xong dự kiến mới, nguyên nhân chung); không quyết
định gì và không gọi được hàm duyệt. Nháp luôn qua `check_draft`: giờ/ngày phải khớp dữ liệu, phải nêu giờ trả mới,
không nhắc liều chiếu hay an toàn — vi phạm, LLM lỗi hoặc tắt (feature flag / thiếu key) → mẫu soạn sẵn để sửa tay.
Không đưa thông tin khách vào prompt (work order chỉ có tên sản phẩm).
"""

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, tzinfo
from enum import StrEnum
from typing import Any

from src.agents.schemas import EscalationDraft
from src.modules.types import PRIORITY_LABEL, Priority

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Bạn là nhân viên kinh doanh của trung tâm chiếu xạ ADC. Soạn NHÁP thông điệp gửi khách hàng báo đơn
hàng bị trễ giờ trả, dựa DUY NHẤT vào dữ liệu JSON cho trước.
- Tiếng Việt, ngắn (tối đa ~120 từ), lịch sự: lời xin lỗi, nguyên nhân ở mức chung (đúng như trường "nguyen_nhan"),
  giờ trả mới đề xuất, đầu mối liên hệ.
- Giờ và ngày CHÉP NGUYÊN VĂN từ dữ liệu (định dạng "HH:MM ngày DD/MM/YYYY"). KHÔNG tự nêu giờ, ngày, số phút hay
  cam kết nào khác. KHÔNG hứa giờ sớm hơn giờ trả mới.
- KHÔNG đề cập liều chiếu, kGy, an toàn, bức xạ hay chi tiết kỹ thuật; không nêu tên line, tên khách hàng hay đơn khác.
- Xưng "ADC", gọi khách là "Quý khách". Không ký tên người cụ thể.
Trả về JSON theo schema: {"message": "<nội dung thông điệp>"}.
"""

BANNED = re.compile(r"liều|kgy|an toàn|bức xạ|phóng xạ|line\s*[ab]\b", re.IGNORECASE)
TIME = re.compile(r"\b(\d{1,2})\s*[:hg]\s*(\d{2})\b")
DATE = re.compile(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{4}))?\b")


class DraftSource(StrEnum):
    LLM = "LLM"
    TEMPLATE = "TEMPLATE"  # mẫu soạn sẵn — LLM lỗi / tắt / nháp vi phạm ràng buộc


@dataclass(frozen=True)
class DelayEvent:
    """Dữ liệu deterministic của 1 escalation — nguồn sự thật duy nhất cho giờ trong thông điệp."""

    product_name: str
    priority: Priority
    requested_return: datetime
    expected_finish: datetime
    cause: str  # mức chung, vd "sự cố kỹ thuật trên dây chuyền chiếu xạ"
    contact: str = "Bộ phận Kinh doanh ADC"


@dataclass(frozen=True)
class Draft:
    message: str
    source: DraftSource
    issues: tuple[str, ...] = ()  # vì sao không dùng nháp LLM (log / debug)


def _at(t: datetime, tz: tzinfo) -> str:
    return t.astimezone(tz).strftime("%H:%M ngày %d/%m/%Y")


def payload(event: DelayEvent, tz: tzinfo) -> dict[str, str]:
    return {
        "san_pham": event.product_name,
        "uu_tien": PRIORITY_LABEL[event.priority],
        "gio_tra_da_hen": _at(event.requested_return, tz),
        "gio_tra_moi_de_xuat": _at(event.expected_finish, tz),
        "nguyen_nhan": event.cause,
        "dau_moi_lien_he": event.contact,
    }


def template_message(event: DelayEvent, tz: tzinfo) -> str:
    """Mẫu soạn sẵn — luôn đúng dữ liệu, người duyệt sửa tay."""
    return (
        "Kính gửi Quý khách,\n\n"
        f"ADC thành thật xin lỗi vì đơn hàng {event.product_name} không thể hoàn tất đúng giờ trả đã hẹn "
        f"({_at(event.requested_return, tz)}) do {event.cause}.\n"
        f"Giờ trả mới ADC đề xuất: {_at(event.expected_finish, tz)}.\n\n"
        f"Mọi thắc mắc, Quý khách vui lòng liên hệ {event.contact}.\n\n"
        "Trân trọng,\nADC"
    )


def check_draft(message: str, event: DelayEvent, tz: tzinfo) -> list[str]:
    """Ràng buộc ADC-005 §Thiết kế AI: không hứa giờ khác dữ liệu, không nhắc an toàn / liều chiếu."""
    issues = []
    if not message.strip():
        return ["nháp rỗng"]
    old, new = event.requested_return.astimezone(tz), event.expected_finish.astimezone(tz)
    times = {(old.hour, old.minute), (new.hour, new.minute)}
    for h, m in TIME.findall(message):
        if (int(h), int(m)) not in times:
            issues.append(f"giờ {h}:{m} không có trong dữ liệu")
    dates = {(old.day, old.month), (new.day, new.month)}
    for d, mo, y in DATE.findall(message):
        if (int(d), int(mo)) not in dates or (y and int(y) not in {old.year, new.year}):
            issues.append(f"ngày {d}/{mo} không có trong dữ liệu")
    if not any((int(h), int(m)) == (new.hour, new.minute) for h, m in TIME.findall(message)):
        issues.append("thiếu giờ trả mới đề xuất")
    if hit := BANNED.search(message):
        issues.append(f"nhắc tới nội dung cấm: {hit.group(0)}")
    return issues


class RiskAgent:
    """`llm`: chat model LangChain hỗ trợ `with_structured_output` (services/llm.get_llm)."""

    def __init__(self, llm: Any, tz: tzinfo):
        self.llm = llm.with_structured_output(EscalationDraft)
        self.tz = tz

    def draft(self, event: DelayEvent) -> Draft:
        fallback = template_message(event, self.tz)
        try:
            out = self.llm.invoke(
                [("system", SYSTEM_PROMPT), ("human", json.dumps(payload(event, self.tz), ensure_ascii=False))]
            )
            message = EscalationDraft.model_validate(out).message.strip()
        except Exception as e:  # LLM lỗi / timeout / sai schema → mẫu soạn sẵn, không chặn kinh doanh
            logger.warning("Risk Agent lỗi, dùng mẫu soạn sẵn: %s", e)
            return Draft(fallback, DraftSource.TEMPLATE, (f"LLM lỗi: {type(e).__name__}",))
        if issues := check_draft(message, event, self.tz):
            logger.warning("Nháp Risk Agent vi phạm ràng buộc, dùng mẫu soạn sẵn: %s", issues)
            return Draft(fallback, DraftSource.TEMPLATE, tuple(issues))
        return Draft(message, DraftSource.LLM)


def draft_message(event: DelayEvent, agent: RiskAgent | None, tz: tzinfo) -> Draft:
    """Không có agent (feature flag tắt / thiếu OPENAI_API_KEY) → mẫu soạn sẵn."""
    if agent is None:
        return Draft(template_message(event, tz), DraftSource.TEMPLATE, ("AI soạn thông điệp đang tắt",))
    return agent.draft(event)
