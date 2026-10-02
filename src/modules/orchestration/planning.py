"""Xếp lịch 1 work order thành plan version mới — ADC-003 (T-028), ADC-005 (T-036), ADC-006, ADR-0004/0005.

Orchestrator chạy kiểm tra rủi ro đơn mới (BR-07, `assess_new_order`) rồi ghi kết quả + 1 dòng `risk_checks`:
- OK → LINE_ASSIGNMENT, version mới = slot ACTIVE + slot mới, ACTIVE ngay, version cũ SUPERSEDED, đơn → SCHEDULED.
- WARN (kịp nhờ đẩy lùi đơn ưu tiên thấp hơn) → ACCEPT_DURING_WARNING cho đơn mới + PRIORITY_OVERRIDE cho đơn bị
  đẩy, version PENDING_APPROVAL, lịch ACTIVE giữ nguyên, đơn mới → PENDING_APPROVAL; đơn bị đẩy giữ trạng thái tới
  khi duyệt (T-042). BR-08. Đơn bị đẩy mà trễ giờ trả → escalation ngay (T-037).
- BLOCK → không tạo version, đơn → BLOCK_NEW_ORDER, NewOrderBlockedError. Quản lý override: T-040/T-042.
Slot đề xuất trong các version đang chờ duyệt được coi là đã giữ chỗ khi tìm khe (không chép vào version mới)
→ các đề xuất chờ duyệt không giành cùng một khung giờ; T-042 gộp slot đó vào lịch ACTIVE khi duyệt.
Khóa lạc quan: version ACTIVE bị đổi bởi request khác trong lúc xếp → PlanConflictError, không ghi gì.
Khung dừng của sự cố chưa kết thúc (ADC-004) coi như slot bận → không xếp đơn mới vào line đang dừng.
Xếp / sửa tay (BR-15, `place_work_order_manually`): Điều phối chọn line + giờ; kịp giờ trả → LINE_ASSIGNMENT ACTIVE
ngay, trễ → RETURN_TIME_CHANGE chờ duyệt (lịch ACTIVE giữ nguyên). Trùng slot → SlotConflictError, không ghi gì.
Đơn RESCHEDULE_REQUIRED (phương án bị từ chối, T-040) xếp tay lại như đơn FEASIBILITY_CHECK.
"""

import math
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, tzinfo
from typing import Protocol

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from src.modules.orchestration.approval import APPROVAL_REQUIRED, ChangeType, initial_plan_status
from src.modules.orchestration.audit import AuditAction, record
from src.modules.orchestration.escalations import raise_escalation
from src.modules.orchestration.history import ActorType
from src.modules.orchestration.plan_versions import PlanChange, PlanTrigger, PlanVersion
from src.modules.orchestration.state_machine import PlanVersionStatus, WorkOrderState
from src.modules.orchestration.transitions import transition_work_order
from src.modules.risk import RiskAssessment, RiskCheck, RiskLevel, assess_new_order
from src.modules.scheduling import (
    Incident,
    ManualPlacement,
    Move,
    Placement,
    RescheduleCandidate,
    ShiftPolicy,
    Slot,
    downtime_slot,
    has_overlap,
    manual_placement,
    placement_reason,
)
from src.modules.scheduling.incident import DOWNTIME_ID
from src.modules.scheduling.models import LineIncident, ScheduleSlot
from src.modules.types import Line, Priority


class Schedulable(Protocol):
    id: str
    state: WorkOrderState
    estimated_duration_min: int | None
    expected_arrival: datetime | None
    requested_return: datetime | None
    priority: Priority | None


class Reschedulable(Protocol):
    id: str
    state: WorkOrderState
    priority: Priority | None
    expected_arrival: datetime | None
    requested_return: datetime | None
    product_name: str | None


# id đơn → work order; Orchestration không import model của Intake (tránh phụ thuộc vòng) nên API truyền vào
OrderLoader = Callable[[Iterable[str]], Mapping[str, Reschedulable]]


class NotSchedulableError(Exception):
    """Đơn không ở trạng thái xếp được (409)."""


class MissingEstimateError(Exception):
    """Chưa có thời lượng ước tính / giờ trả (422)."""


class PlanConflictError(Exception):
    """Version ACTIVE đã đổi trong lúc xếp (409)."""


class NewOrderBlockedError(Exception):
    """Rủi ro BLOCK (BR-07): đơn mới không kịp giờ trả dù xếp sớm nhất → BLOCK_NEW_ORDER (409)."""

    def __init__(self, assessment: RiskAssessment):
        super().__init__(assessment.reasons[0])
        self.assessment = assessment


