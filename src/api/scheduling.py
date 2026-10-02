"""Lịch Line A / B, Kanban, chuyển trạng thái vận hành — ADC-003 (T-028), specs/api-contracts.md §3.

Xếp lịch: Điều phối (EDIT_SCHEDULE) — chạy kiểm tra rủi ro đơn mới trước (T-036); BLOCK → 409 có `risk`. Xem lịch / Kanban / plan version: mọi vai trò (VIEW_BOARD).
Chuyển trạng thái vận hành thủ công: Điều phối (CHANGE_OPERATIONAL_STATE).
"""

from collections.abc import Iterable
from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.agents.graph import get_shift_policy
from src.api.deps import require
from src.modules.identity import Action, User
from src.modules.intake import ReviewStatus, WorkOrder
from src.modules.orchestration import (
    OPERATIONAL_STATES,
    InvalidTransitionError,
    MissingEstimateError,
    NewOrderBlockedError,
    NotSchedulableError,
    OrderLoader,
    PlanConflictError,
    PlanTrigger,
    PlanVersion,
    PlanVersionStatus,
    WorkOrderState,
    active_version,
    place_work_order_manually,
    schedule_work_order,
    slot_details,
    transition_work_order,
    version_slots,
)
from src.modules.risk import RiskAssessment, RiskLevel
from src.modules.scheduling import ScheduleSlot, SlotConflictError, UnschedulableError
from src.modules.types import Line, Priority
from src.services.db import get_db, utcnow
from src.settings import Settings, get_settings

router = APIRouter(tags=["scheduling"])


class RiskCheckOut(BaseModel):
    level: RiskLevel
    reasons: list[str]
    earliest_feasible_return: datetime


def risk_out(r: RiskAssessment) -> RiskCheckOut:
    return RiskCheckOut(level=r.level, reasons=list(r.reasons), earliest_feasible_return=r.earliest_feasible_return)


class ScheduleOut(BaseModel):
    line: Line
    start: datetime
    end: datetime
    plan_version: int
    sla_ok: bool
    plan_status: PlanVersionStatus
    reason: str
    risk: RiskCheckOut


class ManualScheduleIn(BaseModel):
    line: Line
    start: datetime

    @field_validator("start")
    @classmethod
    def _aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("start phải có múi giờ (ISO 8601, vd 2026-10-02T09:00:00+07:00)")
        return v


class ManualScheduleOut(BaseModel):
    line: Line
    start: datetime
    end: datetime
    plan_version: int
    sla_ok: bool
    plan_status: PlanVersionStatus
    reason: str


class PlanVersionOut(BaseModel):
    id: int
    status: PlanVersionStatus
    parent_version_id: int | None
    trigger: PlanTrigger
    requires_approval: bool
    created_by: str
    created_at: datetime
    slot_count: int


class ScheduleSlotOut(BaseModel):
    work_order_id: str
    product_name: str | None
    priority: Priority | None
    state: WorkOrderState
    line: Line
    start: datetime
    end: datetime
    requested_return: datetime | None
    sla_ok: bool
    reason: str | None


class ScheduleViewOut(BaseModel):
    plan_version: PlanVersionOut | None
    date: date | None
    lines: dict[Line, list[ScheduleSlotOut]]


class CardSlotOut(BaseModel):
    line: Line
    start: datetime
    end: datetime
    sla_ok: bool
    plan_version: int
    plan_status: PlanVersionStatus


class WorkOrderCard(BaseModel):
    id: str
    product_name: str | None
    priority: Priority | None
    state: WorkOrderState
    review_status: ReviewStatus | None
    expected_arrival: datetime | None
    requested_return: datetime | None
    estimated_duration_min: int | None
    slot: CardSlotOut | None


class StateChange(BaseModel):
    to_state: WorkOrderState
    reason: str = Field(default="", max_length=500)


def get_work_order(db: Session, work_order_id: str) -> WorkOrder:
    wo = db.get(WorkOrder, work_order_id)
    if wo is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy lệnh")
    return wo


def order_loader(db: Session) -> OrderLoader:
    """Orchestration không import model Intake → API nạp work order theo id giúp nó."""

    def load(ids: Iterable[str]) -> dict[str, WorkOrder]:
        return {wo.id: wo for wo in db.scalars(select(WorkOrder).where(WorkOrder.id.in_(list(ids))))}

    return load


