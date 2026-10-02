"""Đánh giá Risk Agent soạn thông điệp escalation trên 10 tình huống mẫu (T-038, ADC-005 §Thiết kế AI/ML).

    .venv/bin/python -m eval.risk.run_eval

Gọi LLM thật (OPENAI_API_KEY trong .env). Ràng buộc cứng (`check_draft`: giờ/ngày đúng dữ liệu, có giờ trả mới,
không nhắc liều / an toàn) chấm tự động; phần còn lại của checklist chấm tay trong báo cáo
eval/results/risk-messages.md: lịch sự, có lời xin lỗi, nguyên nhân ở mức chung, có đầu mối liên hệ, ngắn gọn.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from src.agents.risk_agent import DelayEvent, DraftSource, RiskAgent, check_draft
from src.modules.types import Priority
from src.services.llm import get_llm
from src.settings import get_settings

RESULTS = Path("eval/results")
INCIDENT = "sự cố kỹ thuật trên dây chuyền chiếu xạ"
BUMP = "điều chỉnh kế hoạch sản xuất để ưu tiên đơn hàng khẩn"
BASE = datetime(2026, 10, 1, 1, 0, tzinfo=UTC)  # 08:00 +07


def _case(product: str, priority: Priority, ret_h: float, late_min: int, cause: str) -> DelayEvent:
    ret = BASE + timedelta(hours=ret_h)
    return DelayEvent(product, priority, ret, ret + timedelta(minutes=late_min), cause)


CASES: list[DelayEvent] = [
    _case("Bột ớt xay khô", Priority.NORMAL, 6, 60, INCIDENT),
    _case("Hạt tiêu đen", Priority.VIP, 4.5, 15, INCIDENT),
    _case("Bột nghệ vàng", Priority.URGENT, 5, 120, INCIDENT),
    _case("Gia vị tổng hợp", Priority.NORMAL, 9, 210, BUMP),
    _case("Quế thanh", Priority.VIP, 9, 45, INCIDENT),
    _case("Hoa hồi khô", Priority.URGENT, 9.5, 30, INCIDENT),
    _case("Tiêu trắng", Priority.NORMAL, 11, 600, INCIDENT),  # trễ sang hôm sau
    _case("Ớt bột Hàn Quốc", Priority.NORMAL, 13.5, 90, BUMP),  # giờ trả 21:30
    _case("Xoài sấy", Priority.URGENT, 2, 240, INCIDENT),
    _case("Găng tay y tế", Priority.VIP, 7, 5, INCIDENT),
]

CHECKLIST = "Lịch sự · Xin lỗi · Nguyên nhân chung · Đầu mối liên hệ · Ngắn gọn (chấm tay: ✅/❌)"


def main() -> None:
    settings = get_settings()
    agent = RiskAgent(get_llm(), settings.local_tz)
    lines = [
        "# Đánh giá Risk Agent — thông điệp escalation (T-038)",
        "",
        f"Model: `{settings.model_name}` · {len(CASES)} tình huống · checklist tay: {CHECKLIST}",
        "",
    ]
    passed = 0
    for i, event in enumerate(CASES, 1):
        draft = agent.draft(event)
        hard_ok = draft.source == DraftSource.LLM and not check_draft(draft.message, event, settings.local_tz)
        passed += hard_ok
        lines += [
            f"## {i}. {event.product_name} ({event.priority.value}) — {draft.source.value}",
            "",
            f"Ràng buộc cứng: {'✅' if hard_ok else '❌ ' + '; '.join(draft.issues)}",
            "",
            "> " + draft.message.replace("\n", "\n> "),
            "",
            "Checklist tay: [ ] Lịch sự [ ] Xin lỗi [ ] Nguyên nhân chung [ ] Đầu mối liên hệ [ ] Ngắn gọn",
            "",
        ]
    lines.insert(4, f"**Ràng buộc cứng đạt: {passed}/{len(CASES)}** (nháp LLM không phải thay bằng mẫu soạn sẵn)\n")
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "risk-messages.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"{passed}/{len(CASES)} đạt ràng buộc cứng → {RESULTS / 'risk-messages.md'}")


if __name__ == "__main__":
    main()
