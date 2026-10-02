"""Luật phê duyệt HITL theo plan version — FR 12, ADR-0005, specs/user-roles.md §4."""

from collections.abc import Iterable
from enum import StrEnum

from src.modules.orchestration.state_machine import PlanVersionStatus


class ChangeType(StrEnum):
    # Không cần duyệt: gán line còn trống, không ảnh hưởng SLA (đảo ngược được, deterministic)
    LINE_ASSIGNMENT = "LINE_ASSIGNMENT"
    # 4 loại cần duyệt
    RETURN_TIME_CHANGE = "RETURN_TIME_CHANGE"  # đổi giờ trả đã hứa
    INCIDENT_DELAY = "INCIDENT_DELAY"  # hoãn đơn do sự cố
    PRIORITY_OVERRIDE = "PRIORITY_OVERRIDE"  # override ưu tiên
    ACCEPT_DURING_WARNING = "ACCEPT_DURING_WARNING"  # nhận đơn mới khi đang cảnh báo


APPROVAL_REQUIRED: frozenset[ChangeType] = frozenset(
    {
        ChangeType.RETURN_TIME_CHANGE,
        ChangeType.INCIDENT_DELAY,
        ChangeType.PRIORITY_OVERRIDE,
        ChangeType.ACCEPT_DURING_WARNING,
    }
)


def requires_approval(changes: Iterable[ChangeType]) -> bool:
    return any(c in APPROVAL_REQUIRED for c in changes)


def initial_plan_status(changes: Iterable[ChangeType], *, is_simulation: bool = False) -> PlanVersionStatus:
    """Version có ≥ 1 thay đổi cần duyệt → PENDING_APPROVAL, ngược lại ACTIVE ngay (BR-08).

    Plan mô phỏng không bao giờ ACTIVE (BR-11).
    """
    if is_simulation:
        return PlanVersionStatus.PROPOSED
    return PlanVersionStatus.PENDING_APPROVAL if requires_approval(changes) else PlanVersionStatus.ACTIVE