@dataclass(frozen=True)
class ManualScheduleResult:
    placement: ManualPlacement
    plan_version: PlanVersion


@dataclass(frozen=True)
class ScheduleResult:
    placement: Placement
    plan_version: PlanVersion
    reason: str
    risk: RiskAssessment


def active_version(db: Session) -> PlanVersion | None:
    return db.scalars(select(PlanVersion).where(PlanVersion.status == PlanVersionStatus.ACTIVE)).first()


def version_slots(db: Session, version_id: int) -> list[ScheduleSlot]:
    return list(
        db.scalars(
            select(ScheduleSlot)
            .where(ScheduleSlot.plan_version_id == version_id)
            .order_by(ScheduleSlot.line, ScheduleSlot.start_at, ScheduleSlot.work_order_id)
        )
    )


def ancestor_ids(db: Session, version_id: int) -> list[int]:
    """Version và các version cha, mới → cũ."""
    out: list[int] = []
    current: int | None = version_id
    while current is not None:
        out.append(current)
        current = db.scalar(select(PlanVersion.parent_version_id).where(PlanVersion.id == current))
    return out


def slot_details(db: Session, version_id: int) -> dict[str, dict]:
    """work_order_id → new_value của lần gán line gần nhất trên nhánh version này ({line, start, end, sla_ok, reason})."""
    changes = db.scalars(
        select(PlanChange)
        .where(PlanChange.plan_version_id.in_(ancestor_ids(db, version_id)))
        .order_by(PlanChange.plan_version_id, PlanChange.id)
    )
    return {c.work_order_id: c.new_value for c in changes}  # version mới hơn ghi đè


def reserved_slots(db: Session) -> list[ScheduleSlot]:
    """Slot đề xuất (đơn có thay đổi) của các version PENDING_APPROVAL — xếp lịch mới hay phương án sự cố.

    Phương án sự cố có cả thay đổi không cần duyệt (sang line còn lại) → lấy mọi dòng thay đổi, không chỉ
    `needs_approval`; version xếp lịch mới chỉ có 1 dòng thay đổi nên không đổi so với T-028.
    """
    return list(
        db.scalars(
            select(ScheduleSlot)
            .join(PlanVersion, PlanVersion.id == ScheduleSlot.plan_version_id)
            .join(
                PlanChange,
                (PlanChange.plan_version_id == ScheduleSlot.plan_version_id)
                & (PlanChange.work_order_id == ScheduleSlot.work_order_id),
            )
            .where(PlanVersion.status == PlanVersionStatus.PENDING_APPROVAL)
        )
    )


def downtime(incident: LineIncident) -> Incident:
    """Khung dừng hiện hành của sự cố: [start_at, giờ hồi phục thực tế hoặc dự kiến)."""
    minutes = math.ceil((incident.end_at - incident.start_at) / timedelta(minutes=1))  # lẻ giây → tròn lên
    return Incident(line=incident.line, start_at=incident.start_at, est_downtime_min=max(minutes, 0))


def current_downtimes(db: Session, now: datetime) -> list[Incident]:
    """Khung dừng của mọi sự cố chưa kết thúc (kể cả đã RESOLVED nhưng giờ hồi phục còn ở tương lai)."""
    return [d for d in map(downtime, db.scalars(select(LineIncident).order_by(LineIncident.id))) if d.end_at > now]


def _to_slots(rows: Sequence[ScheduleSlot]) -> list[Slot]:
    return [Slot(r.work_order_id, r.line, r.start_at, r.end_at) for r in rows]


def _require_estimate(wo: Schedulable, allowed: frozenset[WorkOrderState]) -> None:
    if WorkOrderState(wo.state) not in allowed:
        names = ", ".join(sorted(allowed))
        raise NotSchedulableError(f"Chỉ xếp lịch / kiểm tra rủi ro được lệnh {names} (hiện {wo.state})")
    if not wo.estimated_duration_min or wo.requested_return is None:
        raise MissingEstimateError("Lệnh chưa có thời lượng ước tính hoặc giờ trả")


@dataclass(frozen=True)
class _Simulation:
    risk: RiskAssessment
    base: PlanVersion | None
    base_rows: list[ScheduleSlot]


