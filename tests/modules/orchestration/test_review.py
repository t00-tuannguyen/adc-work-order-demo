"""ADC-006 T-042 — duyệt / từ chối plan version (HITL), gộp vào lịch ACTIVE, khóa lạc quan; FR 12, BR-08/09."""

from datetime import UTC

import pytest
from sqlalchemy import select, update

from src.modules.orchestration import (
    AuditLog,
    PlanConflictError,
    PlanVersion,
    PlanVersionStateError,
    PlanVersionStatus,
    StateHistory,
    WorkOrderState,
    active_version,
    approve_plan_version,
    place_work_order_manually,
    plan_diff,
    reject_plan_version,
    version_slots,
)
from src.modules.scheduling import ScheduleSlot
from src.modules.types import Line, Priority
from tests.conftest import at
from tests.modules.orchestration.test_planning import (  # noqa: F401
    _loader,
    _schedule,
    _two_full_lines,
    make_wo,
    planner,
)

S = WorkOrderState


@pytest.fixture
def warn(db, planner, make_wo):  # noqa: F811
    """Lịch A 08–15 (n1), B 08–15:30 (n2); VIP trả 12:00 đẩy n1 → version WARN chờ duyệt."""
    n1, n2 = _two_full_lines(db, planner, make_wo)
    vip = make_wo(duration=180, arrival=at(8), ret=at(12), priority=Priority.VIP)
    r = _schedule(db, vip, planner)
    assert r.plan_version.status == PlanVersionStatus.PENDING_APPROVAL
    return r.plan_version, vip, n1, n2


def _approve(db, version_id, user, comment=""):
    return approve_plan_version(db, version_id, actor_id=user.id, comment=comment, now=at(9), load_orders=_loader(db))


def _reject(db, version_id, user, reason="khách không đồng ý"):
    return reject_plan_version(db, version_id, actor_id=user.id, reason=reason, now=at(9), load_orders=_loader(db))


def test_approve_activates_version_and_schedules_waiting_order(db, planner, warn):  # noqa: F811
    v, vip, n1, n2 = warn
    old_active = active_version(db)
    _approve(db, v.id, planner, "đã báo khách n1")
    db.refresh(old_active)
    assert active_version(db).id == v.id and old_active.status == PlanVersionStatus.SUPERSEDED
    assert (v.approved_by, v.approved_at, v.comment) == (planner.id, at(9), "đã báo khách n1")
    assert (vip.state, n1.state, n2.state) == (S.SCHEDULED, S.SCHEDULED, S.SCHEDULED)  # đơn bị đẩy giữ trạng thái
    assert {(r.work_order_id, r.line, r.start_at) for r in version_slots(db, v.id)} == {
        (vip.id, Line.A, at(8)),
        (n1.id, Line.A, at(11)),
        (n2.id, Line.B, at(8)),
    }
    h = db.scalars(select(StateHistory).where(StateHistory.work_order_id == vip.id)).all()[-1]
    assert (h.from_state, h.to_state, h.plan_version_id) == (S.PENDING_APPROVAL, S.SCHEDULED, v.id)
    assert h.reason == f"Duyệt plan version {v.id}: đã báo khách n1"
    log = db.scalars(select(AuditLog).where(AuditLog.action == "PLAN_VERSION_APPROVED")).one()
    assert log.payload["work_orders"] == sorted([vip.id, n1.id]) and log.payload["rebased"] is False


def test_reject_keeps_active_and_sends_order_back_to_planner(db, planner, warn):  # noqa: F811
    v, vip, n1, _ = warn
    active_before = active_version(db).id
    _reject(db, v.id, planner)
    assert active_version(db).id == active_before
    assert (v.status, v.comment, v.approved_by) == (PlanVersionStatus.REJECTED, "khách không đồng ý", planner.id)
    assert (vip.state, n1.state) == (S.RESCHEDULE_REQUIRED, S.SCHEDULED)
    log = db.scalars(select(AuditLog).where(AuditLog.action == "PLAN_VERSION_REJECTED")).one()
    assert log.payload["reschedule_required"] == [vip.id]


