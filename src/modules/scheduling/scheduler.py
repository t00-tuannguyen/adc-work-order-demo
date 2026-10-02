"""Scheduler deterministic — greedy earliest feasible (ADC-003, ADR-0004).

- Giờ bắt đầu sớm nhất = max(expected_arrival, now) (BR-03).
- Mỗi line: khe trống đầu tiên đủ thời lượng; chọn line kết thúc sớm nhất, hòa → Line A.
- Kết thúc > requested_return → sla_ok = False (SLA_RISK, chuyển Risk — ADC-005).
- Không bao giờ tạo 2 slot chồng lấn trên cùng line (BR-04).
- Ca làm (T-054, chốt 01/10/2026): line chạy 24/7 nhưng ưu tiên ca ngày (mặc định 06:00–22:00 giờ địa phương);
  ca đêm chỉ cho đơn khẩn cấp (`night_priorities`, mặc định Khẩn + VIP). Đơn còn lại phải nằm trọn trong 1 ca
  ngày — không đủ chỗ thì dời sang đầu ca hôm sau, không cắt đôi lệnh. Cấu hình `lines.shifts` trong
  throughput.yaml; `shifts=None` = chạy 24/7 cho mọi đơn.
- Xếp tay (BR-15): Điều phối chọn line + giờ bắt đầu → `manual_placement` chỉ kiểm tra, không tự dời giờ.
"""

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, tzinfo

from src.modules.types import PRIORITY_LABEL, Line, Priority


class UnschedulableError(ValueError):
    """Đơn không bao giờ xếp được, vd đơn chỉ chạy ca ngày nhưng dài hơn cả ca (422)."""


class SlotConflictError(ValueError):
    """Giờ xếp tay chồng lên đơn khác / khung dừng trên cùng line (BR-04)."""


@dataclass(frozen=True)
class ShiftPolicy:
    """Ca ngày [day_start, day_end) theo giờ địa phương; ưu tiên trong `night_priorities` được chạy cả ca đêm."""

    tz: tzinfo
    day_start: time
    day_end: time
    night_priorities: frozenset[Priority] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if self.day_start >= self.day_end:
            raise ValueError("ca ngày phải có day_start < day_end (không qua nửa đêm)")

    @classmethod
    def from_config(cls, raw: dict, tz: tzinfo) -> "ShiftPolicy | None":
        """`lines.shifts` trong throughput.yaml → policy; không khai báo → None (24/7). Sai định dạng → ValueError."""
        data = (raw.get("lines") or {}).get("shifts")
        if data is None:
            return None
        try:
            day = data["day"]
            return cls(
                tz=tz,
                day_start=time.fromisoformat(day["start"]),
                day_end=time.fromisoformat(day["end"]),
                night_priorities=frozenset(Priority(p) for p in data.get("night_priorities") or ()),
            )
        except (KeyError, TypeError, ValueError) as e:
            raise ValueError(f"lines.shifts không hợp lệ: {e}") from e

    @property
    def day_length(self) -> timedelta:
        return datetime.combine(date.min, self.day_end) - datetime.combine(date.min, self.day_start)

    def day_only(self, priority: Priority | None) -> bool:
        return priority not in self.night_priorities

    def fit_day_shift(self, t: datetime, duration: timedelta) -> datetime:
        """Giờ sớm nhất ≥ t mà [t, t + duration) nằm trọn trong 1 ca ngày."""
        if duration > self.day_length:
            raise UnschedulableError(f"thời lượng {duration} dài hơn ca ngày {self.label}, đơn không được chạy ca đêm")
        local = t.astimezone(self.tz)
        start = datetime.combine(local.date(), self.day_start, self.tz)
        end = datetime.combine(local.date(), self.day_end, self.tz)
        if local < start:
            return start
        if local + duration <= end:
            return t
        return start + timedelta(days=1)

    @property
    def label(self) -> str:
        return f"{self.day_start:%H:%M}–{self.day_end:%H:%M}"


@dataclass(frozen=True)
class Slot:
    work_order_id: str
    line: Line
    start: datetime
    end: datetime

    def overlaps(self, start: datetime, end: datetime) -> bool:
        return self.start < end and start < self.end


@dataclass(frozen=True)
class LineOption:
    """Khe sớm nhất tìm được trên 1 line — giữ lại để giải thích vì sao chọn line này."""

    line: Line
    start: datetime
    end: datetime