def _simulate(
    db: Session, wo: Schedulable, *, now: datetime, tz: tzinfo, shifts: ShiftPolicy | None, load_orders: OrderLoader
) -> _Simulation:
    """Mô phỏng chèn đơn vào lịch hiện hành (BR-07) — không ghi gì."""
    base = active_version(db)
    base_rows = version_slots(db, base.id) if base else []
    pending_rows = reserved_slots(db)
    reserved = {r.work_order_id for r in pending_rows}
    orders = load_orders({r.work_order_id for r in base_rows})
    # Chỉ đơn đã có lịch ACTIVE mà chưa vào luồng vận hành, chưa có đề xuất chờ duyệt mới được đẩy lùi
    bumpable = [
        RescheduleCandidate(
            work_order_id=r.work_order_id,
            priority=o.priority or Priority.NORMAL,
            requested_return=o.requested_return or r.end_at,
            old=Slot(r.work_order_id, r.line, r.start_at, r.end_at),
            expected_arrival=o.expected_arrival,
        )
        for r in base_rows
        if r.work_order_id not in reserved
        and WorkOrderState((o := orders[r.work_order_id]).state) == WorkOrderState.SCHEDULED
    ]
    risk = assess_new_order(
        work_order_id=wo.id,
        duration_min=wo.estimated_duration_min,
        priority=wo.priority,
        requested_return=wo.requested_return,
        expected_arrival=wo.expected_arrival,
        now=now,
        busy=[*_to_slots([*base_rows, *pending_rows]), *map(downtime_slot, current_downtimes(db, now))],
        bumpable=bumpable,
        shifts=shifts,
        tz=tz,
        labels={w: o.product_name or w for w, o in orders.items()},
    )
    return _Simulation(risk, base, base_rows)


def _risk_row(wo: Schedulable, sim: _Simulation, now: datetime) -> RiskCheck:
    return RiskCheck(
        work_order_id=wo.id,
        plan_version_id=sim.base.id if sim.base else None,
        level=sim.risk.level,
        reasons=list(sim.risk.reasons),
        created_at=now,
    )


def check_new_order_risk(
    db: Session,
    wo: Schedulable,
    *,
    now: datetime,
    tz: tzinfo,
    load_orders: OrderLoader,
    shifts: ShiftPolicy | None = None,
) -> RiskAssessment:
    """POST /risk-check: chỉ mô phỏng + lưu `risk_checks`, không đổi lịch hay trạng thái đơn."""
    _require_estimate(wo, frozenset({WorkOrderState.FEASIBILITY_CHECK, WorkOrderState.BLOCK_NEW_ORDER}))
    sim = _simulate(db, wo, now=now, tz=tz, shifts=shifts, load_orders=load_orders)
    db.add(_risk_row(wo, sim, now))
    db.commit()
    return sim.risk


def _span(s: Slot) -> dict:
    return {"line": s.line.value, "start": s.start.isoformat(), "end": s.end.isoformat()}


def _bump_reason(m: Move, tz: tzinfo) -> str:
    return (
        f"Nhường Line {m.old.line.value} cho đơn ưu tiên cao hơn (priority override) → "
        f"{placement_reason(m.placement, tz)}"
    )


def supersede_active(db: Session, base: PlanVersion | None) -> None:
    """Version mới ACTIVE → version cũ SUPERSEDED (BR-09). Cập nhật có điều kiện = khóa lạc quan theo plan version."""
    if base is not None:
        done = db.execute(
            update(PlanVersion)
            .where(PlanVersion.id == base.id, PlanVersion.status == PlanVersionStatus.ACTIVE)
            .values(status=PlanVersionStatus.SUPERSEDED)
        )
        if done.rowcount != 1:
            db.rollback()
            raise PlanConflictError("Lịch đã được người khác cập nhật, tải lại rồi xếp lại")
    db.flush()
    active = db.scalar(select(func.count()).where(PlanVersion.status == PlanVersionStatus.ACTIVE))
    if active != 1:
        db.rollback()
        raise PlanConflictError("Lịch đã được người khác cập nhật, tải lại rồi xếp lại")


