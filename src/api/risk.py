"""Risk & Escalation — ADC-005, specs/api-contracts.md §5.

Kiểm tra rủi ro đơn mới (T-036): mọi vai trò (VIEW_BOARD) — banner khi tạo đơn; chỉ mô phỏng, không đổi lịch.
Hàng đợi escalation (T-037): mọi vai trò (VIEW_BOARD).
Soạn nháp / duyệt thông điệp (T-038): Kinh doanh, Quản lý (APPROVE_ESCALATION_MESSAGE). Risk Agent chỉ soạn chữ.
"""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.agents.graph import get_shift_policy
from src.agents.risk_agent import DelayEvent, DraftSource, RiskAgent, draft_message
from src.api.deps import require
from src.api.scheduling import RiskCheckOut, get_work_order, order_loader, risk_out
from src.modules.identity import Action, User
from src.modules.intake import WorkOrder
from src.modules.orchestration import (
    EscalationStateError,
    MissingEstimateError,
    NotSchedulableError,
    PlanChange,
    PlanVersion,
    PlanVersionStatus,
    WorkOrderState,
    active_version,
    approve_escalation,
    check_new_order_risk,
    save_draft,
)
from src.modules.risk import OPEN_ESCALATION, Escalation, EscalationStatus
from src.modules.scheduling import ScheduleSlot, UnschedulableError
from src.modules.types import PRIORITY_RANK, Priority
from src.services.db import get_db, utcnow
from src.services.llm import get_llm
from src.settings import Settings, get_settings

router = APIRouter(tags=["risk"])