def version_out(db: Session, v: PlanVersion) -> PlanVersionOut:
    count = db.scalar(select(func.count()).where(ScheduleSlot.plan_version_id == v.id)) or 0
    return PlanVersionOut(
        id=v.id,
        status=v.status,
        parent_version_id=v.parent_version_id,
        trigger=v.trigger,
        requires_approval=v.requires_approval,
        created_by=v.created_by,
        created_at=v.created_at,
        slot_count=count,
    )


def _sla_ok(end: datetime, requested_return: datetime | None) -> bool:
    return requested_return is None or end <= requested_return


def card_slots(db: Session, work_order_ids: list[str]) -> dict[str, CardSlotOut]:
    """Slot của mỗi đơn trong version mới nhất đang ACTIVE / PENDING_APPROVAL có chứa đơn."""
    rows = db.execute(
        select(ScheduleSlot, PlanVersion.status)
        .join(PlanVersion, PlanVersion.id == ScheduleSlot.plan_version_id)
        .where(
            ScheduleSlot.work_order_id.in_(work_order_ids),
            PlanVersion.status.in_([PlanVersionStatus.ACTIVE, PlanVersionStatus.PENDING_APPROVAL]),
        )
        .order_by(ScheduleSlot.plan_version_id)
    )
    out: dict[str, tuple[ScheduleSlot, PlanVersionStatus]] = {}
    for slot, status in rows:
        out[slot.work_order_id] = (slot, status)  # version mới hơn ghi đè
    return {
        wid: CardSlotOut(
            line=s.line, start=s.start_at, end=s.end_at, sla_ok=True, plan_version=s.plan_version_id, plan_status=st
        )
        for wid, (s, st) in out.items()
    }


def _card(wo: WorkOrder, slot: CardSlotOut | None) -> WorkOrderCard:
    if slot is not None:
        slot = slot.model_copy(update={"sla_ok": _sla_ok(slot.end, wo.requested_return)})
    return WorkOrderCard(
        id=wo.id,
        product_name=wo.product_name,
        priority=wo.priority,
        state=wo.state,
        review_status=wo.review_status,
        expected_arrival=wo.expected_arrival,
        requested_return=wo.requested_return,
        estimated_duration_min=wo.estimated_duration_min,
        slot=slot,
    )


