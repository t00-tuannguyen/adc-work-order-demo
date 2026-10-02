"""ADC-003 T-028, ADC-005 T-036 — xếp lịch thành plan version (ADC-006): OK → ACTIVE ngay, WARN → chờ duyệt,
BLOCK → BLOCK_NEW_ORDER; khóa lạc quan, BR-04, BR-07, BR-09."""

import random
import time
from datetime import UTC, timedelta

import pytest
from sqlalchemy import select

from src.modules.identity import Role, User, UserStatus
from src.modules.intake import Ticket, TicketSourceType, WorkOrder
from src.modules.orchestration import (
    AuditLog,
    ChangeType,
    MissingEstimateError,
    NewOrderBlockedError,
    NotSchedulableError,
    PlanChange,
    PlanConflictError,
    PlanVersion,
    PlanVersionStatus,
    WorkOrderState,
    active_version,
    check_new_order_risk,
    planning,
    schedule_work_order,
    slot_details,
    version_slots,
)
from src.modules.risk import RiskCheck, RiskLevel
from src.modules.scheduling import Slot, has_overlap
from src.modules.types import Line, Priority
from tests.conftest import at


@pytest.fixture
def planner(db):
    user = User(
        google_sub="s", email="p@adc.test", email_domain="adc.test", role=Role.PLANNER, status=UserStatus.ACTIVE
    )
    db.add(user)
    db.commit()
    return user


@pytest.fixture
def make_wo(db):
    def _make(
        duration=180, arrival=at(9), ret=at(16), state=WorkOrderState.FEASIBILITY_CHECK, priority=Priority.NORMAL
    ) -> WorkOrder:
        ticket = Ticket(source_type=TicketSourceType.MANUAL)
        db.add(ticket)
        db.flush()
        wo = WorkOrder(
            ticket_id=ticket.id,
            product_name="Bột ớt",
            priority=priority,
            expected_arrival=arrival,
            requested_return=ret,
            estimated_duration_min=duration,
            state=state,
        )
        db.add(wo)
        db.commit()
        return wo

    return _make


def _loader(db):
    return lambda ids: {w.id: w for w in db.scalars(select(WorkOrder).where(WorkOrder.id.in_(list(ids))))}


def _schedule(db, wo, planner, now=at(8)):
    return schedule_work_order(db, wo, actor_id=planner.id, now=now, tz=UTC, load_orders=_loader(db))


def test_normal_order_line_a_active_immediately(db, planner, make_wo):
    wo = make_wo()
    r = _schedule(db, wo, planner)
    assert (r.placement.line, r.placement.start, r.placement.end, r.placement.sla_ok) == (Line.A, at(9), at(12), True)
    assert r.plan_version.status == PlanVersionStatus.ACTIVE and r.plan_version.parent_version_id is None
    assert wo.state == WorkOrderState.SCHEDULED
    change = db.scalars(select(PlanChange)).one()
    assert (change.change_type, change.needs_approval) == (ChangeType.LINE_ASSIGNMENT, False)
    assert slot_details(db, r.plan_version.id)[wo.id]["reason"] == r.reason


def test_capacity_conflict_new_version_supersedes_old(db, planner, make_wo):
    first = _schedule(db, make_wo(duration=300, arrival=at(8)), planner)  # Line A 08:00–13:00
    wo2 = make_wo(duration=90, arrival=at(9))
    second = _schedule(db, wo2, planner)
    assert (second.placement.line, second.placement.start) == (Line.B, at(9))
    assert second.plan_version.parent_version_id == first.plan_version.id
    db.refresh(first.plan_version)
    assert first.plan_version.status == PlanVersionStatus.SUPERSEDED
    assert active_version(db).id == second.plan_version.id
    assert len(version_slots(db, second.plan_version.id)) == 2
    assert len(version_slots(db, first.plan_version.id)) == 1  # version cũ giữ nguyên để xem lại
    assert "Line A chỉ trống từ 13:00" in second.reason


def _two_full_lines(db, planner, make_wo):
    """A 08–15 và B 08–15:30, đơn Thường giờ trả 16:00."""
    n1 = make_wo(duration=420, arrival=at(8))
    n2 = make_wo(duration=450, arrival=at(8))
    _schedule(db, n1, planner)
    _schedule(db, n2, planner)
    return n1, n2


