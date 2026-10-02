"""ADC-004 — phát hiện đơn bị ảnh hưởng (FR 07), thứ tự ưu tiên (FR 09), tái lập lịch (FR 08, T-033)."""

import time
from datetime import timedelta, timezone

import pytest

from src.modules.scheduling import (
    AffectedOutcome,
    Incident,
    RescheduleCandidate,
    Slot,
    compact,
    downtime_slot,
    find_affected_slots,
    has_overlap,
    incident_explanation,
    move_reason,
    reschedule,
    reschedule_order,
    summarize,
)
from src.modules.types import Line, Priority
from tests.conftest import at

SLOTS = [
    Slot("WO-1", Line.A, at(7), at(9)),  # kết thúc đúng lúc dừng → không ảnh hưởng
    Slot("WO-2", Line.A, at(8), at(10)),
    Slot("WO-3", Line.A, at(10), at(11)),
    Slot("WO-4", Line.A, at(12), at(13)),  # bắt đầu đúng lúc hồi phục → không ảnh hưởng
    Slot("WO-5", Line.B, at(9), at(12)),  # line khác
]
LINE_A_DOWN = Incident(line=Line.A, start_at=at(9), est_downtime_min=180)  # 09:00–12:00


def test_affected_orders_match_hand_calculation():
    assert [s.work_order_id for s in find_affected_slots(SLOTS, LINE_A_DOWN, now=at(8))] == ["WO-2", "WO-3"]


def test_zero_downtime_affects_nothing():
    assert find_affected_slots(SLOTS, Incident(Line.A, at(9), 0), now=at(8)) == []


def test_incident_fully_in_past_affects_nothing():
    assert find_affected_slots(SLOTS, LINE_A_DOWN, now=at(13)) == []


def test_reschedule_order_vip_then_urgent_then_normal_then_return_time():
    c = [
        RescheduleCandidate("N1", Priority.NORMAL, at(12)),
        RescheduleCandidate("V2", Priority.VIP, at(18)),
        RescheduleCandidate("U1", Priority.URGENT, at(14)),
        RescheduleCandidate("V1", Priority.VIP, at(15)),
    ]
    assert [x.work_order_id for x in reschedule_order(c)] == ["V1", "V2", "U1", "N1"]


# --- T-033: tái lập lịch theo ưu tiên + line thay thế (FR 08, FR 09) ---

VN = timezone(timedelta(hours=7))


def cand(wid, priority, line, start, end, ret, arrival=None) -> RescheduleCandidate:
    return RescheduleCandidate(wid, priority, at(ret), Slot(wid, line, at(start), at(end)), arrival and at(arrival))


def table(moves) -> list[tuple]:
    return [
        (m.candidate.work_order_id, m.new.line, m.new.start.hour, m.new.end.hour, m.outcome, m.sla_ok, m.bumped)
        for m in moves
    ]


def check_no_overlap(moves, fixed, downtimes=(LINE_A_DOWN,)):
    moved = {m.candidate.work_order_id for m in moves}
    plan = [s for s in fixed if s.work_order_id not in moved] + [m.new for m in moves]
    assert not has_overlap(plan)
    for d in downtimes:
        assert not [s for s in plan if s.line == d.line and s.overlaps(d.start_at, d.end_at)]


def test_vip_bumps_unstarted_normal_on_alt_line_then_bumped_order_is_rescheduled():
    """A dừng 09–12. VIP đang chiếu dở sang B trước, đẩy lùi đơn Thường chưa bắt đầu trên B (priority override)."""
    v1 = cand("V1", Priority.VIP, Line.A, 8, 11, ret=12)
    n1 = cand("N1", Priority.NORMAL, Line.A, 11, 13, ret=17)
    n2 = cand("N2", Priority.NORMAL, Line.B, 10, 13, ret=14)
    fixed = [Slot("N3", Line.A, at(13), at(15)), Slot("U1", Line.B, at(8), at(10)), n2.old]
    moves = reschedule(affected=[n1, v1], fixed=fixed, downtimes=[LINE_A_DOWN], now=at(8), bumpable=[n2])
    assert table(moves) == [
        ("V1", Line.B, 10, 13, AffectedOutcome.MOVED_ALT_LINE, False, False),  # vẫn trễ nhưng sớm hơn 3 giờ
        ("N2", Line.B, 13, 16, AffectedOutcome.DELAYED, False, True),
        ("N1", Line.A, 15, 17, AffectedOutcome.DELAYED, True, False),  # sau khi A hồi phục, sau N3
    ]
    check_no_overlap(moves, fixed)


