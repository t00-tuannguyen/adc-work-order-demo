"""Reset dữ liệu demo — ADC-002 (T-025), specs/api-contracts.md §2.

Xóa lịch (plan version, slot) và dữ liệu tiếp nhận rồi nạp `src/seed/orders.json`: giờ trong seed là giờ địa phương (HH:MM), gắn vào ngày
reset → mỗi lần reset cho cùng bố cục lịch. Đơn seed đi thẳng vào FEASIBILITY_CHECK qua Orchestration, kèm
ước tính thời lượng. `incidents.json` chỉ được đọc và trả về (mẫu điền sẵn cho form khai báo sự cố, ADC-004) —
không tự khai báo, để kịch bản demo xếp lịch xong rồi mới cho Line A dừng. Sự cố cũ bị xóa khi reset.
Audit log chỉ ghi thêm (BR-10) → không bị xóa khi reset.
"""

import json
from datetime import date, datetime, time, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, update
from sqlalchemy.orm import Session

from src.agents.graph import get_throughput_config
from src.api.deps import require
from src.modules.estimation import ThroughputConfig
from src.modules.identity import Action, User
from src.modules.intake import (
    ClarificationRequest,
    FieldExtraction,
    IngestJob,
    IntakeWarning,
    ReviewStatus,
    Ticket,
    TicketFile,
    TicketSourceType,
    WorkOrder,
    WorkOrderFields,
    apply_estimate,
    validate,
)
from src.modules.orchestration import (
    ActorType,
    AuditAction,
    PlanChange,
    PlanVersion,
    StateHistory,
    WorkOrderState,
    record,
    record_created,
    transition_work_order,
)
from src.modules.risk import Escalation, RiskCheck
from src.modules.scheduling import IncidentAffectedOrder, LineIncident, ScheduleSlot
from src.modules.types import Line, Priority
from src.services.db import get_db, utcnow
from src.settings import Settings, get_settings

router = APIRouter(tags=["demo"])


class SeedError(ValueError):
    """File seed sai định dạng hoặc lệnh seed không ước tính được."""


class SeedOrder(BaseModel):
    ref: str
    product_name: str
    quantity: int = Field(gt=0)
    pkg_length_cm: float = Field(gt=0)
    pkg_width_cm: float = Field(gt=0)
    pkg_height_cm: float = Field(gt=0)
    pkg_weight_kg: float = Field(gt=0)
    required_dose_kgy: float = Field(gt=0)
    priority: Priority
    expected_arrival: time
    requested_return: time


class SeedIncident(BaseModel):
    ref: str
    line: Line
    start_at: time
    est_downtime_min: int = Field(gt=0)
    note: str = ""


class _SeedFile(BaseModel):
    timezone: str

    @field_validator("timezone")
    @classmethod
    def _offset(cls, v: str) -> str:
        datetime.strptime(v, "%z")
        return v

    @property
    def tz(self) -> timezone:
        return datetime.strptime(self.timezone, "%z").tzinfo  # type: ignore[return-value]


class _OrdersFile(_SeedFile):
    orders: list[SeedOrder] = Field(min_length=1)


class _IncidentsFile(_SeedFile):
    incidents: list[SeedIncident]


def _read(path: Path, model: type[BaseModel]):
    try:
        return model.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError) as e:
        raise SeedError(f"seed {path.name} không hợp lệ: {e}") from e


def seed_day(seed_dir: Path, now: datetime) -> date:
    """Ngày demo = ngày hiện tại theo múi giờ của file seed."""
    return now.astimezone(_read(seed_dir / "orders.json", _OrdersFile).tz).date()


def seed_work_orders(seed_dir: Path, day: date) -> list[tuple[str, WorkOrderFields]]:
    """(ref, 8 trường) của từng lệnh seed, giờ gắn vào `day` theo múi giờ của file."""
    seed = _read(seed_dir / "orders.json", _OrdersFile)
    out = []
    for o in seed.orders:
        fields = WorkOrderFields(
            **o.model_dump(exclude={"ref", "expected_arrival", "requested_return"}),
            expected_arrival=datetime.combine(day, o.expected_arrival, seed.tz),
            requested_return=datetime.combine(day, o.requested_return, seed.tz),
        )
        out.append((o.ref, fields))
    return out


