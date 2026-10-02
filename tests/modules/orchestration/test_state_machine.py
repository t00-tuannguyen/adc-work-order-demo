"""ADC-006 — state machine và luật duyệt."""

import pytest

from src.modules.orchestration import (
    WORK_ORDER_TRANSITIONS,
    ChangeType,
    InvalidTransitionError,
    PlanVersionStatus,
    WorkOrderState,
    assert_transition,
    initial_plan_status,
)

S = WorkOrderState

HAPPY_PATH = [
    S.DRAFT, S.FEASIBILITY_CHECK, S.SCHEDULED, S.WAITING_ARRIVAL, S.READY_FOR_IRRADIATION,
    S.IN_IRRADIATION, S.COMPLETED_IRRADIATION, S.READY_FOR_RETURN, S.RETURNED, S.CLOSED,
]  # fmt: skip


def test_happy_path_is_valid():
    for a, b in zip(HAPPY_PATH, HAPPY_PATH[1:], strict=False):
        assert_transition(WORK_ORDER_TRANSITIONS, a, b)


@pytest.mark.parametrize(
    ("a", "b"),
    [(S.DRAFT, S.SCHEDULED), (S.DRAFT, S.IN_IRRADIATION), (S.CLOSED, S.DRAFT), (S.SCHEDULED, S.RETURNED)],
)
def test_invalid_transition_rejected(a, b):
    with pytest.raises(InvalidTransitionError):
        assert_transition(WORK_ORDER_TRANSITIONS, a, b)


@pytest.mark.parametrize(
    ("a", "b"),
    [
        # duyệt phương án (T-042)
        (S.PENDING_APPROVAL, S.SCHEDULED),
        (S.LINE_INCIDENT, S.SCHEDULED),
        (S.SLA_RISK, S.SCHEDULED),
        (S.ESCALATED_TO_BUSINESS, S.SCHEDULED),
        # từ chối
        (S.PENDING_APPROVAL, S.RESCHEDULE_REQUIRED),
        (S.LINE_INCIDENT, S.RESCHEDULE_REQUIRED),
        (S.SLA_RISK, S.RESCHEDULE_REQUIRED),
        (S.ESCALATED_TO_BUSINESS, S.RESCHEDULE_REQUIRED),
        # Điều phối xếp tay lại (BR-15)
        (S.RESCHEDULE_REQUIRED, S.SCHEDULED),
        (S.RESCHEDULE_REQUIRED, S.PENDING_APPROVAL),
    ],
)
def test_exception_transitions_valid(a, b):
    assert_transition(WORK_ORDER_TRANSITIONS, a, b)


@pytest.mark.parametrize(
    ("a", "b"),
    [
        (S.RESCHEDULE_REQUIRED, S.IN_IRRADIATION),
        (S.LINE_INCIDENT, S.WAITING_ARRIVAL),
        (S.BLOCK_NEW_ORDER, S.SCHEDULED),  # override BLOCK chưa có trong contract
        (S.IN_IRRADIATION, S.RESCHEDULE_REQUIRED),
    ],
)
def test_exception_shortcuts_rejected(a, b):
    with pytest.raises(InvalidTransitionError):
        assert_transition(WORK_ORDER_TRANSITIONS, a, b)


@pytest.mark.parametrize(
    "change",
    [
        ChangeType.RETURN_TIME_CHANGE,
        ChangeType.INCIDENT_DELAY,
        ChangeType.PRIORITY_OVERRIDE,
        ChangeType.ACCEPT_DURING_WARNING,
    ],
)
def test_each_customer_impacting_change_needs_approval(change):
    assert initial_plan_status([ChangeType.LINE_ASSIGNMENT, change]) == PlanVersionStatus.PENDING_APPROVAL


def test_line_assignment_without_sla_impact_is_active_immediately():
    assert initial_plan_status([ChangeType.LINE_ASSIGNMENT]) == PlanVersionStatus.ACTIVE


def test_simulation_plan_never_active():
    assert initial_plan_status([ChangeType.LINE_ASSIGNMENT], is_simulation=True) != PlanVersionStatus.ACTIVE