def test_vip_bumps_every_lower_priority_order_in_its_way():
    """VIP đẩy cả đơn Khẩn lẫn Thường chặn khe B 09–12. Khẩn xếp lại trước Thường; trễ vì không khe nào xong trước 13:00."""
    v = cand("V", Priority.VIP, Line.A, 9, 12, ret=12)
    u = cand("U", Priority.URGENT, Line.B, 9, 11, ret=13)
    n = cand("N", Priority.NORMAL, Line.B, 11, 13, ret=18)
    moves = reschedule(affected=[v], fixed=[u.old, n.old], downtimes=[LINE_A_DOWN], now=at(9), bumpable=[u, n])
    assert table(moves) == [
        ("V", Line.B, 9, 12, AffectedOutcome.MOVED_ALT_LINE, True, False),
        ("U", Line.A, 12, 14, AffectedOutcome.MOVED_ALT_LINE, False, True),
        ("N", Line.B, 12, 14, AffectedOutcome.DELAYED, True, True),
    ]
    check_no_overlap(moves, [u.old, n.old])


def test_vip_and_urgent_take_alt_line_gap_before_normal():
    n1 = cand("N1", Priority.NORMAL, Line.A, 9, 10, ret=18)  # bắt đầu sớm hơn nhưng ưu tiên thấp hơn
    v1 = cand("V1", Priority.VIP, Line.A, 10, 11, ret=12)
    fixed = [Slot("X", Line.B, at(8), at(10)), Slot("Y", Line.B, at(11), at(14))]
    moves = reschedule(affected=[n1, v1], fixed=fixed, downtimes=[LINE_A_DOWN], now=at(9))
    assert table(moves) == [
        ("V1", Line.B, 10, 11, AffectedOutcome.MOVED_ALT_LINE, True, False),
        ("N1", Line.A, 12, 13, AffectedOutcome.DELAYED, True, False),
    ]
    check_no_overlap(moves, fixed)


def test_normal_never_bumps_and_started_or_on_time_orders_are_not_bumped():
    n1 = cand("N1", Priority.NORMAL, Line.A, 9, 11, ret=10)  # Thường trễ → không được đẩy ai
    v1 = cand("V1", Priority.VIP, Line.A, 11, 12, ret=19)  # VIP kịp giờ → không cần đẩy
    started = cand("S", Priority.NORMAL, Line.B, 7, 10, ret=20)  # đã bắt đầu trước now
    later = cand("L", Priority.NORMAL, Line.B, 10, 20, ret=22)
    fixed = [started.old, later.old]
    moves = reschedule(affected=[n1, v1], fixed=fixed, downtimes=[LINE_A_DOWN], now=at(9), bumpable=[started, later])
    assert not any(m.bumped for m in moves)
    assert table(moves) == [
        ("V1", Line.A, 12, 13, AffectedOutcome.DELAYED, True, False),
        ("N1", Line.A, 13, 15, AffectedOutcome.DELAYED, False, False),
    ]


def test_both_lines_down_everything_waits_for_recovery_and_is_late():
    b_down = Incident(Line.B, at(9), 240)  # B dừng 09–13
    v1 = cand("V1", Priority.VIP, Line.A, 9, 10, ret=11)
    u1 = cand("U1", Priority.URGENT, Line.B, 9, 11, ret=12)
    moves = reschedule(affected=[u1, v1], fixed=[], downtimes=[LINE_A_DOWN, b_down], now=at(9))
    assert table(moves) == [
        ("V1", Line.A, 12, 13, AffectedOutcome.DELAYED, False, False),
        ("U1", Line.A, 13, 15, AffectedOutcome.MOVED_ALT_LINE, False, False),  # A 13–15 hòa B 13–15 → Line A
    ]
    check_no_overlap(moves, [], [LINE_A_DOWN, b_down])
    assert all(not m.sla_ok for m in moves)


