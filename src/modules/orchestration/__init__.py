"""Orchestration context — ADC-006. Nơi DUY NHẤT được ghi trạng thái work order và plan version.

Xếp lịch → plan version, kiểm tra rủi ro đơn mới: planning.py (T-028, T-036). Sự cố line: incidents.py (T-031).
Lịch sử trạng thái: history.py (T-041). Duyệt / từ chối / diff plan version: review.py (T-042).
"""

from src.modules.orchestration.approval import APPROVAL_REQUIRED, ChangeType, initial_plan_status, requires_approval
from src.modules.orchestration.audit import AuditAction, AuditLog, AuditLogImmutableError, record
from src.modules.orchestration.escalations import (
    EscalationStateError,
    approve_escalation,
    open_escalation,
    raise_escalation,
    save_draft,
)
from src.modules.orchestration.history import ActorType, StateHistory, record_created, work_order_history
from src.modules.orchestration.incidents import (
    IncidentConflictError,
    InvalidIncidentError,
    declare_incident,
    replan_incident,
    resolve_incident,
)
from src.modules.orchestration.plan_versions import PlanChange, PlanTrigger, PlanVersion
from src.modules.orchestration.planning import (
    ManualScheduleResult,
    MissingEstimateError,
    NewOrderBlockedError,
    NotSchedulableError,
    OrderLoader,
    PlanConflictError,
    ScheduleResult,
    active_version,
    check_new_order_risk,
    place_work_order_manually,
    schedule_work_order,
    slot_details,
    version_slots,
)
from src.modules.orchestration.review import (
    APPROVE_TO_SCHEDULED,
    REJECT_TO_RESCHEDULE,
    ChangeDiff,
    PlanDiff,
    PlanVersionNotFoundError,
    PlanVersionStateError,
    approve_plan_version,
    plan_diff,
    reject_plan_version,
)
from src.modules.orchestration.state_machine import (
    ESCALATION_TRANSITIONS,
    OPERATIONAL_STATES,
    PLAN_VERSION_TRANSITIONS,
    WORK_ORDER_TRANSITIONS,
    EscalationStatus,
    InvalidTransitionError,
    PlanVersionStatus,
    WorkOrderState,
    assert_transition,
    can_transition,
)
from src.modules.orchestration.transitions import transition_work_order

__all__ = [
    "APPROVE_TO_SCHEDULED",
    "REJECT_TO_RESCHEDULE",
    "ChangeDiff",
    "PlanDiff",
    "PlanVersionNotFoundError",
    "PlanVersionStateError",
    "approve_plan_version",
    "plan_diff",
    "reject_plan_version",
    "ActorType",
    "StateHistory",
    "record_created",
    "work_order_history",
    "EscalationStateError",
    "approve_escalation",
    "save_draft",
    "open_escalation",
    "raise_escalation",
    "IncidentConflictError",
    "InvalidIncidentError",
    "declare_incident",
    "replan_incident",
    "resolve_incident",
    "OPERATIONAL_STATES",
    "MissingEstimateError",
    "NewOrderBlockedError",
    "NotSchedulableError",
    "OrderLoader",
    "check_new_order_risk",
    "PlanChange",
    "PlanConflictError",
    "PlanTrigger",
    "PlanVersion",
    "ScheduleResult",
    "active_version",
    "schedule_work_order",
    "place_work_order_manually",
    "ManualScheduleResult",
    "slot_details",
    "version_slots",
    "AuditAction",
    "AuditLog",
    "AuditLogImmutableError",
    "APPROVAL_REQUIRED",
    "ESCALATION_TRANSITIONS",
    "PLAN_VERSION_TRANSITIONS",
    "WORK_ORDER_TRANSITIONS",
    "ChangeType",
    "EscalationStatus",
    "InvalidTransitionError",
    "PlanVersionStatus",
    "WorkOrderState",
    "assert_transition",
    "record",
    "can_transition",
    "initial_plan_status",
    "requires_approval",
    "transition_work_order",
]
