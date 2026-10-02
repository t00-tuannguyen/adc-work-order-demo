"""T-054 — line chạy 24/7, ưu tiên ca ngày 06:00–22:00; ca đêm chỉ cho đơn khẩn cấp (Khẩn, VIP)."""

import random
from datetime import datetime, time, timedelta, timezone

import pytest

from src.modules.estimation import ConfigError, ThroughputConfig
from src.modules.scheduling import (
    RescheduleCandidate,
    ShiftPolicy,
    Slot,
    UnschedulableError,
    has_overlap,
    placement_reason,
    reschedule,
    schedule_order,
)
from src.modules.scheduling.incident import Incident
from src.modules.types import Line, Priority

VN = timezone(timedelta(hours=7))
SHIFTS = ShiftPolicy(
    tz=VN, day_start=time(6), day_end=time(22), night_priorities=frozenset({Priority.URGENT, Priority.VIP})
)


def vn(hour: int, minute: int = 0, day: int = 1) -> datetime:
    return datetime(2026, 10, day, hour, minute, tzinfo=VN)


def place(duration_min: int, arrival: datetime, priority: Priority, slots=(), ret: datetime | None = None):
    return schedule_order(
        duration_min=duration_min,
        expected_arrival=arrival,
        requested_return=ret or arrival + timedelta(hours=24),
        now=vn(0),
        slots=list(slots),
        priority=priority,
        shifts=SHIFTS,
    )


def test_normal_order_inside_day_shift_is_unchanged():
    p = place(180, vn(9), Priority.NORMAL)
    assert (p.line, p.start, p.end, p.shift_delayed) == (Line.A, vn(9), vn(12), None)


def test_normal_order_ending_exactly_at_day_end_fits():
    assert place(180, vn(19), Priority.NORMAL).start == vn(19)


def test_normal_order_past_day_end_moves_to_next_morning():
    p = place(180, vn(20), Priority.NORMAL)
    assert (p.start, p.end) == (vn(6, day=2), vn(9, day=2))
    assert p.shift_delayed == "đơn Thường chỉ chạy ca ngày 06:00–22:00"
    reason = placement_reason(p, VN)
    assert reason == (
        "Line A 06:00–09:00 02/10. Sẵn sàng 20:00 01/10 nhưng đơn Thường chỉ chạy ca ngày 06:00–22:00 → bắt đầu 06:00 02/10. "
        "Các line xong cùng lúc → chọn Line A. Kịp giờ trả 20:00 02/10."
    )


def test_normal_order_arriving_at_night_waits_for_day_start():
    p = place(60, vn(3), Priority.NORMAL)
    assert p.start == vn(6)
    assert "bắt đầu 06:00" in placement_reason(p, VN)


@pytest.mark.parametrize("priority", [Priority.URGENT, Priority.VIP])
def test_urgent_and_vip_may_run_on_night_shift(priority):
    p = place(180, vn(21), priority)
    assert (p.start, p.end, p.shift_delayed) == (vn(21), vn(0, day=2), None)


def test_normal_order_prefers_other_line_still_in_day_shift():
    slots = [Slot("WO-1", Line.A, vn(8), vn(20))]
    p = place(180, vn(9), Priority.NORMAL, slots)
    assert (p.line, p.start) == (Line.B, vn(9))


def test_both_lines_full_until_evening_push_normal_order_to_next_day():
    slots = [Slot("WO-1", Line.A, vn(8), vn(20)), Slot("WO-2", Line.B, vn(8), vn(21))]
    p = place(180, vn(9), Priority.NORMAL, slots, ret=vn(18))
    assert (p.line, p.start, p.sla_ok) == (Line.A, vn(6, day=2), False)
    assert "ca ngày" in placement_reason(p, VN)


def test_shift_move_skips_busy_slot_at_next_day_start():
    """Dời sang 06:00 hôm sau mà đầu ca đã có đơn → tìm tiếp khe trống, vẫn trong ca."""
    slots = [Slot("WO-1", Line.A, vn(6, day=2), vn(8, day=2)), Slot("WO-2", Line.B, vn(6, day=2), vn(10, day=2))]
    p = place(180, vn(20), Priority.NORMAL, slots)
    assert (p.line, p.start, p.end) == (Line.A, vn(8, day=2), vn(11, day=2))


def test_urgent_order_still_takes_night_slot_when_day_is_full():
    slots = [Slot("WO-1", Line.A, vn(6), vn(22)), Slot("WO-2", Line.B, vn(6), vn(22))]
    p = place(120, vn(9), Priority.URGENT, slots)
    assert (p.line, p.start) == (Line.A, vn(22))


def test_normal_order_longer_than_day_shift_is_unschedulable():
    with pytest.raises(UnschedulableError, match="ca ngày"):
        place(17 * 60, vn(6), Priority.NORMAL)


def test_without_shift_policy_line_runs_24_7():
    p = schedule_order(duration_min=180, expected_arrival=vn(21), requested_return=vn(23), now=vn(0), slots=[])
    assert p.start == vn(21)


def test_20_random_orders_never_overlap_and_normal_orders_stay_in_day_shift():
    rng = random.Random(54)
    slots: list[Slot] = []
    placed = []
    for i in range(20):
        arrival = vn(0) + timedelta(minutes=15 * rng.randint(0, 120))
        priority = rng.choice(list(Priority))
        p = place(15 * rng.randint(2, 24), arrival, priority, slots)
        slots.append(Slot(f"WO-{i}", p.line, p.start, p.end))
        placed.append((priority, p))
    assert not has_overlap(slots)
    for priority, p in placed:
        if priority == Priority.NORMAL:
            start, end = p.start.astimezone(VN), p.end.astimezone(VN)
            assert start.date() == end.date() and time(6) <= start.time() and end.time() <= time(22)


def test_incident_reschedule_keeps_normal_order_off_night_shift():
    """Line A dừng 18:00–21:00, Line B kín tới 21:30: đơn Thường không được chạy đêm → sáng hôm sau."""
    old_normal = Slot("N", Line.A, vn(18), vn(20))
    moves = reschedule(
        affected=[
            RescheduleCandidate("N", Priority.NORMAL, vn(23), old=old_normal, expected_arrival=vn(18)),
        ],
        fixed=[Slot("U", Line.B, vn(17), vn(21, 30))],
        downtimes=[Incident(Line.A, vn(18), 180)],
        now=vn(17),
        shifts=SHIFTS,
    )
    (m,) = moves
    assert (m.new.line, m.new.start) == (Line.A, vn(6, day=2))


def test_policy_from_repo_config(config):
    policy = ShiftPolicy.from_config(config.raw, VN)
    assert policy == SHIFTS


def test_missing_shifts_means_24_7(config):
    raw = {**config.raw, "lines": {}}
    assert ShiftPolicy.from_config(raw, VN) is None


@pytest.mark.parametrize(
    "shifts",
    [
        {"day": {"start": "22:00", "end": "06:00"}},  # qua nửa đêm
        {"day": {"start": "6h", "end": "22:00"}},
        {"day": {"start": "06:00", "end": "22:00"}, "night_priorities": ["EMERGENCY"]},
        {"night_priorities": ["VIP"]},
    ],
)
def test_invalid_shifts_rejected_when_loading_config(config, shifts):
    raw = {**config.raw, "lines": {"shifts": shifts}}
    with pytest.raises(ConfigError, match="lines.shifts|day_start"):
        ThroughputConfig.from_dict(raw)
