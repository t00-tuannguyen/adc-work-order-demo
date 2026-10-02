"""Vai trò, trạng thái tài khoản và ma trận quyền — specs/user-roles.md §2."""

from enum import StrEnum


class Role(StrEnum):
    SALES = "SALES"
    PLANNER = "PLANNER"
    OPS_MANAGER = "OPS_MANAGER"
    ADMIN = "ADMIN"


class UserStatus(StrEnum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class Action(StrEnum):
    UPLOAD_TICKET = "UPLOAD_TICKET"
    VIEW_BOARD = "VIEW_BOARD"  # Kanban, lịch, KPI
    EDIT_SCHEDULE = "EDIT_SCHEDULE"
    CHANGE_OPERATIONAL_STATE = "CHANGE_OPERATIONAL_STATE"
    DECLARE_INCIDENT = "DECLARE_INCIDENT"
    APPROVE_PLAN_VERSION = "APPROVE_PLAN_VERSION"
    OVERRIDE_BLOCK = "OVERRIDE_BLOCK"
    APPROVE_ESCALATION_MESSAGE = "APPROVE_ESCALATION_MESSAGE"
    MANAGE_USERS = "MANAGE_USERS"


R = Role

# Ma trận quyền — specs/user-roles.md §2
PERMISSIONS: dict[Action, frozenset[Role]] = {
    Action.UPLOAD_TICKET: frozenset({R.SALES}),
    Action.VIEW_BOARD: frozenset({R.SALES, R.PLANNER, R.OPS_MANAGER, R.ADMIN}),
    Action.EDIT_SCHEDULE: frozenset({R.PLANNER}),
    Action.CHANGE_OPERATIONAL_STATE: frozenset({R.PLANNER}),
    Action.DECLARE_INCIDENT: frozenset({R.PLANNER}),
    Action.APPROVE_PLAN_VERSION: frozenset({R.SALES, R.OPS_MANAGER}),
    Action.OVERRIDE_BLOCK: frozenset({R.OPS_MANAGER}),
    Action.APPROVE_ESCALATION_MESSAGE: frozenset({R.SALES, R.OPS_MANAGER}),
    Action.MANAGE_USERS: frozenset({R.ADMIN}),
}


def is_allowed(role: Role | None, status: UserStatus, action: Action) -> bool:
    """User PENDING/DISABLED hoặc chưa có vai trò → không truy cập dữ liệu (403)."""
    if status != UserStatus.ACTIVE or role is None:
        return False
    return role in PERMISSIONS[action]
