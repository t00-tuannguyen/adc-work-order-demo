"""Scheduler Agent — giải thích phương án tái lập lịch khi sự cố line bằng ngôn ngữ nghiệp vụ (ADC-004, T-034).

Thuật toán deterministic (`reschedule`) đã quyết định thứ tự, line và giờ; LLM chỉ viết lại câu chữ từ kết quả đó,
không tự quyết hay đề xuất gì. Câu giải thích luôn qua `check_explanation`: mọi giờ / ngày / số phút phải có trong dữ
liệu, mỗi cặp "Line X HH:MM" phải đúng là mốc của slot hoặc khung dừng trên line đó, phải nhắc đủ các đơn, không
nói phương án đã được duyệt hay nhắc liều chiếu / an toàn. Vi phạm, LLM lỗi hoặc tắt → giải thích deterministic
(`incident_explanation`). Prompt chỉ có tên sản phẩm, ưu tiên và mốc giờ — không có thông tin khách.
"""

import json
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, tzinfo
from enum import StrEnum
from typing import Any

from src.agents.schemas import ScheduleExplanation
from src.modules.scheduling import MoveSummary, incident_explanation, late_minutes
from src.modules.types import PRIORITY_LABEL, Line

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Bạn là Scheduler Agent của trung tâm chiếu xạ ADC (2 line A và B). Một line vừa dừng do sự cố;
thuật toán xếp lịch ĐÃ tính xong phương án. Hãy giải thích phương án đó cho điều phối viên và người duyệt bằng tiếng
Việt nghiệp vụ, dựa DUY NHẤT vào dữ liệu JSON cho trước.
- Câu mở đầu: line nào dừng, khung giờ nào, bao nhiêu đơn phải xếp lại.
- Mỗi đơn 1 câu ngắn, theo đúng thứ tự trong danh sách: tên đơn, lịch cũ → lịch mới, vì sao (sang line còn lại /
  chờ line hồi phục / bị đẩy lùi để nhường đơn ưu tiên cao hơn / được kéo sớm để lấp khe trống line), kịp hay trễ
  giờ trả (trễ bao nhiêu phút).
- Câu cuối: phương án đang CHỜ DUYỆT, lịch đang chạy chưa đổi; nếu có đơn trễ thì kinh doanh cần báo khách.
- Giờ, ngày, số phút, tên line CHÉP NGUYÊN VĂN từ dữ liệu (dạng "Line A 09:00 03/10"). KHÔNG tự tính, làm tròn hay
  thêm mốc giờ nào khác. KHÔNG nói phương án đã được duyệt. KHÔNG nhắc liều chiếu, kGy, an toàn, bức xạ.
