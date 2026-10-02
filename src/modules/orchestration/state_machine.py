"""State machine work order, plan version, escalation — ADC-006, specs/domains.md §5."""

from enum import StrEnum

# Enum định nghĩa ở Risk (bảng escalations) để Risk không phải import Orchestration; bảng chuyển ở đây
from src.modules.risk.levels import EscalationStatus


class WorkOrderState(StrEnum):
    # Normal
    DRAFT = "DRAFT"
    FEASIBILITY_CHECK = "FEASIBILITY_CHECK"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    SCHEDULED = "SCHEDULED"
    WAITING_ARRIVAL = "WAITING_ARRIVAL"
    READY_FOR_IRRADIATION = "READY_FOR_IRRADIATION"
    IN_IRRADIATION = "IN_IRRADIATION"
    COMPLETED_IRRADIATION = "COMPLETED_IRRADIATION"
    READY_FOR_RETURN = "READY_FOR_RETURN"
    RETURNED = "RETURNED"
    CLOSED = "CLOSED"
    # Exception
    LINE_INCIDENT = "LINE_INCIDENT"
    SLA_RISK = "SLA_RISK"
    RESCHEDULE_REQUIRED = "RESCHEDULE_REQUIRED"
    ESCALATED_TO_BUSINESS = "ESCALATED_TO_BUSINESS"
    BLOCK_NEW_ORDER = "BLOCK_NEW_ORDER"


class PlanVersionStatus(StrEnum):
    PROPOSED = "PROPOSED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    REJECTED = "REJECTED"


S = WorkOrderState

# Theo sơ đồ trong specs/domains.md §5 (chuyển ngoại lệ chốt 02/10/2026, T-040):
# - Duyệt phương án (T-042): PENDING_APPROVAL / LINE_INCIDENT / SLA_RISK / ESCALATED_TO_BUSINESS → SCHEDULED.
# - Từ chối: các trạng thái đó → RESCHEDULE_REQUIRED; Điều phối xếp tay lại → SCHEDULED hoặc PENDING_APPROVAL (BR-15).
# Override BLOCK_NEW_ORDER chưa có API trong contract → chưa có chuyển ra.
WORK_ORDER_TRANSITIONS: dict[WorkOrderState, frozenset[WorkOrderState]] = {
    S.DRAFT: frozenset({S.FEASIBILITY_CHECK}),
    S.FEASIBILITY_CHECK: frozenset({S.SCHEDULED, S.PENDING_APPROVAL, S.BLOCK_NEW_ORDER}),
    S.PENDING_APPROVAL: frozenset({S.SCHEDULED, S.RESCHEDULE_REQUIRED}),
    S.SCHEDULED: frozenset({S.WAITING_ARRIVAL, S.LINE_INCIDENT}),
    S.WAITING_ARRIVAL: frozenset({S.READY_FOR_IRRADIATION}),
    S.READY_FOR_IRRADIATION: frozenset({S.IN_IRRADIATION}),
    S.IN_IRRADIATION: frozenset({S.COMPLETED_IRRADIATION}),
    S.COMPLETED_IRRADIATION: frozenset({S.READY_FOR_RETURN}),
    S.READY_FOR_RETURN: frozenset({S.RETURNED}),
    S.RETURNED: frozenset({S.CLOSED}),
    S.LINE_INCIDENT: frozenset({S.SLA_RISK, S.SCHEDULED, S.RESCHEDULE_REQUIRED}),
    S.SLA_RISK: frozenset({S.ESCALATED_TO_BUSINESS, S.SCHEDULED, S.RESCHEDULE_REQUIRED}),
    S.ESCALATED_TO_BUSINESS: frozenset({S.SCHEDULED, S.RESCHEDULE_REQUIRED}),
    S.RESCHEDULE_REQUIRED: frozenset({S.SCHEDULED, S.PENDING_APPROVAL}),
}

# Trạng thái vận hành Điều phối được chuyển tay qua PATCH /api/work-orders/{id}/state (ADC-003, user-roles §2)
OPERATIONAL_STATES: frozenset[WorkOrderState] = frozenset(
    {
        S.WAITING_ARRIVAL,
        S.READY_FOR_IRRADIATION,
        S.IN_IRRADIATION,
        S.COMPLETED_IRRADIATION,
        S.READY_FOR_RETURN,
        S.RETURNED,
        S.CLOSED,
    }
)

PLAN_VERSION_TRANSITIONS: dict[PlanVersionStatus, frozenset[PlanVersionStatus]] = {
    PlanVersionStatus.PROPOSED: frozenset({PlanVersionStatus.PENDING_APPROVAL, PlanVersionStatus.ACTIVE}),
    PlanVersionStatus.PENDING_APPROVAL: frozenset(
        {PlanVersionStatus.ACTIVE, PlanVersionStatus.REJECTED, PlanVersionStatus.SUPERSEDED}
    ),
    PlanVersionStatus.ACTIVE: frozenset({PlanVersionStatus.SUPERSEDED}),
}

ESCALATION_TRANSITIONS: dict[EscalationStatus, frozenset[EscalationStatus]] = {
    EscalationStatus.OPEN: frozenset({EscalationStatus.DRAFTED}),
    EscalationStatus.DRAFTED: frozenset({EscalationStatus.APPROVED}),
    EscalationStatus.APPROVED: frozenset({EscalationStatus.CLOSED}),
}


class InvalidTransitionError(ValueError):
    pass


def can_transition(table: dict, from_state: StrEnum, to_state: StrEnum) -> bool:
    return to_state in table.get(from_state, frozenset())


def assert_transition(table: dict, from_state: StrEnum, to_state: StrEnum) -> None:
    if not can_transition(table, from_state, to_state):
        raise InvalidTransitionError(f"không được chuyển {from_state} → {to_state}")