def schedule_work_order(
    db: Session,
    wo: Schedulable,
    *,
    actor_id: str,
    now: datetime,
    tz: tzinfo,
    load_orders: OrderLoader,
    shifts: ShiftPolicy | None = None,
    actor_type: ActorType = ActorType.USER,
) -> ScheduleResult:
    """`actor_type=SYSTEM` khi hệ thống tự xếp lúc tạo ticket (`actor_id` = người tạo ticket)."""
    _require_estimate(wo, frozenset({WorkOrderState.FEASIBILITY_CHECK}))
    sim = _simulate(db, wo, now=now, tz=tz, shifts=shifts, load_orders=load_orders)
    risk, base, base_rows = sim.risk, sim.base, sim.base_rows
    db.add(_risk_row(wo, sim, now))
    if risk.level == RiskLevel.BLOCK:
        reason = " ".join(risk.reasons)
        transition_work_order(
            db, wo, WorkOrderState.BLOCK_NEW_ORDER, actor_id=actor_id, reason=reason, now=now, actor_type=actor_type
        )
        raise NewOrderBlockedError(risk)

    placement = risk.placement
    reason = placement_reason(placement, tz)
    change_type = ChangeType.ACCEPT_DURING_WARNING if risk.level == RiskLevel.WARN else ChangeType.LINE_ASSIGNMENT
    status = initial_plan_status([change_type, *(ChangeType.PRIORITY_OVERRIDE for _ in risk.moves)])
    needs_approval = status == PlanVersionStatus.PENDING_APPROVAL

    version = PlanVersion(
        parent_version_id=base.id if base else None,
        trigger=PlanTrigger.NEW_ORDER,
        status=status,
        requires_approval=needs_approval,
        created_by=actor_id,
        created_at=now,
    )
    db.add(version)
    db.flush()

    moved = {m.candidate.work_order_id: m for m in risk.moves}
    new_slots = [
        *(_to_slots([r for r in base_rows if r.work_order_id not in moved])),
        *(m.new for m in risk.moves),
        Slot(wo.id, placement.line, placement.start, placement.end),
    ]
    if has_overlap(new_slots):  # BR-04 — không bao giờ xảy ra nếu scheduler đúng
        db.rollback()
        raise RuntimeError("plan version mới có slot chồng lấn")
    db.add_all(
        ScheduleSlot(
            plan_version_id=version.id, work_order_id=s.work_order_id, line=s.line, start_at=s.start, end_at=s.end
        )
        for s in new_slots
    )
    db.add(
        PlanChange(
            plan_version_id=version.id,
            work_order_id=wo.id,
            change_type=change_type,
            old_value=None,
            new_value={**_span(new_slots[-1]), "sla_ok": placement.sla_ok, "reason": reason},
            needs_approval=change_type in APPROVAL_REQUIRED,
        )
    )
    for m in risk.moves:
        db.add(
            PlanChange(
                plan_version_id=version.id,
                work_order_id=m.candidate.work_order_id,
                change_type=ChangeType.PRIORITY_OVERRIDE,
                old_value=_span(m.old),
                new_value={**_span(m.new), "sla_ok": m.sla_ok, "reason": _bump_reason(m, tz)},
                needs_approval=True,
            )
        )

    if status == PlanVersionStatus.ACTIVE:
        supersede_active(db, base)

    target = WorkOrderState.SCHEDULED if status == PlanVersionStatus.ACTIVE else WorkOrderState.PENDING_APPROVAL
    transition_work_order(
        db, wo, target, actor_id=actor_id, reason=reason, now=now, actor_type=actor_type, plan_version_id=version.id
    )  # commit
    record(
        db,
        actor_id,
        AuditAction.PLAN_VERSION_CREATED,
        {
            "plan_version": version.id,
            "parent_version_id": version.parent_version_id,
            "status": status.value,
            "work_order_id": wo.id,
            "change_type": change_type.value,
            "risk_level": risk.level.value,
            "line": placement.line.value,
            "start": placement.start.isoformat(),
            "end": placement.end.isoformat(),
            "sla_ok": placement.sla_ok,
            "bumped": [{"work_order_id": w, **_span(m.new), "sla_ok": m.sla_ok} for w, m in moved.items()],
        },
        now=now,
    )
    late = [m for m in risk.moves if not m.sla_ok]
    bumped_orders = load_orders([m.candidate.work_order_id for m in late]) if late else {}
    for m in late:  # đơn bị đẩy trễ giờ trả → kinh doanh biết ngay khi phương án còn chờ duyệt (T-037)
        raise_escalation(
            db,
            bumped_orders[m.candidate.work_order_id],
            delay_min=math.ceil((m.new.end - m.candidate.requested_return) / timedelta(minutes=1)),
            incident_id=None,
            actor_id=actor_id,
            now=now,
            reason=_bump_reason(m, tz),
        )
    return ScheduleResult(placement=placement, plan_version=version, reason=reason, risk=risk)


MANUAL_STATES = frozenset(
    {
        WorkOrderState.FEASIBILITY_CHECK,
        WorkOrderState.RESCHEDULE_REQUIRED,
        WorkOrderState.SCHEDULED,
        WorkOrderState.WAITING_ARRIVAL,
    }
)
# Đơn chưa có lịch được duyệt: xếp tay xong mới chuyển trạng thái (RESCHEDULE_REQUIRED = phương án bị từ chối, T-040)
UNSCHEDULED_STATES = frozenset({WorkOrderState.FEASIBILITY_CHECK, WorkOrderState.RESCHEDULE_REQUIRED})


