"""Kiểm tra rủi ro đơn mới — BR-07, ADC-005 (T-036). Lõi deterministic, không DB/LLM.

Mô phỏng chèn đơn vào lịch hiện hành (`busy` = slot ACTIVE + đề xuất đang chờ duyệt + khung dừng):
1. Khe trống sớm nhất (`schedule_order`, như xếp lịch thường) kịp giờ trả → OK.
2. Trễ → thử đẩy lùi đơn ưu tiên thấp hơn chưa bắt đầu (`bumpable`); đơn bị đẩy xếp lại bằng `reschedule`
   (BR-05, có thể đẩy tiếp đơn thấp hơn nữa như tái lập lịch sự cố). Nhờ đẩy mà kịp → WARN: nhận được nhưng cần
   duyệt, vì đổi lịch của đơn khác (dù đơn đó vẫn kịp hay bị trễ — `reasons` nói rõ).
3. Đẩy rồi vẫn trễ (hoặc không có ai để đẩy) → BLOCK, kèm giờ xong sớm nhất khi xếp vào khe trống.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, tzinfo

from src.modules.risk.levels import RiskLevel
from src.modules.scheduling import (
    Move,
    Placement,
    RescheduleCandidate,
    ShiftPolicy,
    Slot,
    placement_reason,
    reschedule,
    schedule_order,
)
from src.modules.types import PRIORITY_LABEL, PRIORITY_RANK, Priority


@dataclass(frozen=True)
class RiskAssessment:
    level: RiskLevel
    reasons: tuple[str, ...]
    earliest_feasible_return: datetime
    # Slot của đơn mới: theo phương án OK / WARN; với BLOCK là khe trống sớm nhất (không xếp)
    placement: Placement
    moves: tuple[Move, ...] = ()  # đơn bị đẩy lùi (WARN), theo thứ tự xử lý


def _minutes(delta: timedelta) -> int:
    return int(delta / timedelta(minutes=1))


def assess_new_order(
    *,
    work_order_id: str,
    duration_min: int,
    priority: Priority | None,
    requested_return: datetime,
    now: datetime,
    busy: Sequence[Slot],
    bumpable: Sequence[RescheduleCandidate] = (),
    expected_arrival: datetime | None = None,
    shifts: ShiftPolicy | None = None,
    tz: tzinfo,
    labels: Mapping[str, str] | None = None,
) -> RiskAssessment:
    """Mức rủi ro của đơn mới. `bumpable`: đơn được phép đẩy (slot cũ nằm trong `busy`); chỉ đơn ưu tiên thấp
    hơn đơn mới và chưa bắt đầu (slot bắt đầu ≥ now) bị xét. Đơn dài hơn cả ca ngày → UnschedulableError."""
    labels = labels or {}

    def place(slots: Sequence[Slot]) -> Placement:
        return schedule_order(
            duration_min=duration_min,
            requested_return=requested_return,
            expected_arrival=expected_arrival,
            now=now,
            slots=slots,
            priority=priority,
            shifts=shifts,
        )

    free = place(busy)
    first_day = free.earliest.astimezone(tz).date()

    def hm(t: datetime) -> str:
        """Như `placement_reason`: khác ngày với giờ sẵn sàng của đơn thì kèm ngày."""
        local = t.astimezone(tz)
        return local.strftime("%H:%M") if local.date() == first_day else local.strftime("%H:%M %d/%m")

    if free.sla_ok:
        return RiskAssessment(
            level=RiskLevel.OK,
            reasons=(f"{placement_reason(free, tz)} Không ảnh hưởng đơn khác.",),
            earliest_feasible_return=free.end,
            placement=free,
        )

    rank = PRIORITY_RANK[priority or Priority.NORMAL]
    lower = {b.work_order_id: b for b in bumpable if b.old and b.old.start >= now and PRIORITY_RANK[b.priority] > rank}
    late_min = _minutes(free.end - requested_return)
    block_reasons = [
        f"Không kịp giờ trả {hm(requested_return)}: xếp vào khe trống sớm nhất xong {hm(free.end)} "
        f"(trễ {late_min} phút).",
        placement_reason(free, tz),
    ]
    if lower:
        bumped = place([s for s in busy if s.work_order_id not in lower])
        victims = [
            b
            for b in lower.values()
            if b.old and b.old.line == bumped.line and b.old.overlaps(bumped.start, bumped.end)
        ]
        if bumped.sla_ok and victims:
            out = {v.work_order_id for v in victims}
            new_slot = Slot(work_order_id, bumped.line, bumped.start, bumped.end)
            moves = reschedule(
                affected=victims,
                fixed=[*(s for s in busy if s.work_order_id not in out), new_slot],
                downtimes=(),
                now=now,
                bumpable=[b for b in bumpable if b.work_order_id not in out],
                shifts=shifts,
            )
            reasons = [
                f"Kịp giờ trả {hm(requested_return)} chỉ khi đẩy lùi {len(moves)} đơn ưu tiên thấp hơn → cần duyệt "
                "nhận đơn.",
                placement_reason(bumped, tz),
            ]
            for m in moves:
                c = m.candidate
                who = f"{labels.get(c.work_order_id, c.work_order_id)} ({PRIORITY_LABEL[c.priority]})"
                moved = (
                    f"Line {m.old.line.value} {hm(m.old.start)} → Line {m.new.line.value} {hm(m.new.start)}–"
                    f"{hm(m.new.end)}"
                )
                if m.sla_ok:
                    sla = f"vẫn kịp giờ trả {hm(c.requested_return)}"
                else:
                    sla = f"trễ giờ trả {hm(c.requested_return)} {_minutes(m.new.end - c.requested_return)} phút"
                reasons.append(f"Đẩy {who}: {moved}, {sla}.")
            return RiskAssessment(
                level=RiskLevel.WARN,
                reasons=tuple(reasons),
                earliest_feasible_return=bumped.end,
                placement=bumped,
                moves=tuple(moves),
            )
        if bumped.end < free.end:
            block_reasons.append(
                f"Kể cả đẩy lùi đơn ưu tiên thấp hơn vẫn chỉ xong {hm(bumped.end)}, trễ giờ trả "
                f"{_minutes(bumped.end - requested_return)} phút."
            )
    return RiskAssessment(
        level=RiskLevel.BLOCK,
        reasons=tuple(block_reasons),
        earliest_feasible_return=free.end,
        placement=free,
    )
