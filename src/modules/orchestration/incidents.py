"""Sự cố line — ADC-004, specs/api-contracts.md §4. Orchestrator điều phối, lõi tính ở src/modules/scheduling.

- Khai báo (T-031): ghi sự cố + audit người khai báo, thời điểm.
- Phát hiện đơn bị ảnh hưởng (T-032): slot của version ACTIVE và slot đề xuất đang chờ duyệt trên line sự cố
  chồng lấn khung dừng của mọi sự cố chưa kết thúc (`find_affected_slots`, FR 07). Đơn đã chiếu xong bỏ qua;
  đơn đang chiếu dở vẫn tính là bị ảnh hưởng (giả định: chạy lại từ đầu — chờ đối tác xác nhận).
- Tái lập lịch (T-033): `reschedule` deterministic → plan version mới trigger INCIDENT, luôn PENDING_APPROVAL
  (bước 10, BR-08) — lịch ACTIVE không đổi tới khi duyệt (T-042). Phương án sự cố đang chờ duyệt trước đó và đề xuất
  xếp lịch bị dời → SUPERSEDED (ADR-0005). Đơn SCHEDULED → LINE_INCIDENT; trễ giờ trả → SLA_RISK (BR-06).
  Đơn ở trạng thái vận hành được dời slot nhưng giữ trạng thái (không quay về luồng lịch — T-040).
- Escalation (T-037): mọi đơn trễ giờ trả trong phương án có escalation; SLA_RISK → ESCALATED_TO_BUSINESS.
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, tzinfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.modules.orchestration.approval import APPROVAL_REQUIRED, ChangeType
from src.modules.orchestration.audit import AuditAction, record
from src.modules.orchestration.escalations import raise_escalation
from src.modules.orchestration.history import ActorType
from src.modules.orchestration.plan_versions import PlanChange, PlanTrigger, PlanVersion
from src.modules.orchestration.planning import (
    OrderLoader,
    active_version,
    current_downtimes,
    reserved_slots,
    version_slots,
)
from src.modules.orchestration.state_machine import (
    PLAN_VERSION_TRANSITIONS,
    PlanVersionStatus,
    WorkOrderState,
    assert_transition,
)
from src.modules.orchestration.transitions import transition_work_order
from src.modules.scheduling import (
    Incident,
    Move,
    RescheduleCandidate,
    ShiftPolicy,
    Slot,
    compact,
    find_affected_slots,
    has_overlap,
    move_reason,
    reschedule,
)
from src.modules.scheduling.models import IncidentAffectedOrder, IncidentStatus, LineIncident, ScheduleSlot
from src.modules.types import Line, Priority

S = WorkOrderState

# Đã chiếu xong → slot là lịch sử, sự cố không ảnh hưởng nữa
IRRADIATED_STATES: frozenset[WorkOrderState] = frozenset(
    {S.COMPLETED_IRRADIATION, S.READY_FOR_RETURN, S.RETURNED, S.CLOSED}
)
# Đơn chưa bắt đầu được phép bị đẩy lùi (priority override) — chỉ khi chưa vào luồng vận hành
BUMPABLE_STATES: frozenset[WorkOrderState] = frozenset({S.SCHEDULED, S.LINE_INCIDENT})


class IncidentConflictError(Exception):
    """Trùng khung dừng với sự cố OPEN khác cùng line, hoặc sự cố đã RESOLVED (409)."""


class InvalidIncidentError(ValueError):
    """Dữ liệu sự cố không hợp lệ, vd giờ hồi phục trước giờ dừng (422)."""


@dataclass(frozen=True)
class AffectedSlot:
    row: ScheduleSlot  # slot cũ — của version ACTIVE hoặc của version đề xuất đang chờ duyệt
    state: WorkOrderState


def find_affected(
    rows: Sequence[ScheduleSlot], states: Mapping[str, WorkOrderState], downtimes: Sequence[Incident], now: datetime
) -> list[AffectedSlot]:
    """Slot chồng lấn ít nhất 1 khung dừng, theo giờ bắt đầu. Mỗi đơn chỉ có 1 slot trong `rows`."""
    by_order = {r.work_order_id: r for r in rows if states[r.work_order_id] not in IRRADIATED_STATES}
    slots = [_slot(r) for r in by_order.values()]
    hit = {s.work_order_id for d in downtimes for s in find_affected_slots(slots, d, now)}
    rows_hit = sorted((by_order[w] for w in hit), key=lambda r: (r.start_at, r.work_order_id))
    return [AffectedSlot(r, states[r.work_order_id]) for r in rows_hit]


def _slot(r: ScheduleSlot) -> Slot:
    return Slot(r.work_order_id, r.line, r.start_at, r.end_at)


def _overlapping_open(db: Session, line: Line, start: datetime, end: datetime) -> LineIncident | None:
    for other in db.scalars(
        select(LineIncident).where(LineIncident.line == line, LineIncident.status == IncidentStatus.OPEN)
    ):
        if other.start_at < end and start < other.end_at:
            return other
    return None


def declare_incident(
    db: Session,
    *,
    line: Line,
    start_at: datetime,
    est_downtime_min: int,
    note: str,
    actor_id: str,
    now: datetime,
    tz: tzinfo,
    load_orders: OrderLoader,
    shifts: ShiftPolicy | None = None,
) -> LineIncident:
    """Ghi sự cố (FR 06) rồi tính phương án phục hồi (FR 07–09)."""
    end = start_at + timedelta(minutes=est_downtime_min)
    if est_downtime_min > 0 and (other := _overlapping_open(db, line, start_at, end)) is not None:
        raise IncidentConflictError(f"Line {line.value} đã có sự cố #{other.id} đang mở trùng khung dừng")
    incident = LineIncident(
        line=line,
        start_at=start_at,
        est_downtime_min=est_downtime_min,
        note=note,
        status=IncidentStatus.OPEN,
        created_by=actor_id,
        created_at=now,
    )
    db.add(incident)
    db.flush()
    record(
        db,
        actor_id,
        AuditAction.INCIDENT_DECLARED,
        {
            "incident_id": incident.id,
            "line": line.value,
            "start_at": start_at.isoformat(),
            "est_downtime_min": est_downtime_min,
            "note": note,
        },
        now=now,
    )  # commit
    replan_incident(db, incident, actor_id=actor_id, now=now, tz=tz, load_orders=load_orders, shifts=shifts)
    return incident


def resolve_incident(
    db: Session,
    incident: LineIncident,
    *,
    actual_end: datetime,
    actor_id: str,
    now: datetime,
    tz: tzinfo,
    load_orders: OrderLoader,
    shifts: ShiftPolicy | None = None,
) -> PlanVersion | None:
    """Line hồi phục lúc `actual_end`. Khác giờ dự kiến → tính lại phương án theo khung dừng thực tế."""
    if incident.status == IncidentStatus.RESOLVED:
        raise IncidentConflictError(f"Sự cố #{incident.id} đã đóng")
    if actual_end < incident.start_at:
        raise InvalidIncidentError("Giờ hồi phục phải sau giờ bắt đầu dừng")
    planned_end = incident.end_at
    incident.actual_end_at = actual_end
    incident.status = IncidentStatus.RESOLVED
    record(
        db,
        actor_id,
        AuditAction.INCIDENT_RESOLVED,
        {"incident_id": incident.id, "actual_end": actual_end.isoformat(), "planned_end": planned_end.isoformat()},
        now=now,
    )  # commit
    if actual_end == planned_end:
        return None
    return replan_incident(db, incident, actor_id=actor_id, now=now, tz=tz, load_orders=load_orders, shifts=shifts)


def _supersede(v: PlanVersion) -> None:
    assert_transition(PLAN_VERSION_TRANSITIONS, v.status, PlanVersionStatus.SUPERSEDED)
    v.status = PlanVersionStatus.SUPERSEDED


def _change_type(m: Move) -> ChangeType:
    if m.bumped:
        return ChangeType.PRIORITY_OVERRIDE
    if m.new.end > m.old.end:
        return ChangeType.INCIDENT_DELAY
    return ChangeType.LINE_ASSIGNMENT


def late_minutes(m: Move) -> int:
    """Số phút trễ giờ trả của đơn sau khi dời (lẻ giây → tròn lên)."""
    return math.ceil((m.new.end - m.candidate.requested_return) / timedelta(minutes=1))


def _span(s: Slot) -> dict:
    return {"line": s.line.value, "start": s.start.isoformat(), "end": s.end.isoformat()}


def replan_incident(
    db: Session,
    incident: LineIncident,
    *,
    actor_id: str,
    now: datetime,
    tz: tzinfo,
    load_orders: OrderLoader,
    shifts: ShiftPolicy | None = None,
) -> PlanVersion | None:
    """Bước 2–10 cho mọi khung dừng chưa kết thúc. Không có đơn bị ảnh hưởng → không tạo version (None)."""
    for v in db.scalars(
        select(PlanVersion).where(
            PlanVersion.status == PlanVersionStatus.PENDING_APPROVAL, PlanVersion.trigger == PlanTrigger.INCIDENT
        )
    ):
        _supersede(v)
    db.flush()

    base = active_version(db)
    base_rows = version_slots(db, base.id) if base else []
    pending_rows = reserved_slots(db)  # đề xuất xếp lịch mới còn chờ duyệt
    rows = [*base_rows, *pending_rows]
    orders = load_orders({r.work_order_id for r in rows})
    states = {r.work_order_id: WorkOrderState(orders[r.work_order_id].state) for r in rows}
    downtimes = current_downtimes(db, now)
    hits = find_affected(rows, states, downtimes, now)
    if not hits:
        db.commit()
        return None

    def candidate(r: ScheduleSlot) -> RescheduleCandidate:
        wo = orders[r.work_order_id]
        return RescheduleCandidate(
            work_order_id=wo.id,
            priority=wo.priority or Priority.NORMAL,
            requested_return=wo.requested_return or r.end_at,
            old=_slot(r),
            expected_arrival=wo.expected_arrival,
        )

    hit_ids = {a.row.work_order_id for a in hits}
    bumpable = [
        candidate(r) for r in base_rows if r.work_order_id not in hit_ids and states[r.work_order_id] in BUMPABLE_STATES
    ]
    moves = reschedule(
        affected=[candidate(a.row) for a in hits],
        fixed=[_slot(r) for r in rows if r.work_order_id not in hit_ids],
        downtimes=downtimes,
        now=now,
        bumpable=bumpable,
        shifts=shifts,
    )
    # Dồn trái (ADR-0011): đơn chưa bắt đầu, không có đề xuất chờ duyệt → được kéo sớm lấp khe trống
    reserved_ids = {r.work_order_id for r in pending_rows}
    movable = [c for c in bumpable if c.work_order_id not in reserved_ids]
    movable_ids = {c.work_order_id for c in movable}
    moves = compact(
        moves=moves,
        movable=movable,
        fixed=[_slot(r) for r in rows if r.work_order_id not in hit_ids and r.work_order_id not in movable_ids],
        downtimes=downtimes,
        now=now,
        shifts=shifts,
    )
    moved = {m.candidate.work_order_id: m for m in moves}
    old_rows = {r.work_order_id: r for r in rows if r.work_order_id in moved}

    version = PlanVersion(
        parent_version_id=base.id if base else None,
        trigger=PlanTrigger.INCIDENT,
        status=PlanVersionStatus.PENDING_APPROVAL,
        requires_approval=True,
        incident_id=incident.id,
        created_by=actor_id,
        created_at=now,
    )
    db.add(version)
    db.flush()
    new_rows = [
        ScheduleSlot(
            plan_version_id=version.id, work_order_id=r.work_order_id, line=r.line, start_at=r.start_at, end_at=r.end_at
        )
        for r in base_rows
        if r.work_order_id not in moved
    ]
    new_by_order: dict[str, ScheduleSlot] = {}
    for m in moves:
        row = ScheduleSlot(
            plan_version_id=version.id,
            work_order_id=m.new.work_order_id,
            line=m.new.line,
            start_at=m.new.start,
            end_at=m.new.end,
        )
        new_rows.append(row)
        new_by_order[m.new.work_order_id] = row
    if has_overlap([_slot(r) for r in new_rows]):  # BR-04 — không bao giờ xảy ra nếu reschedule đúng
        db.rollback()
        raise RuntimeError("phương án sự cố có slot chồng lấn")
    db.add_all(new_rows)
    db.flush()

    reasons: dict[str, str] = {}
    for m in moves:
        wid = m.candidate.work_order_id
        change_type = _change_type(m)
        reasons[wid] = move_reason(m, tz)
        db.add(
            PlanChange(
                plan_version_id=version.id,
                work_order_id=wid,
                change_type=change_type,
                old_value=_span(m.old),
                new_value={**_span(m.new), "sla_ok": m.sla_ok, "reason": reasons[wid]},
                needs_approval=change_type in APPROVAL_REQUIRED,
            )
        )
        db.add(
            IncidentAffectedOrder(
                incident_id=incident.id,
                work_order_id=wid,
                old_slot_id=old_rows[wid].id,
                new_slot_id=new_by_order[wid].id,
                outcome=m.outcome,
            )
        )
    for r in pending_rows:  # đề xuất xếp lịch bị dời → gộp vào phương án sự cố
        if (
            r.work_order_id in moved
            and (v := db.get(PlanVersion, r.plan_version_id)).status != PlanVersionStatus.SUPERSEDED
        ):
            _supersede(v)
    db.commit()

    by_system = {"actor_type": ActorType.SYSTEM, "plan_version_id": version.id}
    for m in moves:
        wo = orders[m.candidate.work_order_id]
        reason = reasons[wo.id]
        if m.pulled:  # không bị ảnh hưởng, chỉ xong sớm hơn → giữ trạng thái
            continue
        if WorkOrderState(wo.state) == S.SCHEDULED:
            transition_work_order(db, wo, S.LINE_INCIDENT, actor_id=actor_id, reason=reason, now=now, **by_system)
        if not m.sla_ok and WorkOrderState(wo.state) == S.LINE_INCIDENT:
            transition_work_order(db, wo, S.SLA_RISK, actor_id=actor_id, reason=reason, now=now, **by_system)
        if not m.sla_ok:  # BR-06 → escalation cho kinh doanh (T-037)
            raise_escalation(
                db,
                wo,
                delay_min=late_minutes(m),
                incident_id=incident.id,
                actor_id=actor_id,
                now=now,
                reason=reason,
            )
    record(
        db,
        actor_id,
        AuditAction.PLAN_VERSION_CREATED,
        {
            "plan_version": version.id,
            "parent_version_id": version.parent_version_id,
            "status": version.status.value,
            "trigger": PlanTrigger.INCIDENT.value,
            "incident_id": incident.id,
            "moves": [
                {"work_order_id": m.candidate.work_order_id, "change_type": _change_type(m).value, **_span(m.new)}
                for m in moves
            ],
            "sla_risks": [m.candidate.work_order_id for m in moves if not m.sla_ok],
        },
        now=now,
    )
    return version