def test_block_moves_order_to_block_new_order_without_plan_version(db, planner, make_wo):
    _two_full_lines(db, planner, make_wo)
    active_before = active_version(db).id
    versions_before = len(db.scalars(select(PlanVersion)).all())
    late = make_wo(duration=180, arrival=at(8), ret=at(16))  # Thường: không đẩy được ai, sớm nhất A 15–18
    with pytest.raises(NewOrderBlockedError) as e:
        _schedule(db, late, planner)
    risk = e.value.assessment
    assert (risk.level, risk.earliest_feasible_return) == (RiskLevel.BLOCK, at(18))
    assert risk.reasons[0] == "Không kịp giờ trả 16:00: xếp vào khe trống sớm nhất xong 18:00 (trễ 120 phút)."
    assert late.state == WorkOrderState.BLOCK_NEW_ORDER
    assert len(db.scalars(select(PlanVersion)).all()) == versions_before
    assert active_version(db).id == active_before
    check = db.scalars(select(RiskCheck).where(RiskCheck.work_order_id == late.id)).one()
    assert (check.level, check.plan_version_id, check.reasons) == (RiskLevel.BLOCK, active_before, list(risk.reasons))
    with pytest.raises(NotSchedulableError):  # đã bị chặn → không xếp lại được, chờ Quản lý override
        _schedule(db, late, planner)


def test_warn_bumps_lower_priority_and_waits_for_approval(db, planner, make_wo):
    n1, n2 = _two_full_lines(db, planner, make_wo)
    active_before = active_version(db).id
    vip = make_wo(duration=180, arrival=at(8), ret=at(12), priority=Priority.VIP)
    r = _schedule(db, vip, planner)
    assert r.risk.level == RiskLevel.WARN
    assert (r.placement.line, r.placement.start, r.placement.end) == (Line.A, at(8), at(11))
    assert r.plan_version.status == PlanVersionStatus.PENDING_APPROVAL and r.plan_version.requires_approval
    assert active_version(db).id == active_before  # BR-08: lịch ACTIVE không đổi
    assert (vip.state, n1.state, n2.state) == (
        WorkOrderState.PENDING_APPROVAL,
        WorkOrderState.SCHEDULED,  # đơn bị đẩy giữ trạng thái tới khi duyệt
        WorkOrderState.SCHEDULED,
    )
    changes = {
        c.work_order_id: c
        for c in db.scalars(select(PlanChange).where(PlanChange.plan_version_id == r.plan_version.id))
    }
    assert set(changes) == {vip.id, n1.id}
    assert (changes[vip.id].change_type, changes[vip.id].needs_approval) == (ChangeType.ACCEPT_DURING_WARNING, True)
    bump = changes[n1.id]
    assert (bump.change_type, bump.needs_approval) == (ChangeType.PRIORITY_OVERRIDE, True)
    assert bump.old_value == {"line": "A", "start": at(8).isoformat(), "end": at(15).isoformat()}
    assert (bump.new_value["start"], bump.new_value["end"], bump.new_value["sla_ok"]) == (
        at(11).isoformat(),
        at(18).isoformat(),
        False,
    )
    assert bump.new_value["reason"].startswith("Nhường Line A cho đơn ưu tiên cao hơn (priority override)")
    assert "Đẩy Bột ớt (Thường): Line A 08:00 → Line A 11:00–18:00, trễ giờ trả 16:00 120 phút." in r.risk.reasons
    rows = version_slots(db, r.plan_version.id)
    assert {(x.work_order_id, x.line, x.start_at) for x in rows} == {
        (vip.id, Line.A, at(8)),
        (n1.id, Line.A, at(11)),
        (n2.id, Line.B, at(8)),
    }


def test_risk_check_only_simulates(db, planner, make_wo):
    _two_full_lines(db, planner, make_wo)
    vip = make_wo(duration=180, arrival=at(8), ret=at(12), priority=Priority.VIP)
    versions_before = len(db.scalars(select(PlanVersion)).all())
    risk = check_new_order_risk(db, vip, now=at(8), tz=UTC, load_orders=_loader(db))
    assert risk.level == RiskLevel.WARN
    assert vip.state == WorkOrderState.FEASIBILITY_CHECK
    assert len(db.scalars(select(PlanVersion)).all()) == versions_before
    assert db.scalars(select(RiskCheck).where(RiskCheck.work_order_id == vip.id)).one().level == RiskLevel.WARN
    with pytest.raises(NotSchedulableError):
        check_new_order_risk(db, make_wo(state=WorkOrderState.SCHEDULED), now=at(8), tz=UTC, load_orders=_loader(db))