- Tối đa ~150 từ, không dùng markdown.
Trả về JSON theo schema: {"text": "<đoạn giải thích>"}.
"""

TIME = re.compile(r"\b(\d{1,2})\s*[:h]\s*(\d{2})\b")
DATE = re.compile(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{4}))?\b")
LINE_TIME = re.compile(r"\bLine\s*([AB])\s+(\d{1,2})\s*[:h]\s*(\d{2})\b", re.IGNORECASE)
MINUTES = re.compile(r"\b(\d+)\s*phút\b", re.IGNORECASE)
BANNED = re.compile(r"liều|kgy|an toàn|bức xạ|phóng xạ|đã (?:được )?(?:phê )?duyệt", re.IGNORECASE)


class ExplanationSource(StrEnum):
    LLM = "LLM"
    TEMPLATE = "TEMPLATE"  # giải thích deterministic — LLM lỗi / tắt / vi phạm ràng buộc


@dataclass(frozen=True)
class PlanFacts:
    """Kết quả deterministic của 1 phương án sự cố — nguồn sự thật duy nhất cho mọi con số trong giải thích."""

    line: Line
    start: datetime
    end: datetime
    moves: Sequence[MoveSummary]
    resolved: bool = False


@dataclass(frozen=True)
class Explanation:
    text: str
    source: ExplanationSource
    issues: tuple[str, ...] = ()  # vì sao không dùng câu của LLM (log / debug)


def _at(t: datetime, tz: tzinfo) -> str:
    return t.astimezone(tz).strftime("%H:%M %d/%m")


def template(facts: PlanFacts, tz: tzinfo) -> str:
    return incident_explanation(facts.line, facts.start, facts.end, facts.moves, tz, resolved=facts.resolved)


def _why(m: MoveSummary) -> str:
    if m.pulled:
        return "không bị ảnh hưởng, được kéo sớm để lấp khe trống"
    if m.bumped:
        return "bị đẩy lùi để nhường đơn ưu tiên cao hơn đang trễ"
    return "sang line còn lại" if m.new.line != m.old.line else "chờ line hồi phục"


def payload(facts: PlanFacts, tz: tzinfo) -> dict[str, Any]:
    def slot(line: Line, a: datetime, b: datetime) -> str:
        return f"Line {line.value} {_at(a, tz)} – {_at(b, tz)}"

    return {
        "line_dung": f"Line {facts.line.value}",
        "khung_dung": f"{_at(facts.start, tz)} – {_at(facts.end, tz)}",
        "trang_thai_su_co": "đã hồi phục" if facts.resolved else "dự kiến",
        "so_don_phai_xep_lai": sum(1 for m in facts.moves if not m.pulled),
        "so_don_keo_som": sum(1 for m in facts.moves if m.pulled),
        "don": [
            {
                "ten": m.label,
                "uu_tien": PRIORITY_LABEL[m.priority],
                "lich_cu": slot(m.old.line, m.old.start, m.old.end),
                "lich_moi": slot(m.new.line, m.new.start, m.new.end),
                "ly_do": _why(m),
                "gio_tra": _at(m.requested_return, tz),
                "ket_qua": f"trễ giờ trả {late_minutes(m)} phút" if late_minutes(m) else "kịp giờ trả",
            }
            for m in facts.moves
        ],
        "phuong_an": "chờ duyệt, lịch đang chạy chưa đổi",
    }


def check_explanation(text: str, facts: PlanFacts, tz: tzinfo) -> list[str]:
    """Ràng buộc ADC-004 §Thiết kế AI: giờ và line trong câu giải thích phải khớp dữ liệu."""
    if not text.strip():
        return ["giải thích rỗng"]
    marks: set[tuple[Line, datetime]] = {(facts.line, facts.start), (facts.line, facts.end)}
    for m in facts.moves:
        marks |= {
            (m.old.line, m.old.start),
            (m.old.line, m.old.end),
            (m.new.line, m.new.start),
            (m.new.line, m.new.end),
        }
    stamps = [t.astimezone(tz) for _, t in marks] + [m.requested_return.astimezone(tz) for m in facts.moves]
    times = {(t.hour, t.minute) for t in stamps}
    dates = {(t.day, t.month) for t in stamps}
    line_times = {(line.value, t.astimezone(tz).hour, t.astimezone(tz).minute) for line, t in marks}
    minutes = {late_minutes(m) for m in facts.moves} | {int((facts.end - facts.start).total_seconds() // 60)}

    issues = []
    for h, mi in TIME.findall(text):
        if (int(h), int(mi)) not in times:
            issues.append(f"giờ {h}:{mi} không có trong dữ liệu")
    for d, mo, y in DATE.findall(text):
        if (int(d), int(mo)) not in dates or (y and int(y) not in {t.year for t in stamps}):
            issues.append(f"ngày {d}/{mo} không có trong dữ liệu")
    for line, h, mi in LINE_TIME.findall(text):
        if (line.upper(), int(h), int(mi)) not in line_times:
            issues.append(f"Line {line.upper()} {h}:{mi} không khớp slot / khung dừng")
    for n in MINUTES.findall(text):
        if int(n) not in minutes:
            issues.append(f"{n} phút không có trong dữ liệu")
    lowered = text.casefold()
    for m in facts.moves:
        if m.label.casefold() not in lowered:
            issues.append(f"thiếu đơn {m.label}")
    if hit := BANNED.search(text):
        issues.append(f"nội dung cấm: {hit.group(0)}")
    return issues


class SchedulerAgent:
    """`llm`: chat model LangChain hỗ trợ `with_structured_output` (services/llm.get_llm)."""

    def __init__(self, llm: Any, tz: tzinfo):
        self.llm = llm.with_structured_output(ScheduleExplanation)
        self.tz = tz

    def explain(self, facts: PlanFacts) -> Explanation:
        fallback = template(facts, self.tz)
        if not facts.moves:  # không có gì để giải thích thêm
            return Explanation(fallback, ExplanationSource.TEMPLATE, ("không có đơn bị ảnh hưởng",))
        try:
            out = self.llm.invoke(
                [("system", SYSTEM_PROMPT), ("human", json.dumps(payload(facts, self.tz), ensure_ascii=False))]
            )
            text = ScheduleExplanation.model_validate(out).text.strip()
        except Exception as e:  # LLM lỗi / timeout / sai schema → giải thích deterministic, không chặn điều phối
            logger.warning("Scheduler Agent lỗi, dùng giải thích deterministic: %s", e)
            return Explanation(fallback, ExplanationSource.TEMPLATE, (f"LLM lỗi: {type(e).__name__}",))
        if issues := check_explanation(text, facts, self.tz):
            logger.warning("Giải thích Scheduler Agent sai dữ liệu, dùng bản deterministic: %s", issues)
            return Explanation(fallback, ExplanationSource.TEMPLATE, tuple(issues))
        return Explanation(text, ExplanationSource.LLM)


def explain_plan(facts: PlanFacts, agent: SchedulerAgent | None, tz: tzinfo) -> Explanation:
    """Không có agent (feature flag tắt / thiếu OPENAI_API_KEY) → giải thích deterministic."""
    if agent is None:
        return Explanation(template(facts, tz), ExplanationSource.TEMPLATE, ("AI giải thích đang tắt",))
    return agent.explain(facts)
