"""Sự cố line — ADC-004, specs/api-contracts.md §4.

Khai báo / đóng sự cố: Điều phối (DECLARE_INCIDENT). Xem: mọi vai trò (VIEW_BOARD).
Phương án đọc lại từ DB (version đề xuất mới nhất của sự cố) → POST và GET trả cùng dữ liệu.
`explanation` trong IncidentOut là bản deterministic (trả ngay); Scheduler Agent viết lại bằng LLM qua
POST /incidents/{id}/explanation (T-034) — gọi riêng để phương án không phải chờ LLM.
"""

from collections.abc import Iterable
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import AwareDatetime, BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from src.agents.graph import get_shift_policy
from src.agents.scheduler_agent import ExplanationSource, PlanFacts, SchedulerAgent, explain_plan
from src.api.deps import require
from src.api.scheduling import PlanVersionOut, version_out
from src.modules.identity import Action, User
from src.modules.intake import WorkOrder
from src.modules.orchestration import (
    ChangeType,
    IncidentConflictError,
    InvalidIncidentError,
    PlanChange,
    PlanVersion,
    WorkOrderState,
    declare_incident,
    resolve_incident,
)
from src.modules.scheduling import (
    AffectedOutcome,
    IncidentAffectedOrder,
    IncidentStatus,
    LineIncident,
    MoveSummary,
    ScheduleSlot,
    Slot,
)
from src.modules.types import Line, Priority
from src.services.db import get_db, utcnow
from src.services.llm import get_llm
from src.settings import Settings, get_settings

router = APIRouter(tags=["incidents"])

MAX_DOWNTIME_MIN = 7 * 24 * 60


class IncidentIn(BaseModel):
    line: Line
    start_at: AwareDatetime
    est_downtime_min: int = Field(ge=0, le=MAX_DOWNTIME_MIN)
    note: str = Field(default="", max_length=500)


class ResolveIn(BaseModel):
    actual_end: AwareDatetime


class SlotTimeOut(BaseModel):
    line: Line
    start: datetime
    end: datetime


class AffectedOrderOut(BaseModel):
    work_order_id: str
    product_name: str | None
    priority: Priority | None
    state: WorkOrderState
    outcome: AffectedOutcome
    change_type: ChangeType
    old: SlotTimeOut
    new: SlotTimeOut
    requested_return: datetime | None
    sla_ok: bool
    reason: str


class ExplanationOut(BaseModel):
    explanation: str
    source: ExplanationSource
    plan_version_id: int | None


class IncidentOut(BaseModel):
    incident_id: int
    line: Line
    start_at: datetime
    est_downtime_min: int
    end_at: datetime
    actual_end_at: datetime | None
    status: IncidentStatus
    note: str
    created_by: str
    created_at: datetime
    affected_orders: list[AffectedOrderOut]
    proposed_plan_version: PlanVersionOut | None
    sla_risks: list[str]
    explanation: str