def place_work_order_manually(
    db: Session,
    wo: Schedulable,
    *,
    line: Line,
    start: datetime,
    actor_id: str,
    now: datetime,
    tz: tzinfo,
    load_orders: OrderLoader,
    shifts: ShiftPolicy | None = None,
) -> ManualScheduleResult:
    """Điều phối xếp / sửa lịch 1 đơn chưa chạy vào line + giờ đã chọn (BR-15) → plan version `MANUAL`."""
    _require_estimate(wo, MANUAL_STATES)
    pending_rows = reserved_slots(db)
    if any(r.work_order_id == wo.id for r in pending_rows):
        raise NotSchedulableError("Lệnh đang có phương án chờ duyệt — duyệt / từ chối trước khi sửa lịch")
    base = active_version(db)
    base_rows = version_slots(db, base.id) if base else []
    old = next((r for r in base_rows if r.work_order_id == wo.id), None)
    if old is None and WorkOrderState(wo.state) not in UNSCHEDULED_STATES:
        raise NotSchedulableError("Lệnh không có trong lịch đang áp dụng")

    others = [r for r in [*base_rows, *pending_rows] if r.work_order_id != wo.id]
    labels = {w: o.product_name or w for w, o in load_orders({r.work_order_id for r in others}).items()}
    labels[DOWNTIME_ID] = "khung dừng sự cố"
    placement = manual_placement(
        work_order_id=wo.id,
        line=line,
        start=start,
        duration_min=wo.estimated_duration_min,
        expected_arrival=wo.expected_arrival,
        requested_return=wo.requested_return,
        now=now,
        busy=[*_to_slots(others), *map(downtime_slot, current_downtimes(db, now))],
        priority=wo.priority,
        shifts=shifts,
        tz=tz,
        labels=labels,
    )
    change_type = ChangeType.LINE_ASSIGNMENT if placement.sla_ok else ChangeType.RETURN_TIME_CHANGE
    status = initial_plan_status([change_type])

    version = PlanVersion(
        parent_version_id=base.id if base else None,
        trigger=PlanTrigger.MANUAL,
        status=status,
        requires_approval=status == PlanVersionStatus.PENDING_APPROVAL,
        created_by=actor_id,
        created_at=now,
    )
    db.add(version)
    db.flush()
    new_slots = [*_to_slots([r for r in base_rows if r.work_order_id != wo.id]), placement.slot]
    if has_overlap(new_slots):  # BR-04 — manual_placement đã chặn trùng
        db.rollback()
        raise RuntimeError("plan version mới có slot chồng lấn")
    db.add_all(
        ScheduleSlot(
            plan_version_id=version.id, work_order_id=s.work_order_id, line=s.line, start_at=s.start, end_at=s.end
        )
        for s in new_slots
    )
    old_span = _span(Slot(wo.id, old.line, old.start_at, old.end_at)) if old else None
    db.add(
        PlanChange(
            plan_version_id=version.id,
            work_order_id=wo.id,
            change_type=change_type,
            old_value=old_span,
            new_value={**_span(placement.slot), "sla_ok": placement.sla_ok, "reason": placement.reason},
            needs_approval=change_type in APPROVAL_REQUIRED,
        )
    )
    if status == PlanVersionStatus.ACTIVE:
        supersede_active(db, base)

    if WorkOrderState(wo.state) in UNSCHEDULED_STATES:
        target = WorkOrderState.SCHEDULED if status == PlanVersionStatus.ACTIVE else WorkOrderState.PENDING_APPROVAL
        transition_work_order(
            db, wo, target, actor_id=actor_id, reason=placement.reason, now=now, plan_version_id=version.id
        )  # commit
    else:
        db.commit()  # đơn đã có lịch giữ trạng thái; đề xuất trễ chờ duyệt (T-042)
    record(
        db,
        actor_id,
        AuditAction.PLAN_VERSION_CREATED,
        {
            "plan_version": version.id,
            "parent_version_id": version.parent_version_id,
            "status": status.value,
            "trigger": PlanTrigger.MANUAL.value,
            "work_order_id": wo.id,
            "change_type": change_type.value,
            "old": old_span,
            **_span(placement.slot),
            "sla_ok": placement.sla_ok,
        },
        now=now,
    )
    return ManualScheduleResult(placement=placement, plan_version=version)
