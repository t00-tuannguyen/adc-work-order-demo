"""Phê duyệt plan version & lịch sử trạng thái — ADC-006, specs/api-contracts.md §6.

Duyệt / từ chối (T-042): SALES, OPS_MANAGER (APPROVE_PLAN_VERSION). Diff, lịch sử (T-041): mọi vai trò (VIEW_BOARD).
LLM không bao giờ gọi các endpoint duyệt (specs/user-roles.md §4).
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.api.deps import require
from src.api.scheduling import PlanVersionOut, get_work_order, order_loader, version_out
from src.modules.identity import Action, User
from src.modules.intake import WorkOrder
from src.modules.orchestration import (
    ActorType,
    ChangeType,
    PlanConflictError,
    PlanVersionNotFoundError,
    PlanVersionStateError,
    WorkOrderState,
    approve_plan_version,
    plan_diff,
    reject_plan_version,
    work_order_history,
)
from src.modules.types import Line, Priority
from src.services.db import get_db, utcnow

router = APIRouter(tags=["approval"])


class HistoryEntryOut(BaseModel):
    id: int
    from_state: WorkOrderState | None
    to_state: WorkOrderState
    actor_type: ActorType
    actor_id: str
    actor_name: str
    reason: str
    plan_version_id: int | None
    at: datetime


class SpanOut(BaseModel):
    line: Line
    start: datetime
    end: datetime


class PlanChangeOut(BaseModel):
    work_order_id: str
    product_name: str | None
    priority: Priority | None
    state: WorkOrderState
    requested_return: datetime | None
    change_type: ChangeType
    needs_approval: bool
    old: SpanOut | None
    new: SpanOut
    sla_ok: bool
    reason: str | None


class PlanDiffOut(BaseModel):
    plan_version: PlanVersionOut
    base_version_id: int | None
    base_changed: bool
    incident_id: int | None
    changes: list[PlanChangeOut]
    decided_by: str | None
    decided_by_name: str | None
    decided_at: datetime | None
    comment: str | None


class ApproveIn(BaseModel):
    comment: str = Field(default="", max_length=500)


class RejectIn(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


def _names(db: Session, ids: set[str]) -> dict[str, str]:
    return {u.id: u.name or u.email for u in db.scalars(select(User).where(User.id.in_(ids)))}


def _span(value: dict | None) -> SpanOut | None:
    return SpanOut(line=value["line"], start=value["start"], end=value["end"]) if value else None


def _decide_errors(e: Exception) -> HTTPException:
    if isinstance(e, PlanVersionNotFoundError):
        return HTTPException(status_code=404, detail=str(e))
    return HTTPException(status_code=409, detail=str(e))


@router.get("/plan-versions/{version_id}/diff", response_model=PlanDiffOut)
def get_plan_diff(
    version_id: int,
    _: User = Depends(require(Action.VIEW_BOARD)),
    db: Session = Depends(get_db),
) -> PlanDiffOut:
    try:
        diff = plan_diff(db, version_id)
    except PlanVersionNotFoundError as e:
        raise _decide_errors(e) from e
    v = diff.version
    orders = {
        wo.id: wo
        for wo in db.scalars(select(WorkOrder).where(WorkOrder.id.in_([d.change.work_order_id for d in diff.changes])))
    }
    names = _names(db, {v.approved_by} if v.approved_by else set())
    return PlanDiffOut(
        plan_version=version_out(db, v),
        base_version_id=diff.base_version_id,
        base_changed=diff.base_changed,
        incident_id=v.incident_id,
        changes=[
            PlanChangeOut(
                work_order_id=(wo := orders[d.change.work_order_id]).id,
                product_name=wo.product_name,
                priority=wo.priority,
                state=wo.state,
                requested_return=wo.requested_return,
                change_type=d.change.change_type,
                needs_approval=d.change.needs_approval,
                old=_span(d.old),
                new=_span(d.new),
                sla_ok=bool(d.new.get("sla_ok", True)),
                reason=d.new.get("reason"),
            )
            for d in diff.changes
        ],
        decided_by=v.approved_by,
        decided_by_name=names.get(v.approved_by) if v.approved_by else None,
        decided_at=v.approved_at,
        comment=v.comment,
    )


@router.post("/plan-versions/{version_id}/approve", response_model=PlanVersionOut)
def approve(
    version_id: int,
    body: ApproveIn,
    user: User = Depends(require(Action.APPROVE_PLAN_VERSION)),
    db: Session = Depends(get_db),
) -> PlanVersionOut:
    try:
        v = approve_plan_version(
            db, version_id, actor_id=user.id, comment=body.comment.strip(), now=utcnow(), load_orders=order_loader(db)
        )
    except (PlanVersionNotFoundError, PlanVersionStateError, PlanConflictError) as e:
        raise _decide_errors(e) from e
    return version_out(db, v)


@router.post("/plan-versions/{version_id}/reject", response_model=PlanVersionOut)
def reject(
    version_id: int,
    body: RejectIn,
    user: User = Depends(require(Action.APPROVE_PLAN_VERSION)),
    db: Session = Depends(get_db),
) -> PlanVersionOut:
    reason = body.reason.strip()
    if not reason:
        raise HTTPException(status_code=422, detail="Từ chối phải ghi lý do")
    try:
        v = reject_plan_version(
            db, version_id, actor_id=user.id, reason=reason, now=utcnow(), load_orders=order_loader(db)
        )
    except (PlanVersionNotFoundError, PlanVersionStateError) as e:
        raise _decide_errors(e) from e
    return version_out(db, v)


@router.get("/work-orders/{work_order_id}/history", response_model=list[HistoryEntryOut])
def get_history(
    work_order_id: str,
    _: User = Depends(require(Action.VIEW_BOARD)),
    db: Session = Depends(get_db),
) -> list[HistoryEntryOut]:
    get_work_order(db, work_order_id)  # 404
    rows = work_order_history(db, work_order_id)
    names = _names(db, {r.actor_id for r in rows})
    return [
        HistoryEntryOut(
            id=r.id,
            from_state=r.from_state,
            to_state=r.to_state,
            actor_type=r.actor_type,
            actor_id=r.actor_id,
            actor_name=names.get(r.actor_id, r.actor_id),
            reason=r.reason,
            plan_version_id=r.plan_version_id,
            at=r.at,
        )
        for r in rows
    ]