@router.post("/work-orders/{work_order_id}/risk-check", response_model=RiskCheckOut)
def risk_check(
    work_order_id: str,
    _: User = Depends(require(Action.VIEW_BOARD)),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> RiskCheckOut:
    wo = get_work_order(db, work_order_id)
    try:
        risk = check_new_order_risk(
            db,
            wo,
            now=utcnow(),
            tz=settings.local_tz,
            load_orders=order_loader(db),
            shifts=get_shift_policy(settings.local_tz),
        )
    except NotSchedulableError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except (MissingEstimateError, UnschedulableError) as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return risk_out(risk)


class EscalationOut(BaseModel):
    id: int
    work_order_id: str
    product_name: str | None
    priority: Priority | None
    state: WorkOrderState
    incident_id: int | None
    delay_min: int
    requested_return: datetime | None
    expected_finish: datetime | None
    status: EscalationStatus
    draft_message: str | None
    final_message: str | None
    approved_by: str | None
    approved_at: datetime | None
    can_close: bool


def planned_ends(db: Session, ids: list[str]) -> dict[str, datetime]:
    """Giờ xong theo kế hoạch hiện hành của mỗi đơn: thay đổi mới nhất của đơn trong 1 version đang ACTIVE / chờ
    duyệt (phương án sự cố, đơn bị đẩy…), không có thì slot của version ACTIVE. Không lấy bản chép lại của đơn trong
    đề xuất khác (vd đề xuất nhận đơn WARN chép cả lịch ACTIVE) — nó che mất phương án đang chờ duyệt."""
    live = [PlanVersionStatus.ACTIVE, PlanVersionStatus.PENDING_APPROVAL]
    out: dict[str, datetime] = {}
    active = active_version(db)
    if active is not None:
        for r in db.scalars(
            select(ScheduleSlot).where(ScheduleSlot.plan_version_id == active.id, ScheduleSlot.work_order_id.in_(ids))
        ):
            out[r.work_order_id] = r.end_at
    changes = db.scalars(
        select(PlanChange)
        .join(PlanVersion, PlanVersion.id == PlanChange.plan_version_id)
        .where(PlanChange.work_order_id.in_(ids), PlanVersion.status.in_(live))
        .order_by(PlanChange.plan_version_id, PlanChange.id)
    )
    for c in changes:  # version mới hơn ghi đè
        if "end" in c.new_value:
            out[c.work_order_id] = datetime.fromisoformat(c.new_value["end"])
    return out


def escalations_out(db: Session, rows: list[Escalation]) -> list[EscalationOut]:
    ids = [e.work_order_id for e in rows]
    orders = {wo.id: wo for wo in db.scalars(select(WorkOrder).where(WorkOrder.id.in_(ids)))}
    ends = planned_ends(db, ids)
    out = []
    for e in rows:
        wo = orders[e.work_order_id]
        ret = wo.requested_return
        end = ends.get(wo.id)
        out.append(
            EscalationOut(
                id=e.id,
                work_order_id=wo.id,
                product_name=wo.product_name,
                priority=wo.priority,
                state=wo.state,
                incident_id=e.incident_id,
                delay_min=e.delay_min,
                requested_return=ret,
                expected_finish=ret + timedelta(minutes=e.delay_min) if ret else None,
                status=e.status,
                draft_message=e.draft_message,
                final_message=e.final_message,
                approved_by=e.approved_by,
                approved_at=e.approved_at,
                # Hết trễ (sự cố kết thúc sớm, phương án bị từ chối…) → người xác nhận đóng
                can_close=e.status in OPEN_ESCALATION and end is not None and ret is not None and end <= ret,
            )
        )
    return out


@router.get("/escalations", response_model=list[EscalationOut])
def list_escalations(
    status: str | None = Query(None),
    _: User = Depends(require(Action.VIEW_BOARD)),
    db: Session = Depends(get_db),
) -> list[EscalationOut]:
    query = select(Escalation)
    if status is not None:
        if status.lower() == "open":
            query = query.where(Escalation.status.in_(OPEN_ESCALATION))
        elif status.upper() in EscalationStatus.__members__:
            query = query.where(Escalation.status == EscalationStatus(status.upper()))
        else:
            raise HTTPException(status_code=422, detail=f"status không hợp lệ: {status}")
    items = escalations_out(db, list(db.scalars(query)))
    return sorted(items, key=lambda e: (PRIORITY_RANK[e.priority or Priority.NORMAL], -e.delay_min, e.id))


class DraftOut(BaseModel):
    message_draft: str
    source: DraftSource


class ApproveIn(BaseModel):
    final_message: str = Field(min_length=1, max_length=2000)


def get_risk_agent(settings: Settings = Depends(get_settings)) -> RiskAgent | None:
    """Tắt bằng FEATURE_AI_MESSAGE_DRAFT (dự phòng khi LLM chậm lúc demo) hoặc thiếu OPENAI_API_KEY → mẫu soạn sẵn."""
    if not settings.feature_ai_message_draft or not settings.openai_api_key:
        return None
    return RiskAgent(get_llm(), settings.local_tz)


def _get_escalation(db: Session, escalation_id: int) -> Escalation:
    esc = db.get(Escalation, escalation_id)
    if esc is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy escalation")
    return esc


def _cause(esc: Escalation) -> str:
    """Nguyên nhân ở mức chung — không nêu line, đơn hay khách khác."""
    if esc.incident_id is not None:
        return "sự cố kỹ thuật trên dây chuyền chiếu xạ"
    return "điều chỉnh kế hoạch sản xuất để ưu tiên đơn hàng khẩn"


@router.post("/escalations/{escalation_id}/draft", response_model=DraftOut)
def draft(
    escalation_id: int,
    user: User = Depends(require(Action.APPROVE_ESCALATION_MESSAGE)),
    agent: RiskAgent | None = Depends(get_risk_agent),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> DraftOut:
    esc = _get_escalation(db, escalation_id)
    wo = get_work_order(db, esc.work_order_id)
    if esc.status not in OPEN_ESCALATION:
        raise HTTPException(status_code=409, detail=f"Escalation đã {esc.status}, không soạn lại được")
    if wo.requested_return is None:
        raise HTTPException(status_code=422, detail="Lệnh chưa có giờ trả")
    event = DelayEvent(
        product_name=wo.product_name or "của Quý khách",
        priority=wo.priority or Priority.NORMAL,
        requested_return=wo.requested_return,
        expected_finish=wo.requested_return + timedelta(minutes=esc.delay_min),
        cause=_cause(esc),
    )
    result = draft_message(event, agent, settings.local_tz)
    try:
        save_draft(db, esc, result.message, source=result.source.value, actor_id=user.id, now=utcnow())
    except EscalationStateError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return DraftOut(message_draft=result.message, source=result.source)


@router.post("/escalations/{escalation_id}/approve", response_model=EscalationOut)
def approve(
    escalation_id: int,
    body: ApproveIn,
    user: User = Depends(require(Action.APPROVE_ESCALATION_MESSAGE)),
    db: Session = Depends(get_db),
) -> EscalationOut:
    esc = _get_escalation(db, escalation_id)
    message = body.final_message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="Thông điệp cuối không được rỗng")
    try:
        approve_escalation(db, esc, message, actor_id=user.id, now=utcnow())
    except EscalationStateError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return escalations_out(db, [esc])[0]
