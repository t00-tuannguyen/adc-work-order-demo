"""specs/user-roles.md §2 — ma trận quyền; ADC-008 TC2."""

from src.modules.identity import Action, Role, UserStatus, is_allowed


def test_pending_or_disabled_user_cannot_access_data():
    for status in (UserStatus.PENDING, UserStatus.DISABLED):
        assert not is_allowed(Role.OPS_MANAGER, status, Action.VIEW_BOARD)
    assert not is_allowed(None, UserStatus.ACTIVE, Action.VIEW_BOARD)


def test_only_planner_declares_incident():
    allowed = {r for r in Role if is_allowed(r, UserStatus.ACTIVE, Action.DECLARE_INCIDENT)}
    assert allowed == {Role.PLANNER}


def test_planner_cannot_approve_plan_version():
    assert not is_allowed(Role.PLANNER, UserStatus.ACTIVE, Action.APPROVE_PLAN_VERSION)


def test_only_ops_manager_overrides_block():
    allowed = {r for r in Role if is_allowed(r, UserStatus.ACTIVE, Action.OVERRIDE_BLOCK)}
    assert allowed == {Role.OPS_MANAGER}


def test_sales_and_ops_manager_approve_plan_version():
    # ADC-008 TC9 (đã sửa): PLANNER gọi approve → 403
    allowed = {r for r in Role if is_allowed(r, UserStatus.ACTIVE, Action.APPROVE_PLAN_VERSION)}
    assert allowed == {Role.SALES, Role.OPS_MANAGER}