@router.post("/work-orders/{work_order_id}/schedule", response_model=ScheduleOut)
def schedule(
    work_order_id: str,
    user: User = Depends(require(Action.EDIT_SCHEDULE)),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> ScheduleOut:
    wo = get_work_order(db, work_order_id)
    try:
        result = schedule_work_order(
            db,
            wo,
            actor_id=user.id,
            now=utcnow(),
            tz=settings.local_tz,
            load_orders=order_loader(db),
            shifts=get_shift_policy(settings.local_tz),
        )
    except NewOrderBlockedError as e:
        raise HTTPException(
            status_code=409,
            detail={
                "error_code": "NEW_ORDER_BLOCKED",
                "message": f"Đơn bị chặn (BLOCK_NEW_ORDER): {e}",
                "risk": risk_out(e.assessment).model_dump(mode="json"),
            },
        ) from e
    except NotSchedulableError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except PlanConflictError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except (MissingEstimateError, UnschedulableError) as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    p = result.placement
    return ScheduleOut(
        line=p.line,
        start=p.start,
        end=p.end,
        plan_version=result.plan_version.id,
        sla_ok=p.sla_ok,
        plan_status=result.plan_version.status,
        reason=result.reason,
        risk=risk_out(result.risk),
    )


@router.put("/work-orders/{work_order_id}/schedule", response_model=ManualScheduleOut)
def schedule_manually(
    work_order_id: str,
    body: ManualScheduleIn,
    user: User = Depends(require(Action.EDIT_SCHEDULE)),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> ManualScheduleOut:
    """Điều phối xếp / sửa lịch thủ công (BR-15)."""
    wo = get_work_order(db, work_order_id)
    try:
        result = place_work_order_manually(
            db,
            wo,
            line=body.line,
            start=body.start,
            actor_id=user.id,
            now=utcnow(),
            tz=settings.local_tz,
            load_orders=order_loader(db),
            shifts=get_shift_policy(settings.local_tz),
        )
    except (NotSchedulableError, PlanConflictError, SlotConflictError) as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except (MissingEstimateError, UnschedulableError) as e:
        raise HTTPException(status_code=422, detail=f"Không xếp được: {e}") from e
    p = result.placement
    return ManualScheduleOut(
        line=p.slot.line,
        start=p.slot.start,
        end=p.slot.end,
        plan_version=result.plan_version.id,
        sla_ok=p.sla_ok,
        plan_status=result.plan_version.status,
        reason=p.reason,
    )


@router.get("/schedule", response_model=ScheduleViewOut)
def get_schedule(
    version: str = Query("current", pattern=r"^(current|\d+)$"),
    day: date | None = Query(None, alias="date"),
    _: User = Depends(require(Action.VIEW_BOARD)),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> ScheduleViewOut:
    if version == "current":
        v = active_version(db)
    else:
        v = db.get(PlanVersion, int(version))
        if v is None:
            raise HTTPException(status_code=404, detail=f"Không có plan version {version}")
    lines: dict[Line, list[ScheduleSlotOut]] = {Line.A: [], Line.B: []}
    if v is None:
        return ScheduleViewOut(plan_version=None, date=day, lines=lines)

    rows = version_slots(db, v.id)
    if day is not None:
        start = datetime.combine(day, time(0), settings.local_tz)
        end = start + timedelta(days=1)
        rows = [r for r in rows if r.start_at < end and start < r.end_at]
    orders = {
        wo.id: wo for wo in db.scalars(select(WorkOrder).where(WorkOrder.id.in_([r.work_order_id for r in rows])))
    }
    details = slot_details(db, v.id)
    for r in rows:
        wo = orders[r.work_order_id]
        lines[r.line].append(
            ScheduleSlotOut(
                work_order_id=wo.id,
                product_name=wo.product_name,
                priority=wo.priority,
                state=wo.state,
                line=r.line,
                start=r.start_at,
                end=r.end_at,
                requested_return=wo.requested_return,
                sla_ok=_sla_ok(r.end_at, wo.requested_return),
                reason=details.get(wo.id, {}).get("reason"),
            )
        )
    return ScheduleViewOut(plan_version=version_out(db, v), date=day, lines=lines)


@router.get("/plan-versions", response_model=list[PlanVersionOut])
def list_plan_versions(
    status: str | None = Query(None),
    _: User = Depends(require(Action.VIEW_BOARD)),
    db: Session = Depends(get_db),
) -> list[PlanVersionOut]:
    query = select(PlanVersion).order_by(PlanVersion.id.desc())
    if status is not None:
        wanted = PlanVersionStatus.PENDING_APPROVAL.value if status.lower() == "pending" else status.upper()
        if wanted not in PlanVersionStatus.__members__:
            raise HTTPException(status_code=422, detail=f"status không hợp lệ: {status}")
        query = query.where(PlanVersion.status == PlanVersionStatus(wanted))
    return [version_out(db, v) for v in db.scalars(query)]


@router.get("/work-orders", response_model=list[WorkOrderCard])
def list_work_orders(
    state: list[WorkOrderState] | None = Query(None),
    _: User = Depends(require(Action.VIEW_BOARD)),
    db: Session = Depends(get_db),
) -> list[WorkOrderCard]:
    query = select(WorkOrder).order_by(WorkOrder.requested_return, WorkOrder.created_at, WorkOrder.id)
    if state:
        query = query.where(WorkOrder.state.in_(state))
    orders = list(db.scalars(query))
    slots = card_slots(db, [wo.id for wo in orders])
    return [_card(wo, slots.get(wo.id)) for wo in orders]


@router.patch("/work-orders/{work_order_id}/state", response_model=WorkOrderCard)
def change_state(
    work_order_id: str,
    body: StateChange,
    user: User = Depends(require(Action.CHANGE_OPERATIONAL_STATE)),
    db: Session = Depends(get_db),
) -> WorkOrderCard:
    wo = get_work_order(db, work_order_id)
    if body.to_state not in OPERATIONAL_STATES:
        raise HTTPException(status_code=422, detail=f"{body.to_state} không phải trạng thái vận hành chuyển tay được")
    try:
        transition_work_order(
            db, wo, body.to_state, actor_id=user.id, reason=body.reason.strip() or "chuyển tay", now=utcnow()
        )
    except InvalidTransitionError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return _card(wo, card_slots(db, [wo.id]).get(wo.id))