@dataclass(frozen=True)
class Placement:
    line: Line
    start: datetime
    end: datetime
    sla_ok: bool
    earliest: datetime  # max(expected_arrival, now)
    requested_return: datetime
    options: tuple[LineOption, ...] = ()
    # Ca ngày đã đẩy giờ bắt đầu muộn hơn so với chạy 24/7 → ghi vào lý do xếp
    shift_delayed: str | None = None  # vd "đơn Thường chỉ chạy ca ngày 06:00–22:00"


def _first_gap(busy: Sequence[Slot], earliest: datetime, duration: timedelta) -> datetime:
    t = earliest
    for slot in busy:
        if slot.end <= t:
            continue
        if slot.start >= t + duration:
            break
        t = slot.end
    return t


def earliest_start_on_line(
    busy: Iterable[Slot],
    earliest: datetime,
    duration: timedelta,
    fit: Callable[[datetime, timedelta], datetime] | None = None,
) -> datetime:
    """Giờ bắt đầu sớm nhất ≥ `earliest` mà [start, start + duration) không chạm slot nào trong `busy`.

    `fit(t, duration)`: giờ sớm nhất ≥ t thỏa ràng buộc ca (vd `ShiftPolicy.fit_day_shift`). Lặp tới khi cả khe
    trống lẫn ca cùng thỏa — mỗi vòng t chỉ tăng nên luôn dừng.
    """
    ordered = sorted(busy, key=lambda s: (s.start, s.end))
    t = _first_gap(ordered, earliest, duration)
    while fit is not None and (shifted := fit(t, duration)) != t:
        t = _first_gap(ordered, shifted, duration)
    return t


def schedule_order(
    *,
    duration_min: int,
    requested_return: datetime,
    now: datetime,
    slots: Sequence[Slot],
    expected_arrival: datetime | None = None,
    lines: Sequence[Line] = (Line.A, Line.B),
    priority: Priority | None = None,
    shifts: ShiftPolicy | None = None,
) -> Placement:
    if duration_min <= 0:
        raise ValueError("duration_min phải > 0")
    if not lines:
        raise ValueError("cần ít nhất 1 line")

    earliest = max(expected_arrival, now) if expected_arrival else now
    duration = timedelta(minutes=duration_min)

    fit = shifts.fit_day_shift if shifts and shifts.day_only(priority) else None

    options = []
    for line in lines:
        start = earliest_start_on_line([s for s in slots if s.line == line], earliest, duration, fit)
        options.append(LineOption(line=line, start=start, end=start + duration))
    # Thứ tự A trước B + min ổn định → hòa chọn Line A
    best = min(options, key=lambda o: o.end)
    shift_delayed = None
    if fit is not None:
        unconstrained = earliest_start_on_line([s for s in slots if s.line == best.line], earliest, duration)
        if unconstrained < best.start:
            who = f"đơn {PRIORITY_LABEL[priority]}" if priority else "đơn"
            shift_delayed = f"{who} chỉ chạy ca ngày {shifts.label}"
    return Placement(
        line=best.line,
        start=best.start,
        end=best.end,
        sla_ok=best.end <= requested_return,
        earliest=earliest,
        requested_return=requested_return,
        options=tuple(options),
        shift_delayed=shift_delayed,
    )