def test_arrival_and_now_bound_new_start():
    v1 = cand("V1", Priority.VIP, Line.A, 9, 10, ret=20, arrival=9)
    [m] = reschedule(affected=[v1], fixed=[Slot("B1", Line.B, at(9), at(10))], downtimes=[LINE_A_DOWN], now=at(9, 30))
    assert (m.new.line, m.new.start, m.new.end) == (Line.B, at(10), at(11))


def test_reschedule_is_deterministic():
    v1 = cand("V1", Priority.VIP, Line.A, 8, 11, ret=12)
    n1 = cand("N1", Priority.NORMAL, Line.A, 11, 13, ret=17)
    n2 = cand("N2", Priority.NORMAL, Line.B, 10, 13, ret=14)
    args = dict(affected=[n1, v1], fixed=[n2.old], downtimes=[LINE_A_DOWN], now=at(8), bumpable=[n2])
    assert reschedule(**args) == reschedule(**args)


def test_missing_old_slot_is_rejected():
    with pytest.raises(ValueError):
        reschedule(affected=[RescheduleCandidate("X", Priority.VIP, at(12))], fixed=[], downtimes=[], now=at(8))


def test_reschedule_under_ten_seconds_for_large_plan():
    """TC "Phương án < 10 giây" — 150 đơn bị ảnh hưởng, 150 đơn Thường đẩy được trên line còn lại."""
    day_down = Incident(Line.A, at(0), 24 * 60)
    affected = [
        RescheduleCandidate(
            f"A{i:03}",
            [Priority.VIP, Priority.URGENT, Priority.NORMAL][i % 3],
            at(1) + timedelta(minutes=10 * i),
            Slot(f"A{i:03}", Line.A, at(0) + timedelta(minutes=9 * i), at(0) + timedelta(minutes=9 * i + 9)),
        )
        for i in range(150)
    ]
    bumpable = [
        RescheduleCandidate(
            f"B{i:03}",
            Priority.NORMAL,
            at(23, day=2),
            Slot(f"B{i:03}", Line.B, at(1) + timedelta(minutes=9 * i), at(1) + timedelta(minutes=9 * i + 9)),
        )
        for i in range(150)
    ]
    t0 = time.perf_counter()
    moves = reschedule(
        affected=affected, fixed=[b.old for b in bumpable], downtimes=[day_down], now=at(0), bumpable=bumpable
    )
    assert time.perf_counter() - t0 < 10
    check_no_overlap(moves, [b.old for b in bumpable], [day_down])


def test_downtime_slot_and_reasons_in_local_time():
    assert downtime_slot(LINE_A_DOWN) == Slot("__downtime__", Line.A, at(9), at(12))
    v1 = cand("V1", Priority.VIP, Line.A, 8, 11, ret=12)
    n1 = cand("N1", Priority.NORMAL, Line.A, 11, 13, ret=17)
    n2 = cand("N2", Priority.NORMAL, Line.B, 10, 13, ret=14)
    fixed = [Slot("N3", Line.A, at(13), at(15)), Slot("U1", Line.B, at(8), at(10)), n2.old]
    moves = reschedule(affected=[n1, v1], fixed=fixed, downtimes=[LINE_A_DOWN], now=at(8), bumpable=[n2])
    assert move_reason(moves[0], VN).startswith("Line A dừng → Line B 17:00–20:00.")
    assert move_reason(moves[1], VN).startswith("Nhường Line B cho đơn ưu tiên cao hơn đang trễ (priority override) →")
    text = incident_explanation(Line.A, at(9), at(12), [summarize(m, m.candidate.work_order_id) for m in moves], VN)
    assert text.splitlines() == [
        # N1 xong lúc 00:00 hôm sau → mọi mốc kèm ngày
        "Line A dừng 16:00–19:00 01/10 (dự kiến): 3 đơn phải xếp lại, theo thứ tự VIP → Khẩn → Thường rồi giờ trả sớm hơn.",
        "- V1 (VIP): Line A 15:00–18:00 01/10 → Line B 17:00–20:00 01/10, trễ giờ trả 19:00 01/10 60 phút → SLA_RISK.",
        "- N2 (Thường) bị đẩy lùi nhường đơn ưu tiên cao hơn: Line B 17:00–20:00 01/10 → Line B 20:00–23:00 01/10, "
        "trễ giờ trả 21:00 01/10 120 phút → SLA_RISK.",
        "- N1 (Thường): Line A 18:00–20:00 01/10 → Line A 22:00 01/10–00:00 02/10, kịp giờ trả 00:00 02/10.",
        "2 đơn trễ giờ trả cần kinh doanh báo khách (escalation). Phương án chờ duyệt, lịch đang chạy chưa đổi.",
    ]
    assert incident_explanation(Line.A, at(9), at(12), [], VN, resolved=True) == (
        "Line A dừng 16:00–19:00 (đã hồi phục): không có đơn bị ảnh hưởng."
    )


