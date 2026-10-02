"""ADC-005 T-036 — luật rủi ro đơn mới OK / WARN / BLOCK (BR-07), lõi deterministic."""

from datetime import UTC, time

import pytest

from src.modules.risk import RiskLevel, assess_new_order
from src.modules.scheduling import Incident, RescheduleCandidate, ShiftPolicy, Slot, UnschedulableError, downtime_slot
from src.modules.types import Line, Priority
from tests.conftest import at

NOW = at(8)


def busy_order(wid, line, start, end, priority=Priority.NORMAL, ret=None):
    slot = Slot(wid, line, start, end)
    return slot, RescheduleCandidate(wid, priority, ret or at(16), old=slot)


def assess(busy=(), bumpable=(), *, duration=180, priority=Priority.VIP, ret=at(12), arrival=at(8), now=NOW, **kw):
    return assess_new_order(
        work_order_id="new",
        duration_min=duration,
        priority=priority,
        requested_return=ret,
        expected_arrival=arrival,
        now=now,
        busy=list(busy),
        bumpable=list(bumpable),
        tz=UTC,
        **kw,
    )


def test_ok_when_free_slot_meets_return_time():
    r = assess()
    assert (r.level, r.earliest_feasible_return, r.moves) == (RiskLevel.OK, at(11), ())
    assert r.reasons == (
        "Line A 08:00–11:00. Các line xong cùng lúc → chọn Line A. Kịp giờ trả 12:00. Không ảnh hưởng đơn khác.",
    )


def test_ok_during_incident_uses_other_line():
    """TC: đơn mới trong sự cố, vẫn kịp và không ảnh hưởng đơn khác → OK."""
    down = downtime_slot(Incident(Line.A, at(8), 180))
    r = assess([down])
    assert (r.level, r.placement.line, r.placement.start) == (RiskLevel.OK, Line.B, at(8))


def test_warn_when_on_time_only_by_pushing_lower_priority_late():
    """TC: kịp nhưng đẩy đơn khác trễ → WARN, reasons nêu đơn bị đẩy."""
    a, ca = busy_order("n1", Line.A, at(8), at(15))
    b, cb = busy_order("n2", Line.B, at(8), at(15, 30))
    r = assess([a, b], [ca, cb], labels={"n1": "Bột ớt"})
    assert r.level == RiskLevel.WARN
    assert (r.placement.line, r.placement.start, r.earliest_feasible_return) == (Line.A, at(8), at(11))
    [m] = r.moves
    assert (m.candidate.work_order_id, m.new.line, m.new.start, m.sla_ok) == ("n1", Line.A, at(11), False)
    assert r.reasons[0] == "Kịp giờ trả 12:00 chỉ khi đẩy lùi 1 đơn ưu tiên thấp hơn → cần duyệt nhận đơn."
    assert r.reasons[-1] == "Đẩy Bột ớt (Thường): Line A 08:00 → Line A 11:00–18:00, trễ giờ trả 16:00 120 phút."


def test_warn_even_if_pushed_order_stays_on_time():
    """Đẩy đơn khác là đổi lịch đã hứa (PRIORITY_OVERRIDE) → vẫn cần duyệt dù đơn đó còn kịp."""
    a, ca = busy_order("n1", Line.A, at(8), at(10), ret=at(20))
    b, cb = busy_order("n2", Line.B, at(8), at(11), priority=Priority.VIP)
    r = assess([a, b], [ca, cb], duration=180, ret=at(11, 30))
    assert r.level == RiskLevel.WARN
    [m] = r.moves
    assert (m.candidate.work_order_id, m.sla_ok) == ("n1", True)
    assert r.reasons[-1].endswith("vẫn kịp giờ trả 20:00.")


def test_block_when_late_and_nobody_to_push():
    """TC: không thể kịp → BLOCK kèm giờ sớm nhất. Đơn Thường không đẩy được đơn Thường khác."""
    a, ca = busy_order("n1", Line.A, at(8), at(15))
    b, cb = busy_order("n2", Line.B, at(8), at(15, 30))
    r = assess([a, b], [ca, cb], priority=Priority.NORMAL, ret=at(16))
    assert (r.level, r.earliest_feasible_return, r.moves) == (RiskLevel.BLOCK, at(18), ())
    assert r.reasons[0] == "Không kịp giờ trả 16:00: xếp vào khe trống sớm nhất xong 18:00 (trễ 120 phút)."


def test_block_when_pushing_still_late():
    a, ca = busy_order("n1", Line.A, at(8), at(15))
    b, cb = busy_order("n2", Line.B, at(8), at(15, 30))
    r = assess([a, b], [ca, cb], ret=at(10))  # VIP 3 giờ, giờ trả 10:00 → xong sớm nhất 11:00 kể cả đẩy
    assert (r.level, r.earliest_feasible_return) == (RiskLevel.BLOCK, at(18))
    assert r.reasons[-1] == "Kể cả đẩy lùi đơn ưu tiên thấp hơn vẫn chỉ xong 11:00, trễ giờ trả 60 phút."


def test_started_or_higher_priority_orders_are_never_pushed():
    started, cs = busy_order("run", Line.A, at(7), at(15))  # đã bắt đầu trước now
    urgent, cu = busy_order("urg", Line.B, at(8), at(15), priority=Priority.URGENT)
    r = assess([started, urgent], [cs, cu], priority=Priority.URGENT, ret=at(12))
    assert r.level == RiskLevel.BLOCK


def test_pushed_urgent_order_may_push_normal_order_in_turn():
    """Đơn bị đẩy xếp lại theo BR-05 như tái lập lịch sự cố — đơn Khẩn bị đẩy lại đẩy tiếp đơn Thường."""
    u, cu = busy_order("urg", Line.A, at(8), at(11), priority=Priority.URGENT, ret=at(14))
    n, cn = busy_order("nor", Line.A, at(11), at(14), ret=at(23))
    b, cb = busy_order("vip2", Line.B, at(8), at(20), priority=Priority.VIP)
    r = assess([u, n, b], [cu, cn, cb], duration=180, ret=at(11, 30))
    assert r.level == RiskLevel.WARN
    moved = {m.candidate.work_order_id: (m.new.start, m.sla_ok) for m in r.moves}
    assert moved == {"urg": (at(11), True), "nor": (at(14), True)}


def test_day_shift_applies_to_new_order():
    shifts = ShiftPolicy(tz=UTC, day_start=time(6), day_end=time(22))
    with pytest.raises(UnschedulableError):
        assess(duration=17 * 60, priority=Priority.NORMAL, ret=at(23, day=2), shifts=shifts)
    r = assess(duration=180, priority=Priority.NORMAL, arrival=at(20), now=at(20), ret=at(23), shifts=shifts)
    assert (r.level, r.placement.start) == (RiskLevel.BLOCK, at(6, day=2))