def test_only_feasibility_check_orders_can_be_scheduled(db, planner, make_wo):
    with pytest.raises(NotSchedulableError):
        _schedule(db, make_wo(state=WorkOrderState.DRAFT), planner)
    wo = make_wo()
    _schedule(db, wo, planner)
    with pytest.raises(NotSchedulableError):
        _schedule(db, wo, planner)


def test_missing_estimate_is_rejected(db, planner, make_wo):
    with pytest.raises(MissingEstimateError):
        _schedule(db, make_wo(duration=None), planner)
    assert db.scalars(select(PlanVersion)).first() is None


def test_stale_active_version_is_a_conflict(db, planner, make_wo, monkeypatch):
    """2 người xếp cùng lúc: người sau dựa trên version đã bị thay → 409, không ghi gì."""
    first = _schedule(db, make_wo(), planner)
    stale = first.plan_version
    _schedule(db, make_wo(), planner)  # người kia xếp xong trước → `stale` đã SUPERSEDED
    monkeypatch.setattr(planning, "active_version", lambda _db: stale)
    wo = make_wo()
    versions_before = len(db.scalars(select(PlanVersion)).all())
    with pytest.raises(PlanConflictError):
        _schedule(db, wo, planner)
    assert len(db.scalars(select(PlanVersion)).all()) == versions_before
    assert db.get(WorkOrder, wo.id).state == WorkOrderState.FEASIBILITY_CHECK


def test_audit_records_plan_version_and_state_change(db, planner, make_wo):
    wo = make_wo()
    r = _schedule(db, wo, planner)
    actions = [(a.action, a.actor_id) for a in db.scalars(select(AuditLog).order_by(AuditLog.id))]
    assert actions == [("WORK_ORDER_STATE_CHANGED", planner.id), ("PLAN_VERSION_CREATED", planner.id)]
    created = db.scalars(select(AuditLog).where(AuditLog.action == "PLAN_VERSION_CREATED")).one()
    assert created.payload["plan_version"] == r.plan_version.id


def test_20_random_orders_no_overlap_in_any_version_and_fast(db, planner, make_wo):
    rng = random.Random(7)
    for _ in range(20):
        arrival = at(6) + timedelta(minutes=15 * rng.randint(0, 40))
        wo = make_wo(duration=15 * rng.randint(2, 16), arrival=arrival, ret=arrival + timedelta(hours=8))
        started = time.perf_counter()
        try:
            _schedule(db, wo, planner, now=at(6))
        except NewOrderBlockedError:
            assert wo.state == WorkOrderState.BLOCK_NEW_ORDER
        assert time.perf_counter() - started < 5  # ticket → lịch < 5 giây
    versions = db.scalars(select(PlanVersion)).all()
    assert sum(v.status == PlanVersionStatus.ACTIVE for v in versions) == 1  # BR-09
    for v in versions:
        rows = version_slots(db, v.id)
        assert not has_overlap([Slot(r.work_order_id, r.line, r.start_at, r.end_at) for r in rows])  # BR-04


def test_pending_proposals_reserve_their_slot(db, planner, make_wo):
    """Đề xuất WARN đang chờ duyệt giữ chỗ: đơn sau không được xếp chồng lên slot đề xuất."""
    _two_full_lines(db, planner, make_wo)
    warn = _schedule(db, make_wo(duration=180, arrival=at(8), ret=at(12), priority=Priority.VIP), planner)
    assert warn.plan_version.status == PlanVersionStatus.PENDING_APPROVAL  # A 08–11 VIP, A 11–18 đơn bị đẩy
    third = _schedule(db, make_wo(duration=60, arrival=at(8), ret=at(23)), planner)  # A bận tới 18 → B 15:30
    assert (third.placement.line, third.placement.start) == (Line.B, at(15, 30))
    assert third.risk.level == RiskLevel.OK
    assert len(version_slots(db, third.plan_version.id)) == 3  # đề xuất chưa duyệt không vào lịch ACTIVE
