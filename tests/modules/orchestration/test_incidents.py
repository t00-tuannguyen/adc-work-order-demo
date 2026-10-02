"""ADC-004 T-032 — phát hiện đơn bị ảnh hưởng trên lịch ACTIVE + đề xuất chờ duyệt (FR 07)."""

from datetime import timedelta

from src.modules.identity import Role, User, UserStatus
from src.modules.orchestration import WorkOrderState
from src.modules.orchestration.incidents import find_affected
from src.modules.orchestration.planning import current_downtimes, downtime
from src.modules.scheduling import Incident, LineIncident, ScheduleSlot
from src.modules.types import Line
from tests.conftest import at

S = WorkOrderState
LINE_A_DOWN = Incident(Line.A, at(9), 180)  # 09:00–12:00


def row(wid: str, line: Line, start: int, end: int) -> ScheduleSlot:
    return ScheduleSlot(plan_version_id=1, work_order_id=wid, line=line, start_at=at(start), end_at=at(end))


ROWS = [
    row("WO-1", Line.A, 7, 9),  # xong đúng lúc dừng
    row("WO-2", Line.A, 8, 10),  # đang chiếu dở lúc dừng
    row("WO-3", Line.A, 10, 11),
    row("WO-4", Line.A, 11, 13),
    row("WO-5", Line.B, 9, 12),  # line khác
    row("WO-6", Line.A, 9, 10),
]


def states(**override: S) -> dict[str, S]:
    return {r.work_order_id: override.get(r.work_order_id.replace("-", "_"), S.SCHEDULED) for r in ROWS}


def ids(found) -> list[str]:
    return [a.row.work_order_id for a in found]


def test_affected_match_hand_calculation_sorted_by_start():
    assert ids(find_affected(ROWS, states(), [LINE_A_DOWN], now=at(8))) == ["WO-2", "WO-6", "WO-3", "WO-4"]


def test_in_progress_counts_but_irradiated_orders_are_skipped():
    found = find_affected(
        ROWS, states(WO_2=S.IN_IRRADIATION, WO_6=S.COMPLETED_IRRADIATION, WO_3=S.CLOSED), [LINE_A_DOWN], now=at(8)
    )
    assert ids(found) == ["WO-2", "WO-4"]
    assert found[0].state == S.IN_IRRADIATION


def test_both_lines_down_and_past_or_zero_downtime():
    both = [LINE_A_DOWN, Incident(Line.B, at(11), 60)]
    assert ids(find_affected(ROWS, states(), both, now=at(8))) == ["WO-2", "WO-5", "WO-6", "WO-3", "WO-4"]
    assert find_affected(ROWS, states(), [LINE_A_DOWN], now=at(12)) == []
    assert find_affected(ROWS, states(), [Incident(Line.A, at(9), 0)], now=at(8)) == []


def test_current_downtimes_use_actual_end_and_skip_finished(db):
    user = User(
        google_sub="s", email="p@adc.test", email_domain="adc.test", role=Role.PLANNER, status=UserStatus.ACTIVE
    )
    db.add(user)
    db.flush()
    early = LineIncident(line=Line.A, start_at=at(9), est_downtime_min=180, created_by=user.id)
    late = LineIncident(line=Line.B, start_at=at(10), est_downtime_min=60, created_by=user.id)
    late.actual_end_at = at(14, 30)  # hồi phục muộn hơn dự kiến
    db.add_all([early, late])
    db.commit()
    assert downtime(early) == LINE_A_DOWN
    assert downtime(late) == Incident(Line.B, at(10), 270)
    assert current_downtimes(db, now=at(8)) == [LINE_A_DOWN, Incident(Line.B, at(10), 270)]
    assert current_downtimes(db, now=at(13)) == [Incident(Line.B, at(10), 270)]
    late.actual_end_at = at(10, 0) + timedelta(seconds=30)
    assert downtime(late).est_downtime_min == 1  # lẻ giây → tròn lên
