"""Estimation API — ADC-002, specs/api-contracts.md §2."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.agents.graph import get_throughput_config
from src.api.deps import require
from src.modules.estimation import EstimateInput, EstimationError, estimate_duration
from src.modules.identity import Action

# Dữ liệu vận hành → mọi vai trò ACTIVE (specs/user-roles.md §2: xem Kanban, lịch, KPI)
router = APIRouter(tags=["estimation"], dependencies=[Depends(require(Action.VIEW_BOARD))])


class EstimateRequest(BaseModel):
    product_group: str
    quantity: int = Field(..., gt=0)
    pkg_length_cm: float = Field(..., gt=0)
    pkg_width_cm: float = Field(..., gt=0)
    pkg_height_cm: float = Field(..., gt=0)
    pkg_weight_kg: float = Field(..., gt=0)
    required_dose_kgy: float = Field(..., gt=0)


class BreakdownOut(BaseModel):
    setup: float
    weight_load: float
    volume_load: float
    dose_load: float
    buffer: float


class EstimateResponse(BaseModel):
    duration_min: int
    breakdown: BreakdownOut
    config_version: str


@router.post("/estimate", response_model=EstimateResponse)
def estimate(req: EstimateRequest) -> EstimateResponse:
    try:
        result = estimate_duration(EstimateInput(**req.model_dump()), get_throughput_config())
    except EstimationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return EstimateResponse(
        duration_min=result.duration_min,
        breakdown=BreakdownOut(**vars(result.breakdown)),
        config_version=result.config_version,
    )


@router.get("/config/throughput")
def throughput_config() -> dict:
    """Tham số hiện hành — trang "Giả định vận hành" (chỉ đọc, giá trị giả lập)."""
    return get_throughput_config().raw
