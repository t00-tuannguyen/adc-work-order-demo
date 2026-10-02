"""ADC-003 — Kế hoạch kiểm thử."""

import random
from datetime import UTC, timedelta, timezone

import pytest

from src.modules.scheduling import Slot, has_overlap, placement_reason, schedule_order
from src.modules.types import Line
from tests.conftest import at


def test_two_empty_lines_pick_line_a_from_arrival():
    p = schedule_order(duration_min=180, expected_arrival=at(9), requested_return=at(16), now=at(8), slots=[])
    assert (p.line, p.start, p.end, p.sla_ok) == (Line.A, at(9), at(12), True)


def test_earliest_start_is_now_when_goods_already_arrived():
    p = schedule_order(duration_min=60, expected_arrival=at(7), requested_return=at(16), now=at(8), slots=[])
    assert p.start == at(8)


def test_capacity_conflict_moves_to_line_b():
    slots = [Slot("WO-1", Line.A, at(8), at(14))]
    p = schedule_order(duration_min=90, expected_arrival=at(9), requested_return=at(16), now=at(8), slots=slots)
    assert (p.line, p.start) == (Line.B, at(9))


def test_fits_in_gap_on_line_a():
    slots = [
        Slot("WO-1", Line.A, at(8), at(9)),
        Slot("WO-2", Line.A, at(11), at(12)),
        Slot("WO-3", Line.B, at(8), at(15)),
    ]
    p = schedule_order(duration_min=120, expected_arrival=at(8), requested_return=at(16), now=at(8), slots=slots)
    assert (p.line, p.start, p.end) == (Line.A, at(9), at(11))


def test_no_line_meets_return_time_flags_sla_risk():
    slots = [Slot("WO-1", Line.A, at(8), at(15)), Slot("WO-2", Line.B, at(8), at(15, 30))]
    p = schedule_order(duration_min=180, expected_arrival=at(8), requested_return=at(16), now=at(8), slots=slots)
    assert (p.line, p.start, p.sla_ok) == (Line.A, at(15), False)


def test_20_random_orders_never_overlap():
    rng = random.Random(42)
    slots: list[Slot] = []
    for i in range(20):
        arrival = at(6) + timedelta(minutes=15 * rng.randint(0, 40))
        p = schedule_order(
            duration_min=15 * rng.randint(2, 16),
            expected_arrival=arrival,
            requested_return=arrival + timedelta(hours=8),
            now=at(6),
            slots=slots,
        )
        slots.append(Slot(f"WO-{i}", p.line, p.start, p.end))
    assert not has_overlap(slots)


def test_single_line_mode_only_uses_line_a():
    p = schedule_order(duration_min=60, requested_return=at(16), now=at(8), slots=[], lines=(Line.A,))
    assert p.line == Line.A


def test_rejects_non_positive_duration():
    with pytest.raises(ValueError):
        schedule_order(duration_min=0, requested_return=at(16), now=at(8), slots=[])


def test_same_input_same_result():
    slots = [Slot("WO-1", Line.A, at(8), at(12)), Slot("WO-2", Line.B, at(9), at(11))]
    kwargs = dict(duration_min=90, expected_arrival=at(8), requested_return=at(16), now=at(8), slots=slots)
    assert schedule_order(**kwargs) == schedule_order(**kwargs)


def test_order_longer_than_a_day_runs_continuously():
    """Giả định MVP: line chạy 24/7 — đơn dài không bị cắt hay dời sang ca sau."""
    p = schedule_order(
        duration_min=26 * 60, expected_arrival=at(20), requested_return=at(23, day=2), now=at(8), slots=[]
    )
    assert (p.start, p.end) == (at(20), at(22, day=2))


def test_placement_keeps_option_of_each_line():
    slots = [Slot("WO-1", Line.A, at(8), at(14))]
    p = schedule_order(duration_min=90, expected_arrival=at(9), requested_return=at(16), now=at(8), slots=slots)
    assert [(o.line, o.start, o.end) for o in p.options] == [(Line.A, at(14), at(15, 30)), (Line.B, at(9), at(10, 30))]
    assert p.earliest == at(9)


def test_reason_capacity_conflict():
    slots = [Slot("WO-1", Line.A, at(8), at(14))]
    p = schedule_order(duration_min=90, expected_arrival=at(9), requested_return=at(16), now=at(8), slots=slots)
    assert placement_reason(p, UTC) == (
        "Line B 09:00–10:30. Line A chỉ trống từ 14:00 → chọn Line B. Kịp giờ trả 16:00."
    )


def test_reason_tie_uses_local_time():
    p = schedule_order(duration_min=180, expected_arrival=at(2), requested_return=at(9), now=at(1), slots=[])
    assert placement_reason(p, timezone(timedelta(hours=7))) == (
        "Line A 09:00–12:00. Các line xong cùng lúc → chọn Line A. Kịp giờ trả 16:00."
    )


def test_reason_sla_risk_numbers_match_placement():
    slots = [Slot("WO-1", Line.A, at(8), at(15)), Slot("WO-2", Line.B, at(8), at(15, 30))]
    p = schedule_order(duration_min=180, expected_arrival=at(8), requested_return=at(16), now=at(8), slots=slots)
    assert placement_reason(p, UTC) == (
        "Line A 15:00–18:00. Line A bận đến 15:00. Line B chỉ trống từ 15:30 → chọn Line A. "
        "Trễ giờ trả 16:00 120 phút → SLA_RISK."
    )


def test_reason_single_line_mode():
    p = schedule_order(duration_min=60, requested_return=at(16), now=at(8), slots=[], lines=(Line.A,))
    assert placement_reason(p, UTC) == "Line A 08:00–09:00. Kịp giờ trả 16:00."


# ---- BR-15: xếp tay ----


def _manual(start, busy=(), **kw):
    from src.modules.scheduling import manual_placement

    args = dict(
        work_order_id="W",
        line=Line.A,
        start=start,
        duration_min=120,
        expected_arrival=at(9),
        requested_return=at(16),
        now=at(8),
        busy=list(busy),
        tz=UTC,
    )
    return manual_placement(**{**args, **kw})


def test_manual_placement_keeps_chosen_time_and_ignores_own_old_slot():
    p = _manual(at(10, 30).replace(second=15), busy=[Slot("W", Line.A, at(10), at(12))])
    assert (p.slot.start, p.slot.end, p.sla_ok) == (at(10, 30), at(12, 30), True)  # bỏ giây


def test_manual_placement_conflict_names_downtime_and_other_line_is_free():
    from src.modules.scheduling import SlotConflictError

    busy = [Slot("__downtime__", Line.A, at(11), at(13))]
    with pytest.raises(SlotConflictError, match="trùng khung dừng sự cố"):
        _manual(at(10), busy=busy, labels={"__downtime__": "khung dừng sự cố"})
    assert _manual(at(10), busy=busy, line=Line.B).slot.line == Line.B


def test_manual_placement_late_is_not_an_error():
    p = _manual(at(15))
    assert p.sla_ok is False and "Trễ giờ trả" in p.reason and "60 phút" in p.reason
