"""Luồng tiếp nhận do Orchestrator điều phối (ADR-0001, ADR-0007): validate → assess → estimate → schedule.

Graph là code định nghĩa sẵn; LLM không quyết định bước tiếp theo, không sinh giờ/line/thứ tự.
Bước trích xuất (Order Agent, T-019) chạy trước graph và đổ kết quả vào `fields` + `signals`
(nhãn nguồn, độ tin cậy OCR từng trường). Không có `signals` (nhập tay / dán nội dung) → coi như chắc chắn.
Chỉ HITL khi độ tin cậy thấp (REVIEW); kết quả không rõ ràng (WARN) vẫn đi tiếp kèm cảnh báo cho người.
"""

from datetime import datetime, tzinfo
from functools import lru_cache
from typing import TypedDict

from langgraph.graph import END, StateGraph

from src.modules.estimation import Estimate, EstimateInput, ThroughputConfig, ThroughputConfigSource, estimate_duration
from src.modules.intake import (
    FieldError,
    FieldSignal,
    IntakeAssessment,
    ReviewDecision,
    ReviewThresholds,
    TicketSignal,
    WorkOrderFields,
    assess,
    validate,
)
from src.modules.scheduling import Placement, ShiftPolicy, Slot, schedule_order
from src.settings import get_settings


class IntakeState(TypedDict, total=False):
    fields: WorkOrderFields
    signals: dict[str, FieldSignal]
    ticket_signal: TicketSignal
    product_group: str  # TODO(T-017): gán nhóm sản phẩm từ product_name
    now: datetime
    slots: list[Slot]
    shifts: ShiftPolicy | None
    errors: list[FieldError]
    assessment: IntakeAssessment
    estimate: Estimate
    placement: Placement


@lru_cache
def _throughput_source() -> ThroughputConfigSource:
    return ThroughputConfigSource(get_settings().throughput_config_path)


def get_throughput_config() -> ThroughputConfig:
    """Cấu hình đang dùng — tự nạp lại khi file đổi, không cần khởi động lại (T-023)."""
    return _throughput_source().get()


def get_shift_policy(tz: tzinfo) -> ShiftPolicy | None:
    """Ca làm của line từ cấu hình đang dùng (T-054); None = chạy 24/7 cho mọi đơn."""
    return ShiftPolicy.from_config(get_throughput_config().raw, tz)


def validate_node(state: IntakeState) -> dict:
    config = get_throughput_config()
    allowed = [k for k, v in config.dose_factor.items() if v is not None]
    return {"errors": validate(state["fields"], allowed_doses=allowed)}


def assess_node(state: IntakeState) -> dict:
    thresholds = ReviewThresholds.from_config(get_throughput_config().raw)
    return {"assessment": assess(state.get("signals", {}), thresholds, state.get("ticket_signal"))}


def estimate_node(state: IntakeState) -> dict:
    f = state["fields"]
    order = EstimateInput(
        product_group=state["product_group"],
        quantity=f.quantity,
        pkg_length_cm=f.pkg_length_cm,
        pkg_width_cm=f.pkg_width_cm,
        pkg_height_cm=f.pkg_height_cm,
        pkg_weight_kg=f.pkg_weight_kg,
        required_dose_kgy=f.required_dose_kgy,
    )
    return {"estimate": estimate_duration(order, get_throughput_config())}


def schedule_node(state: IntakeState) -> dict:
    f = state["fields"]
    placement = schedule_order(
        duration_min=state["estimate"].duration_min,
        expected_arrival=f.expected_arrival,
        requested_return=f.requested_return,
        now=state["now"],
        slots=state.get("slots", []),
        priority=f.priority,
        shifts=state.get("shifts"),
    )
    return {"placement": placement}


def after_assess(state: IntakeState) -> str:
    # Thiếu/sai trường → dừng, giữ DRAFT và sinh yêu cầu bổ sung (BR-01)
    if state["errors"]:
        return END
    # Tin cậy thấp → dừng, giữ DRAFT chờ người xác nhận (BR-12). WARN vẫn đi tiếp (BR-13).
    if state["assessment"].decision == ReviewDecision.REVIEW:
        return END
    return "estimate"


def build_intake_graph():
    graph = StateGraph(IntakeState)
    graph.add_node("validate", validate_node)
    graph.add_node("assess", assess_node)
    graph.add_node("estimate", estimate_node)
    graph.add_node("schedule", schedule_node)
    graph.set_entry_point("validate")
    graph.add_edge("validate", "assess")
    graph.add_conditional_edges("assess", after_assess)
    graph.add_edge("estimate", "schedule")
    graph.add_edge("schedule", END)
    return graph.compile()


intake_graph = build_intake_graph()