# --- T-058: dồn trái sau sự cố (ADR-0011) ---


def test_compact_fills_gap_left_by_moved_order():
    """Kịch bản demo: đơn bị ảnh hưởng sang Line B → đơn phía sau trên Line A kéo sớm lấp khe sau hồi phục."""
    e = cand("E", Priority.NORMAL, Line.A, 7, 13, ret=23)  # chồng khung dừng A 9–12
    c = cand("C", Priority.NORMAL, Line.A, 13, 20, ret=23, arrival=7)  # không bị ảnh hưởng
    fixed_b = [Slot("X", Line.B, at(7), at(12)), Slot("Y", Line.B, at(12), at(16))]
    moves = reschedule(affected=[e], fixed=[*fixed_b, c.old], downtimes=[LINE_A_DOWN], now=at(8))
    assert table(moves) == [("E", Line.B, 16, 22, AffectedOutcome.MOVED_ALT_LINE, True, False)]

    out = compact(moves=moves, movable=[c], fixed=fixed_b, downtimes=[LINE_A_DOWN], now=at(8))
    assert table(out) == [
        ("E", Line.B, 16, 22, AffectedOutcome.MOVED_ALT_LINE, True, False),
        # Line A rảnh từ 12:00 (hồi phục) thay vì nghỉ tới 13:00
        ("C", Line.A, 12, 19, AffectedOutcome.PULLED_FORWARD, True, False),
    ]
    assert out[1].pulled and move_reason(out[1], VN).startswith(
        "Kéo sớm lấp khe trống sau sự cố → Line A 19:00 01/10–02:00 02/10."
    )
    check_no_overlap(out, fixed_b)


def test_compact_iterates_until_no_order_can_finish_earlier():
    """Kéo C sớm mở chỗ cho đơn bị ảnh hưởng E xong sớm hơn ở vòng sau; không đơn nào xong muộn hơn."""
    e = cand("E", Priority.VIP, Line.A, 8, 10, ret=23)
    c = cand("C", Priority.NORMAL, Line.A, 13, 15, ret=23, arrival=8)
    fixed_b = [Slot("X", Line.B, at(8), at(20))]
    moves = reschedule(affected=[e], fixed=[*fixed_b, c.old], downtimes=[LINE_A_DOWN], now=at(8))
    assert table(moves) == [("E", Line.A, 15, 17, AffectedOutcome.DELAYED, True, False)]

    out = compact(moves=moves, movable=[c], fixed=fixed_b, downtimes=[LINE_A_DOWN], now=at(8))
    assert table(out) == [
        ("E", Line.A, 14, 16, AffectedOutcome.DELAYED, True, False),
        ("C", Line.A, 12, 14, AffectedOutcome.PULLED_FORWARD, True, False),
    ]
    before = {m.candidate.work_order_id: m.new.end for m in moves} | {"C": c.old.end}
    assert all(m.new.end <= before[m.candidate.work_order_id] for m in out)
    check_no_overlap(out, fixed_b)


def test_compact_never_moves_started_orders_or_ties():
    e = cand("E", Priority.NORMAL, Line.A, 9, 10, ret=23)
    started = cand("S", Priority.NORMAL, Line.B, 7, 13, ret=23)  # bắt đầu trước now → không được kéo
    tie = cand("T", Priority.NORMAL, Line.B, 13, 14, ret=23, arrival=13)  # không thể sớm hơn (giờ hàng đến)
    moves = reschedule(affected=[e], fixed=[started.old, tie.old], downtimes=[LINE_A_DOWN], now=at(8))
    out = compact(moves=moves, movable=[started, tie], fixed=[], downtimes=[LINE_A_DOWN], now=at(8))
    assert [m.candidate.work_order_id for m in out] == ["E"]