def test_reject_requires_reason(db, planner, warn):  # noqa: F811
    v = warn[0]
    with pytest.raises(ValueError):
        _reject(db, v.id, planner, reason="  ")
    assert v.status == PlanVersionStatus.PENDING_APPROVAL


@pytest.mark.parametrize("first", ["approve", "reject"])
def test_decided_version_cannot_be_decided_again(db, planner, warn, first):  # noqa: F811
    v = warn[0]
    (_approve if first == "approve" else _reject)(db, v.id, planner)
    with pytest.raises(PlanVersionStateError):
        _approve(db, v.id, planner)
    with pytest.raises(PlanVersionStateError):
        _reject(db, v.id, planner)


def test_concurrent_decision_loses_optimistic_lock(db, planner, warn):  # noqa: F811
    """Người khác vừa từ chối (object trong phiên này còn cũ) → người sau nhận lỗi, không đổi gì."""
    v, vip, *_ = warn
    db.execute(
        update(PlanVersion)
        .where(PlanVersion.id == v.id)
        .values(status=PlanVersionStatus.REJECTED)
        .execution_options(synchronize_session=False)
    )
    db.commit()
    assert v.status == PlanVersionStatus.PENDING_APPROVAL  # còn cũ
    with pytest.raises(PlanVersionStateError):
        _approve(db, v.id, planner)
    assert vip.state == S.PENDING_APPROVAL


def _late_manual(db, planner, wo, line, start):  # noqa: F811
    return place_work_order_manually(
        db, wo, line=line, start=start, actor_id=planner.id, now=at(7), tz=UTC, load_orders=_loader(db)
    ).plan_version


def test_second_pending_version_is_merged_onto_new_active(db, planner, make_wo):  # noqa: F811
    """2 đề xuất trễ giờ trả cùng gốc: duyệt cái 1 xong, cái 2 gộp vào lịch ACTIVE mới (không mất đơn của cái 1)."""
    a = make_wo(duration=120, arrival=at(8), ret=at(9))
    b = make_wo(duration=120, arrival=at(8), ret=at(9))
    va = _late_manual(db, planner, a, Line.A, at(8))  # 08–10, trễ
    vb = _late_manual(db, planner, b, Line.B, at(8))
    assert va.status == vb.status == PlanVersionStatus.PENDING_APPROVAL
    _approve(db, va.id, planner)
    diff = plan_diff(db, vb.id)
    assert diff.base_changed and diff.base_version_id == va.id
    _approve(db, vb.id, planner)
    assert active_version(db).id == vb.id and vb.parent_version_id == va.id
    assert {(r.work_order_id, r.line) for r in version_slots(db, vb.id)} == {(a.id, Line.A), (b.id, Line.B)}
    assert (a.state, b.state) == (S.SCHEDULED, S.SCHEDULED)


def test_merge_conflict_is_rejected_without_changes(db, planner, make_wo):  # noqa: F811
    a = make_wo(duration=120, arrival=at(8), ret=at(9))
    b = make_wo(duration=120, arrival=at(8), ret=at(16))
    va = _late_manual(db, planner, a, Line.A, at(8))
    _schedule(db, b, planner, now=at(7))  # B 08–10 ACTIVE (A 08–10 đang giữ chỗ)
    active = active_version(db)
    db.execute(update(ScheduleSlot).where(ScheduleSlot.plan_version_id == active.id).values(line=Line.A))  # giả lập
    db.commit()
    with pytest.raises(PlanConflictError):
        _approve(db, va.id, planner)
    db.expire_all()
    assert db.get(PlanVersion, va.id).status == PlanVersionStatus.PENDING_APPROVAL
    assert active_version(db).id == active.id