def seed_incidents(seed_dir: Path, day: date) -> list[dict]:
    seed = _read(seed_dir / "incidents.json", _IncidentsFile)
    return [
        {**i.model_dump(), "line": i.line.value, "start_at": datetime.combine(day, i.start_at, seed.tz)}
        for i in seed.incidents
    ]


def clear_intake_data(db: Session) -> None:
    """Xóa lịch, lịch sử trạng thái, kiểm tra rủi ro, escalation, sự cố, ticket, work order và dữ liệu đi kèm (theo thứ tự khóa ngoại). Không động tới user / audit."""
    db.execute(update(PlanVersion).values(parent_version_id=None))
    for model in (
        Escalation,
        RiskCheck,
        StateHistory,
        IncidentAffectedOrder,
        ScheduleSlot,
        PlanChange,
        PlanVersion,
        LineIncident,
        FieldExtraction,
        ClarificationRequest,
        IntakeWarning,
        WorkOrder,
        Ticket,
        IngestJob,
        TicketFile,
    ):
        db.execute(delete(model))


def load_seed(
    db: Session, orders: list[tuple[str, WorkOrderFields]], config: ThroughputConfig, *, actor_id: str, now: datetime
) -> list[tuple[str, WorkOrder]]:
    loaded: list[tuple[str, WorkOrder]] = []
    for ref, fields in orders:
        if errors := validate(fields):
            raise SeedError(f"{ref}: {', '.join(f'{e.field} {e.code}' for e in errors)}")
        ticket = Ticket(source_type=TicketSourceType.MANUAL, raw_text=f"Seed demo {ref}")
        db.add(ticket)
        db.flush()
        wo = WorkOrder(ticket_id=ticket.id, review_status=ReviewStatus.AUTO_ACCEPTED, **fields.model_dump())
        if reason := apply_estimate(wo, config):
            raise SeedError(f"{ref}: {reason}")
        db.add(wo)
        db.flush()
        record_created(
            db, wo.id, actor_id=actor_id, actor_type=ActorType.SYSTEM, reason=f"nạp seed demo {ref}", now=now
        )
        loaded.append((ref, wo))
    db.commit()
    for ref, wo in loaded:
        transition_work_order(
            db,
            wo,
            WorkOrderState.FEASIBILITY_CHECK,
            actor_id=actor_id,
            reason=f"nạp seed demo {ref}",
            now=now,
            actor_type=ActorType.SYSTEM,
        )
    return loaded


class SeedWorkOrderOut(BaseModel):
    id: str
    ref: str
    state: WorkOrderState
    estimated_duration_min: int


class SeedIncidentOut(BaseModel):
    ref: str
    line: Line
    start_at: datetime
    est_downtime_min: int
    note: str


class DemoResetOut(BaseModel):
    demo_date: date
    work_orders: list[SeedWorkOrderOut]
    incidents: list[SeedIncidentOut]


@router.post("/demo/reset", response_model=DemoResetOut)
def reset_demo(
    user: User = Depends(require(Action.VIEW_BOARD)),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> DemoResetOut:
    # Chỉ bật ở demo/staging (specs/user-roles.md §2); production luôn tắt dù cờ bật nhầm
    if not settings.demo_reset_enabled or settings.app_env == "production":
        raise HTTPException(status_code=404, detail="Not Found")
    seed_dir = Path(settings.seed_dir)
    now = utcnow()
    day = seed_day(seed_dir, now)
    orders = seed_work_orders(seed_dir, day)
    incidents = seed_incidents(seed_dir, day)

    clear_intake_data(db)
    loaded = load_seed(db, orders, get_throughput_config(), actor_id=user.id, now=now)
    record(
        db,
        user.id,
        AuditAction.DEMO_RESET,
        {"demo_date": day.isoformat(), "work_orders": len(loaded), "incidents": len(incidents)},
        now=now,
    )
    return DemoResetOut(
        demo_date=day,
        work_orders=[
            SeedWorkOrderOut(id=wo.id, ref=ref, state=wo.state, estimated_duration_min=wo.estimated_duration_min)
            for ref, wo in loaded
        ],
        incidents=[SeedIncidentOut(**i) for i in incidents],
    )