def _get(db: Session, incident_id: int) -> LineIncident:
    incident = db.get(LineIncident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy sự cố")
    return incident


def _orders(db: Session):
    def load(ids: Iterable[str]) -> dict[str, WorkOrder]:
        return {wo.id: wo for wo in db.scalars(select(WorkOrder).where(WorkOrder.id.in_(list(ids))))}

    return load


def _span(s: ScheduleSlot) -> SlotTimeOut:
    return SlotTimeOut(line=s.line, start=s.start_at, end=s.end_at)


def _plan(db: Session, inc: LineIncident) -> tuple[PlanVersion | None, list[AffectedOrderOut], list[MoveSummary]]:
    """Phương án mới nhất của sự cố: version, đơn bị ảnh hưởng (thứ tự xử lý) và dữ liệu để giải thích."""
    version = db.scalars(
        select(PlanVersion).where(PlanVersion.incident_id == inc.id).order_by(PlanVersion.id.desc())
    ).first()
    affected: list[AffectedOrderOut] = []
    summaries: list[MoveSummary] = []
    if version is not None:
        old, new = aliased(ScheduleSlot), aliased(ScheduleSlot)
        rows = db.execute(
            select(IncidentAffectedOrder, old, new, WorkOrder, PlanChange)
            .join(old, old.id == IncidentAffectedOrder.old_slot_id)
            .join(new, new.id == IncidentAffectedOrder.new_slot_id)
            .join(WorkOrder, WorkOrder.id == IncidentAffectedOrder.work_order_id)
            .join(
                PlanChange,
                (PlanChange.plan_version_id == new.plan_version_id)
                & (PlanChange.work_order_id == IncidentAffectedOrder.work_order_id),
            )
            .where(IncidentAffectedOrder.incident_id == inc.id, new.plan_version_id == version.id)
            .order_by(IncidentAffectedOrder.id)  # thứ tự xử lý của reschedule
        )
        for a, o, n, wo, change in rows:
            affected.append(
                AffectedOrderOut(
                    work_order_id=wo.id,
                    product_name=wo.product_name,
                    priority=wo.priority,
                    state=wo.state,
                    outcome=a.outcome,
                    change_type=change.change_type,
                    old=_span(o),
                    new=_span(n),
                    requested_return=wo.requested_return,
                    sla_ok=change.new_value["sla_ok"],
                    reason=change.new_value["reason"],
                )
            )
            summaries.append(
                MoveSummary(
                    label=wo.product_name or wo.id,
                    priority=wo.priority or Priority.NORMAL,
                    old=Slot(wo.id, o.line, o.start_at, o.end_at),
                    new=Slot(wo.id, n.line, n.start_at, n.end_at),
                    requested_return=wo.requested_return or o.end_at,
                    bumped=change.change_type == ChangeType.PRIORITY_OVERRIDE,
                    pulled=a.outcome == AffectedOutcome.PULLED_FORWARD,
                )
            )
    return version, affected, summaries


def _facts(inc: LineIncident, summaries: list[MoveSummary]) -> PlanFacts:
    return PlanFacts(
        line=inc.line,
        start=inc.start_at,
        end=inc.end_at,
        moves=summaries,
        resolved=inc.status == IncidentStatus.RESOLVED,
    )


def _out(db: Session, inc: LineIncident, settings: Settings) -> IncidentOut:
    version, affected, summaries = _plan(db, inc)
    return IncidentOut(
        incident_id=inc.id,
        line=inc.line,
        start_at=inc.start_at,
        est_downtime_min=inc.est_downtime_min,
        end_at=inc.end_at,
        actual_end_at=inc.actual_end_at,
        status=inc.status,
        note=inc.note,
        created_by=inc.created_by,
        created_at=inc.created_at,
        affected_orders=affected,
        proposed_plan_version=version_out(db, version) if version else None,
        sla_risks=[a.work_order_id for a in affected if not a.sla_ok],
        explanation=explain_plan(_facts(inc, summaries), None, settings.local_tz).text,
    )


@router.post("/incidents", response_model=IncidentOut, status_code=201)
def create_incident(
    body: IncidentIn,
    user: User = Depends(require(Action.DECLARE_INCIDENT)),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> IncidentOut:
    try:
        incident = declare_incident(
            db,
            line=body.line,
            start_at=body.start_at,
            est_downtime_min=body.est_downtime_min,
            note=body.note.strip(),
            actor_id=user.id,
            now=utcnow(),
            tz=settings.local_tz,
            load_orders=_orders(db),
            shifts=get_shift_policy(settings.local_tz),
        )
    except IncidentConflictError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return _out(db, incident, settings)


@router.get("/incidents", response_model=list[IncidentOut])
def list_incidents(
    _: User = Depends(require(Action.VIEW_BOARD)),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> list[IncidentOut]:
    """Mọi sự cố, mới nhất trước — màn danh sách / so sánh trước-sau (T-035)."""
    incidents = db.scalars(select(LineIncident).order_by(LineIncident.start_at.desc(), LineIncident.id.desc()))
    return [_out(db, inc, settings) for inc in incidents]


@router.get("/incidents/{incident_id}", response_model=IncidentOut)
def get_incident(
    incident_id: int,
    _: User = Depends(require(Action.VIEW_BOARD)),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> IncidentOut:
    return _out(db, _get(db, incident_id), settings)


@router.post("/incidents/{incident_id}/resolve", response_model=IncidentOut)
def resolve(
    incident_id: int,
    body: ResolveIn,
    user: User = Depends(require(Action.DECLARE_INCIDENT)),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> IncidentOut:
    incident = _get(db, incident_id)
    try:
        resolve_incident(
            db,
            incident,
            actual_end=body.actual_end,
            actor_id=user.id,
            now=utcnow(),
            tz=settings.local_tz,
            load_orders=_orders(db),
            shifts=get_shift_policy(settings.local_tz),
        )
    except IncidentConflictError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except InvalidIncidentError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return _out(db, incident, settings)


def get_scheduler_agent(settings: Settings = Depends(get_settings)) -> SchedulerAgent | None:
    """Tắt bằng FEATURE_AI_EXPLANATION (dự phòng khi LLM chậm lúc demo) hoặc thiếu OPENAI_API_KEY → bản deterministic."""
    if not settings.feature_ai_explanation or not settings.openai_api_key:
        return None
    return SchedulerAgent(get_llm(), settings.local_tz)


@router.post("/incidents/{incident_id}/explanation", response_model=ExplanationOut)
def explain(
    incident_id: int,
    _: User = Depends(require(Action.VIEW_BOARD)),
    agent: SchedulerAgent | None = Depends(get_scheduler_agent),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> ExplanationOut:
    """Chỉ đọc: không đổi phương án hay trạng thái; câu LLM sai dữ liệu → bản deterministic."""
    inc = _get(db, incident_id)
    version, _affected, summaries = _plan(db, inc)
    result = explain_plan(_facts(inc, summaries), agent, settings.local_tz)
    return ExplanationOut(
        explanation=result.text, source=result.source, plan_version_id=version.id if version else None
    )
