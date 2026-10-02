"""Duyệt / từ chối plan version (HITL) và diff trước/sau — ADC-006 T-042, FR 12, BR-08/09, ADR-0005.

Chỉ con người gọi được (API kiểm tra quyền APPROVE_PLAN_VERSION); LLM không có đường gọi tới đây.
- Duyệt: version PENDING_APPROVAL → ACTIVE, version ACTIVE cũ → SUPERSEDED. Lịch ACTIVE đã đổi kể từ lúc đề xuất
  (vd duyệt đề xuất khác trước) → gộp: slot của các đơn có thay đổi trong version này đặt lên lịch ACTIVE hiện tại;
  chồng lấn → PlanConflictError (409), người duyệt từ chối rồi xếp lại. Đơn PENDING_APPROVAL / LINE_INCIDENT /
  SLA_RISK / ESCALATED_TO_BUSINESS / RESCHEDULE_REQUIRED có thay đổi → SCHEDULED; đơn khác giữ trạng thái.
- Từ chối (bắt buộc lý do): version → REJECTED, lịch ACTIVE giữ nguyên; đơn có thay đổi đang chờ phương án này
  (PENDING_APPROVAL / LINE_INCIDENT / SLA_RISK / ESCALATED_TO_BUSINESS) → RESCHEDULE_REQUIRED cho Điều phối xếp lại.
- Khóa lạc quan: đổi trạng thái version bằng UPDATE có điều kiện status = PENDING_APPROVAL → người thứ hai nhận 409.
`approved_by` / `approved_at` / `comment` lưu người quyết định, thời điểm và ghi chú (duyệt) hoặc lý do (từ chối).
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from src.modules.orchestration.audit import AuditAction, record
from src.modules.orchestration.plan_versions import PlanChange, PlanVersion
from src.modules.orchestration.planning import (
    OrderLoader,
    PlanConflictError,
    active_version,
    supersede_active,
    version_slots,
)
from src.modules.orchestration.state_machine import PlanVersionStatus, WorkOrderState
from src.modules.orchestration.transitions import transition_work_order
from src.modules.scheduling import Slot, has_overlap
from src.modules.scheduling.models import ScheduleSlot

S = WorkOrderState

# Đơn đang chờ phương án → có lịch được duyệt
APPROVE_TO_SCHEDULED: frozenset[WorkOrderState] = frozenset(
    {S.PENDING_APPROVAL, S.LINE_INCIDENT, S.SLA_RISK, S.ESCALATED_TO_BUSINESS, S.RESCHEDULE_REQUIRED}
)
# Đơn mất phương án → Điều phối xếp lại (T-040)
REJECT_TO_RESCHEDULE: frozenset[WorkOrderState] = frozenset(
    {S.PENDING_APPROVAL, S.LINE_INCIDENT, S.SLA_RISK, S.ESCALATED_TO_BUSINESS}
)


class PlanVersionNotFoundError(LookupError):
    """Không có plan version (404)."""


class PlanVersionStateError(Exception):
    """Version không còn chờ duyệt — đã duyệt / từ chối / bị thay bằng version mới hơn (409)."""


@dataclass(frozen=True)
class ChangeDiff:
    change: PlanChange
    old: dict | None  # {line, start, end} trong lịch ACTIVE hiện tại (hoặc lúc đề xuất), None = đơn chưa có lịch
    new: dict  # {line, start, end, sla_ok, reason}


@dataclass(frozen=True)
class PlanDiff:
    version: PlanVersion
    base_version_id: int | None  # lịch ACTIVE hiện tại — "trước"
    base_changed: bool  # ACTIVE đã đổi kể từ lúc đề xuất → duyệt sẽ gộp
    changes: list[ChangeDiff]


def get_version(db: Session, version_id: int) -> PlanVersion:
    v = db.get(PlanVersion, version_id)
    if v is None:
        raise PlanVersionNotFoundError(f"Không có plan version {version_id}")
    return v


def _changes(db: Session, version_id: int) -> list[PlanChange]:
    return list(db.scalars(select(PlanChange).where(PlanChange.plan_version_id == version_id).order_by(PlanChange.id)))


def _span(r: ScheduleSlot) -> dict:
    return {"line": r.line.value, "start": r.start_at.isoformat(), "end": r.end_at.isoformat()}


def plan_diff(db: Session, version_id: int) -> PlanDiff:
    """Trước = slot của đơn trong lịch ACTIVE hiện tại (version chờ duyệt) hoặc lúc đề xuất (version đã xử lý)."""
    v = get_version(db, version_id)
    base = active_version(db)
    pending = v.status == PlanVersionStatus.PENDING_APPROVAL
    before_id = base.id if pending and base else v.parent_version_id
    before = {r.work_order_id: r for r in version_slots(db, before_id)} if before_id else {}
    changes = _changes(db, v.id)
    return PlanDiff(
        version=v,
        base_version_id=before_id,
        base_changed=pending and before_id != v.parent_version_id,
        changes=[
            ChangeDiff(
                change=c,
                old=_span(before[c.work_order_id]) if c.work_order_id in before else c.old_value,
                new=c.new_value,
            )
            for c in changes
        ],
    )


def _claim(db: Session, v: PlanVersion, to: PlanVersionStatus) -> None:
    """Khóa lạc quan: chỉ 1 người đổi được version đang PENDING_APPROVAL."""
    done = db.execute(
        update(PlanVersion)
        .where(PlanVersion.id == v.id, PlanVersion.status == PlanVersionStatus.PENDING_APPROVAL)
        .values(status=to)
    )
    if done.rowcount != 1:
        db.rollback()
        db.refresh(v)
        raise PlanVersionStateError(f"Plan version {v.id} đã {v.status} — tải lại danh sách chờ duyệt")


def _require_pending(v: PlanVersion) -> None:
    if v.status != PlanVersionStatus.PENDING_APPROVAL:
        if v.status == PlanVersionStatus.SUPERSEDED:
            raise PlanVersionStateError(f"Plan version {v.id} đã có version mới hơn thay thế")
        raise PlanVersionStateError(f"Plan version {v.id} không còn chờ duyệt (hiện {v.status})")


def approve_plan_version(
    db: Session, version_id: int, *, actor_id: str, comment: str, now: datetime, load_orders: OrderLoader
) -> PlanVersion:
    v = get_version(db, version_id)
    _require_pending(v)
    changes = _changes(db, v.id)
    changed = {c.work_order_id for c in changes}
    base = active_version(db)
    rebased = (base.id if base else None) != v.parent_version_id
    if rebased:
        proposed = [r for r in version_slots(db, v.id) if r.work_order_id in changed]
        kept = [r for r in (version_slots(db, base.id) if base else []) if r.work_order_id not in changed]
        merged = [Slot(r.work_order_id, r.line, r.start_at, r.end_at) for r in [*kept, *proposed]]
        if has_overlap(merged):
            raise PlanConflictError(
                f"Lịch đã đổi sau khi đề xuất plan version {v.id} — phương án trùng giờ với lịch hiện tại, "
                "hãy từ chối để Điều phối xếp lại"
            )

    _claim(db, v, PlanVersionStatus.ACTIVE)
    if rebased:
        db.execute(delete(ScheduleSlot).where(ScheduleSlot.plan_version_id == v.id))
        db.add_all(
            ScheduleSlot(
                plan_version_id=v.id, work_order_id=s.work_order_id, line=s.line, start_at=s.start, end_at=s.end
            )
            for s in merged
        )
        v.parent_version_id = base.id if base else None
    supersede_active(db, base)  # khóa lạc quan theo version ACTIVE (BR-09)
    v.approved_by, v.approved_at, v.comment = actor_id, now, comment or None
    db.commit()

    reason = f"Duyệt plan version {v.id}" + (f": {comment}" if comment else "")
    orders = load_orders(changed)
    for wid in sorted(changed):
        wo = orders[wid]
        if WorkOrderState(wo.state) in APPROVE_TO_SCHEDULED:
            transition_work_order(db, wo, S.SCHEDULED, actor_id=actor_id, reason=reason, now=now, plan_version_id=v.id)
    record(
        db,
        actor_id,
        AuditAction.PLAN_VERSION_APPROVED,
        {
            "plan_version": v.id,
            "parent_version_id": v.parent_version_id,
            "rebased": rebased,
            "comment": comment,
            "work_orders": sorted(changed),
        },
        now=now,
    )
    return v


def reject_plan_version(
    db: Session, version_id: int, *, actor_id: str, reason: str, now: datetime, load_orders: OrderLoader
) -> PlanVersion:
    if not reason.strip():
        raise ValueError("Từ chối phải ghi lý do")
    v = get_version(db, version_id)
    _require_pending(v)
    _claim(db, v, PlanVersionStatus.REJECTED)
    v.approved_by, v.approved_at, v.comment = actor_id, now, reason
    db.commit()

    changed = sorted({c.work_order_id for c in _changes(db, v.id)})
    orders = load_orders(changed)
    why = f"Từ chối plan version {v.id}: {reason}"
    moved = []
    for wid in changed:
        wo = orders[wid]
        if WorkOrderState(wo.state) in REJECT_TO_RESCHEDULE:
            transition_work_order(
                db, wo, S.RESCHEDULE_REQUIRED, actor_id=actor_id, reason=why, now=now, plan_version_id=v.id
            )
            moved.append(wid)
    record(
        db,
        actor_id,
        AuditAction.PLAN_VERSION_REJECTED,
        {"plan_version": v.id, "reason": reason, "work_orders": changed, "reschedule_required": moved},
        now=now,
    )
    return v
