"""Risk context — ADC-005.

Mức rủi ro là luật deterministic; LLM chỉ soạn nháp thông điệp (Risk & Escalation Agent).
Kiểm tra rủi ro đơn mới (T-036): `assess_new_order`. Orchestration gọi khi xếp lịch và ghi `risk_checks`.
Escalation (T-037): bảng `escalations`; Orchestration tạo mục cho mọi đơn trễ giờ trả (BR-06).
Không import `orchestration` (Orchestration import module này — tránh vòng).
"""

from src.modules.risk.assessment import RiskAssessment, assess_new_order
from src.modules.risk.levels import EscalationStatus, RiskLevel
from src.modules.risk.models import OPEN_ESCALATION, Escalation, RiskCheck

__all__ = [
    "OPEN_ESCALATION",
    "Escalation",
    "EscalationStatus",
    "RiskAssessment",
    "RiskCheck",
    "RiskLevel",
    "assess_new_order",
]
