"""estimate_duration — mô hình throughput MÔ PHỎNG (ADC-002, specs/domains.md §4).

Hàm thuần, không gọi AI: cùng input + cùng cấu hình → cùng kết quả.
Ngoại lệ DEMO: bật FEATURE_RANDOM_ESTIMATE → bỏ qua mô hình, trả ngẫu nhiên 4–8 giờ (bội số `round_to_min`).
"""

import math
import random
from dataclasses import dataclass

from src.modules.estimation.config import ThroughputConfig
from src.settings import get_settings

DEMO_MIN_MIN = 4 * 60
DEMO_MAX_MIN = 8 * 60


class EstimationError(ValueError):
    """Input không hợp lệ hoặc hệ số không có trong cấu hình (BR-02)."""


@dataclass(frozen=True)
class EstimateInput:
    product_group: str
    quantity: int
    pkg_length_cm: float
    pkg_width_cm: float
    pkg_height_cm: float
    pkg_weight_kg: float
    required_dose_kgy: float


@dataclass(frozen=True)
class Breakdown:
    setup: float
    weight_load: float
    volume_load: float
    dose_load: float
    buffer: float


@dataclass(frozen=True)
class Estimate:
    duration_min: int
    breakdown: Breakdown
    config_version: str


def dose_key(dose_kgy: float) -> str:
    """10.0 → "10", 7.5 → "7.5" — khớp key trong `dose_factor`."""
    return f"{dose_kgy:g}"


def _factor(table: dict[str, float | None], key: str, name: str) -> float:
    if key not in table:
        raise EstimationError(f"{name} '{key}' không có trong cấu hình")
    value = table[key]
    if value is None:
        raise EstimationError(f"{name} '{key}' chưa được cấu hình (TODO trong throughput.yaml)")
    return float(value)


def estimate_duration(order: EstimateInput, config: ThroughputConfig) -> Estimate:
    if order.quantity <= 0:
        raise EstimationError("quantity phải > 0")
    dims = (order.pkg_length_cm, order.pkg_width_cm, order.pkg_height_cm, order.pkg_weight_kg)
    if any(v <= 0 for v in dims):
        raise EstimationError("kích thước và khối lượng thùng phải > 0")

    if get_settings().feature_random_estimate:
        return _random_estimate(config)

    density = _factor(config.density_factor, order.product_group, "product_group")
    dose = _factor(config.dose_factor, dose_key(order.required_dose_kgy), "required_dose_kgy")

    total_weight = order.quantity * order.pkg_weight_kg
    total_volume_m3 = order.quantity * order.pkg_length_cm * order.pkg_width_cm * order.pkg_height_cm / 1_000_000

    setup = config.setup_min
    weight_load = total_weight * config.min_per_kg * density
    volume_load = total_volume_m3 * config.min_per_m3
    dose_load = (weight_load + volume_load) * (dose - 1)
    buffer = (setup + weight_load + volume_load + dose_load) * config.buffer_pct
    total = setup + weight_load + volume_load + dose_load + buffer

    # round() trước ceil để tránh sai số dấu phẩy động đẩy 180.0000001 lên 195
    step = config.round_to_min
    duration = math.ceil(round(total, 6) / step) * step

    return Estimate(
        duration_min=duration,
        breakdown=Breakdown(*(round(v, 2) for v in (setup, weight_load, volume_load, dose_load, buffer))),
        config_version=config.version,
    )


def _random_estimate(config: ThroughputConfig) -> Estimate:
    """DEMO: thời lượng ngẫu nhiên 4–8 giờ; breakdown chia lại cho cộng đúng tổng."""
    step = config.round_to_min
    duration = random.randrange(DEMO_MIN_MIN, DEMO_MAX_MIN + 1, step)
    buffer = duration * config.buffer_pct / (1 + config.buffer_pct)
    setup = config.setup_min
    return Estimate(
        duration_min=duration,
        breakdown=Breakdown(setup, round(duration - setup - buffer, 2), 0.0, 0.0, round(buffer, 2)),
        config_version=f"{config.version}-demo-random",
    )