def placement_reason(p: Placement, tz: tzinfo) -> str:
    """Lý do xếp ngắn gọn, mỗi ý 1 câu, sinh deterministic từ chính kết quả (không LLM) — hiện khi bấm khối trên lịch.

    Vd "Line B 10:30–13:30. Line A chỉ trống từ 14:00 → chọn Line B. Kịp giờ trả 16:00."
    """

    # Các mốc rơi vào nhiều ngày (vd dời sang ca hôm sau) → mốc nào cũng kèm ngày cho khỏi hiểu nhầm
    marks = (p.earliest, p.start, p.end, p.requested_return, *(o.start for o in p.options))
    dated = len({t.astimezone(tz).date() for t in marks}) > 1

    def hm(t: datetime) -> str:
        return t.astimezone(tz).strftime("%H:%M %d/%m" if dated else "%H:%M")

    s, e = p.start.astimezone(tz), p.end.astimezone(tz)
    if s.date() == e.date():
        span = f"{s:%H:%M}–{e:%H:%M}" + (f" {s:%d/%m}" if dated else "")
    else:
        span = f"{hm(p.start)}–{hm(p.end)}"
    parts = [f"Line {p.line.value} {span}."]

    if p.shift_delayed:
        parts.append(f"Sẵn sàng {hm(p.earliest)} nhưng {p.shift_delayed} → bắt đầu {hm(p.start)}.")
    elif p.start > p.earliest:
        parts.append(f"Line {p.line.value} bận đến {hm(p.start)}.")

    others = [o for o in p.options if o.line != p.line]
    if others and all(o.end == p.end for o in others):
        parts.append(f"Các line xong cùng lúc → chọn Line {p.line.value}.")
    elif others:
        busy = ", ".join(f"Line {o.line.value} chỉ trống từ {hm(o.start)}" for o in others)
        parts.append(f"{busy} → chọn Line {p.line.value}.")

    if p.sla_ok:
        parts.append(f"Kịp giờ trả {hm(p.requested_return)}.")
    else:
        late = int((p.end - p.requested_return).total_seconds() // 60)
        parts.append(f"Trễ giờ trả {hm(p.requested_return)} {late} phút → SLA_RISK.")
    return " ".join(parts)


def has_overlap(slots: Sequence[Slot]) -> bool:
    """Kiểm tra BR-04 trên một plan version."""
    for line in {s.line for s in slots}:
        ordered = sorted((s for s in slots if s.line == line), key=lambda s: s.start)
        if any(a.end > b.start for a, b in zip(ordered, ordered[1:], strict=False)):
            return True
    return False


@dataclass(frozen=True)
class ManualPlacement:
    slot: Slot
    sla_ok: bool
    reason: str


def manual_placement(
    *,
    work_order_id: str,
    line: Line,
    start: datetime,
    duration_min: int,
    expected_arrival: datetime | None,
    requested_return: datetime,
    now: datetime,
    busy: Iterable[Slot],
    priority: Priority | None = None,
    shifts: ShiftPolicy | None = None,
    tz: tzinfo,
    labels: dict[str, str] | None = None,
) -> ManualPlacement:
    """Kiểm tra giờ Điều phối chọn (BR-15) — sai → UnschedulableError / SlotConflictError, không tự dời."""
    start = start.replace(second=0, microsecond=0)
    end = start + timedelta(minutes=duration_min)
    first_day = start.astimezone(tz).date()

    def hm(t: datetime) -> str:
        local = t.astimezone(tz)
        return local.strftime("%H:%M") if local.date() == first_day else local.strftime("%H:%M %d/%m")

    if start < now.replace(second=0, microsecond=0):
        raise UnschedulableError("giờ bắt đầu đã qua")
    if expected_arrival is not None and start < expected_arrival:
        raise UnschedulableError(f"giờ bắt đầu trước giờ hàng đến {hm(expected_arrival)}")
    if shifts is not None and shifts.day_only(priority):
        label = PRIORITY_LABEL[priority or Priority.NORMAL]
        if end - start > shifts.day_length:
            h, m = divmod(duration_min, 60)
            raise UnschedulableError(f"đơn {label} dài {h}h{m:02d}, hơn cả ca ngày {shifts.label}")
        if shifts.fit_day_shift(start, end - start) != start:
            raise UnschedulableError(f"đơn {label} chỉ chạy trọn trong ca ngày {shifts.label}")
    for other in sorted(busy, key=lambda b: b.start):
        if other.line == line and other.work_order_id != work_order_id and other.overlaps(start, end):
            name = (labels or {}).get(other.work_order_id, other.work_order_id)
            raise SlotConflictError(
                f"Line {line.value} {hm(start)}–{hm(end)} trùng {name} ({hm(other.start)}–{hm(other.end)})"
            )
    sla_ok = end <= requested_return
    if sla_ok:
        sla = f"Kịp giờ trả {hm(requested_return)}."
    else:
        late = int((end - requested_return).total_seconds() // 60)
        sla = f"Trễ giờ trả {hm(requested_return)} {late} phút → cần duyệt đổi giờ trả."
    reason = f"Line {line.value} {hm(start)}–{hm(end)}. Điều phối xếp tay. {sla}"
    return ManualPlacement(Slot(work_order_id, line, start, end), sla_ok, reason)
