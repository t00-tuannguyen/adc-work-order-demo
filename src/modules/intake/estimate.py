"""Gắn ước tính thời lượng vào work order (ADC-002) — gọi khi đơn vào FEASIBILITY_CHECK và khi nạp seed.

Nhóm sản phẩm lấy từ bảng từ khóa trong cấu hình; thiếu trường / nhóm hoặc liều chưa cấu hình → không tính,
trả lý do (BR-02: không lấy mặc định). Không commit, không đổi `state`.
"""

from dataclasses import asdict

from src.modules.estimation import Estimate, EstimateInput, EstimationError, ThroughputConfig, estimate_duration
from src.modules.intake.models import WorkOrder

_INPUT_COLUMNS = ("quantity", "pkg_length_cm", "pkg_width_cm", "pkg_height_cm", "pkg_weight_kg", "required_dose_kgy")


def try_estimate(wo: WorkOrder, config: ThroughputConfig) -> Estimate | str:
    """Ước tính hoặc lý do không ước tính được (thuần, không ghi gì)."""
    group = config.classify_product(wo.product_name)
    if group is None:
        return f"chưa xác định được nhóm sản phẩm từ tên '{wo.product_name or ''}'"
    values = {c: getattr(wo, c) for c in _INPUT_COLUMNS}
    if any(v is None for v in values.values()):
        return "thiếu trường để ước tính"
    try:
        return estimate_duration(EstimateInput(product_group=group, **values), config)
    except EstimationError as e:
        return str(e)


def apply_estimate(wo: WorkOrder, config: ThroughputConfig) -> str | None:
    """Ghi nhóm sản phẩm + ước tính lên work order; trả lý do khi không tính được."""
    wo.product_group = config.classify_product(wo.product_name)
    result = try_estimate(wo, config)
    if isinstance(result, str):
        wo.estimated_duration_min = wo.estimate_breakdown = wo.config_version = None
        return result
    wo.estimated_duration_min = result.duration_min
    wo.estimate_breakdown = asdict(result.breakdown)
    wo.config_version = result.config_version
    return None
