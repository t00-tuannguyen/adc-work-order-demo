"""Xử lý sự cố line — ADC-004, Incident Handling Logic (ADR-0004). Lõi deterministic, không DB/LLM.

- Bước 2: `find_affected_slots` — slot trên line sự cố chồng lấn khung dừng (FR 07).
- Bước 3: `reschedule_order` — VIP → Khẩn → Thường, cùng mức giờ trả sớm hơn trước (BR-05, FR 09).
- Bước 4–6: `reschedule` — greedy theo thứ tự trên, mỗi đơn chọn line kết thúc sớm nhất giữa line còn lại và
  line sự cố sau khi hồi phục (khung dừng coi như slot bận, FR 08). Đơn VIP/Khẩn vẫn trễ mà xong sớm hơn được
  nhờ đẩy lùi đơn ưu tiên thấp hơn chưa bắt đầu → đẩy (priority override, cần duyệt); đơn bị đẩy xếp lại theo cùng
  thứ tự (đơn Khẩn bị đẩy lại có thể đẩy đơn Thường). Tiêu chí ADC-004: không đơn ưu tiên cao nào trễ trong khi đơn
  ưu tiên thấp hơn còn giữ chỗ giúp nó xong sớm hơn. Đơn đang chiếu dở chạy lại đủ thời lượng từ đầu (giả định
  chờ đối tác).
- Bước 6b: `compact` — dồn trái (ADR-0011): mọi đơn chưa bắt đầu (kể cả đơn vừa dời) được xếp lại sớm nhất có thể,
  chỉ nhận khi xong sớm hơn → lấp khe trống do sự cố để lại, không đơn nào xong muộn hơn.
- Giải thích deterministic (`move_reason`, `incident_explanation`) — Scheduler Agent (T-034) viết lại bằng LLM.
Bước 7–10 (plan version, SLA_RISK, gửi duyệt) ở src/modules/orchestration/incidents.py.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, tzinfo
from enum import StrEnum

from src.modules.scheduling.scheduler import Placement, ShiftPolicy, Slot, placement_reason, schedule_order
from src.modules.types import PRIORITY_LABEL, PRIORITY_RANK, Line, Priority


@dataclass(frozen=True)
class Incident:
    line: Line
    start_at: datetime
    est_downtime_min: int

    @property
    def end_at(self) -> datetime:
        return self.start_at + timedelta(minutes=self.est_downtime_min)


def find_affected_slots(slots: Sequence[Slot], incident: Incident, now: datetime) -> list[Slot]:
    """Slot trên line sự cố chồng lấn [start, start + downtime] (FR 07).

    Downtime = 0 hoặc nằm hoàn toàn trong quá khứ → không có đơn bị ảnh hưởng.
    """
    if incident.est_downtime_min <= 0 or incident.end_at <= now:
        return []
    return sorted(
        (s for s in slots if s.line == incident.line and s.overlaps(incident.start_at, incident.end_at)),
        key=lambda s: (s.start, s.work_order_id),
    )


@dataclass(frozen=True)
class RescheduleCandidate:
    work_order_id: str
    priority: Priority
    requested_return: datetime
    old: Slot | None = None  # slot cũ; thời lượng xếp lại = độ dài slot cũ
    expected_arrival: datetime | None = None


def reschedule_order(candidates: Sequence[RescheduleCandidate]) -> list[RescheduleCandidate]:
    """Thứ tự xử lý khi tái lập lịch (BR-05): VIP → Khẩn → Thường, cùng mức thì giờ trả sớm hơn trước.

    Mã đơn là khóa phụ cuối cùng để kết quả luôn tái lập được.
    """
    return sorted(candidates, key=lambda c: (PRIORITY_RANK[c.priority], c.requested_return, c.work_order_id))


class AffectedOutcome(StrEnum):
    MOVED_ALT_LINE = "MOVED_ALT_LINE"
    DELAYED = "DELAYED"
    UNCHANGED = "UNCHANGED"
    PULLED_FORWARD = "PULLED_FORWARD"  # không bị ảnh hưởng, được kéo sớm lấp khe trống (ADR-0011)


@dataclass(frozen=True)
class Move:
    candidate: RescheduleCandidate
    placement: Placement
    bumped: bool = False  # bị đẩy lùi để nhường đơn ưu tiên cao hơn đang trễ (priority override)
    pulled: bool = False  # không bị ảnh hưởng, được kéo sớm lấp khe trống (compaction — ADR-0011)

    @property
    def old(self) -> Slot:
        assert self.candidate.old is not None
        return self.candidate.old

    @property
    def new(self) -> Slot:
        p = self.placement
        return Slot(self.candidate.work_order_id, p.line, p.start, p.end)

    @property
    def outcome(self) -> AffectedOutcome:
        if self.new == self.old:
            return AffectedOutcome.UNCHANGED
        if self.pulled:
            return AffectedOutcome.PULLED_FORWARD
        return AffectedOutcome.MOVED_ALT_LINE if self.new.line != self.old.line else AffectedOutcome.DELAYED

    @property
    def sla_ok(self) -> bool:
        return self.placement.sla_ok


DOWNTIME_ID = "__downtime__"


def downtime_slot(incident: Incident) -> Slot:
    """Khung dừng như 1 slot bận trên line sự cố — scheduler không xếp gì vào đó."""
    return Slot(DOWNTIME_ID, incident.line, incident.start_at, incident.end_at)


def reschedule(
    *,
    affected: Sequence[RescheduleCandidate],
    fixed: Sequence[Slot],
    downtimes: Sequence[Incident],
    now: datetime,
    bumpable: Sequence[RescheduleCandidate] = (),
    shifts: ShiftPolicy | None = None,
) -> list[Move]:
    """Xếp lại đơn bị ảnh hưởng; trả theo thứ tự xử lý, gồm cả đơn bị đẩy (`bumped`).

    `fixed`: slot giữ nguyên (gồm cả slot của `bumpable`). `bumpable`: đơn không bị ảnh hưởng được phép đẩy lùi
    nếu chưa bắt đầu (slot bắt đầu ≥ now) và ưu tiên thấp hơn đơn đang trễ.
    Không bao giờ tạo slot chồng lấn nhau hay chồng khung dừng (BR-04).
    """
    busy = [*fixed, *(downtime_slot(d) for d in downtimes if d.est_downtime_min > 0)]
    pool = {c.work_order_id: c for c in bumpable if c.old and c.old.start >= now}
    queue = reschedule_order(affected)
    bumped: set[str] = set()
    moves: list[Move] = []
    while queue:
        c = queue.pop(0)
        if c.old is None:
            raise ValueError(f"{c.work_order_id}: thiếu slot cũ")
        duration_min = int((c.old.end - c.old.start) / timedelta(minutes=1))

        def place(slots: Sequence[Slot], c: RescheduleCandidate = c, duration_min: int = duration_min) -> Placement:
            return schedule_order(
                duration_min=duration_min,
                requested_return=c.requested_return,
                expected_arrival=c.expected_arrival,
                now=now,
                slots=slots,
                priority=c.priority,
                shifts=shifts,
            )

        p = place(busy)
        lower = {w: b for w, b in pool.items() if PRIORITY_RANK[b.priority] > PRIORITY_RANK[c.priority]}
        if not p.sla_ok and lower:
            p2 = place([s for s in busy if s.work_order_id not in lower])
            victims = [
                b for b in lower.values() if b.old and b.old.line == p2.line and b.old.overlaps(p2.start, p2.end)
            ]
            if victims and p2.end < p.end:
                out = {v.work_order_id for v in victims}
                busy = [s for s in busy if s.work_order_id not in out]
                for w in out:
                    del pool[w]
                bumped |= out
                queue = reschedule_order([*queue, *victims])
                p = p2
        busy.append(Slot(c.work_order_id, p.line, p.start, p.end))
        moves.append(Move(c, p, bumped=c.work_order_id in bumped))
    return moves


def compact(
    *,
    moves: Sequence[Move],
    movable: Sequence[RescheduleCandidate],
    fixed: Sequence[Slot],
    downtimes: Sequence[Incident],
    now: datetime,
    shifts: ShiftPolicy | None = None,
    max_passes: int = 20,
) -> list[Move]:
    """Dồn trái sau `reschedule` (ADR-0011): lấp khe trống mà không đơn nào xong muộn hơn.

    `moves`: kết quả `reschedule` (đơn bị ảnh hưởng + đơn bị đẩy). `movable`: đơn không bị ảnh hưởng, chưa bắt đầu,
    được phép kéo sớm (slot hiện tại = `old`). `fixed`: slot giữ nguyên tuyệt đối (đang chạy, chờ hàng, đề xuất chờ
    duyệt...). Mỗi vòng xét theo thứ tự BR-05; đơn chỉ đổi chỗ khi giờ xong mới sớm hơn hẳn → luôn dừng.
    Trả `moves` (vị trí đã cải thiện nếu có, giữ thứ tự) rồi các đơn được kéo sớm (`pulled`) theo BR-05.
    """
    busy_fixed = [*fixed, *(downtime_slot(d) for d in downtimes if d.est_downtime_min > 0)]
    current: dict[str, Slot] = {m.candidate.work_order_id: m.new for m in moves}
    placements: dict[str, Placement] = {}
    candidates = {m.candidate.work_order_id: m.candidate for m in moves}
    for c in movable:
        if c.old is not None and c.old.start >= now and c.work_order_id not in candidates:
            candidates[c.work_order_id] = c
            current[c.work_order_id] = c.old

    for _ in range(max_passes):
        changed = False
        for c in reschedule_order(list(candidates.values())):
            wid = c.work_order_id
            assert c.old is not None
            others = [s for w, s in current.items() if w != wid]
            p = schedule_order(
                duration_min=int((c.old.end - c.old.start) / timedelta(minutes=1)),
                requested_return=c.requested_return,
                expected_arrival=c.expected_arrival,
                now=now,
                slots=[*busy_fixed, *others],
                priority=c.priority,
                shifts=shifts,
            )
            if p.end < current[wid].end:
                current[wid] = Slot(wid, p.line, p.start, p.end)
                placements[wid] = p
                changed = True
        if not changed:
            break

    out = [Move(m.candidate, placements.get(m.candidate.work_order_id, m.placement), bumped=m.bumped) for m in moves]
    moved = {m.candidate.work_order_id for m in moves}
    pulled = [c for c in reschedule_order(list(candidates.values())) if c.work_order_id not in moved]
    out += [Move(c, placements[c.work_order_id], pulled=True) for c in pulled if c.work_order_id in placements]
    return out


def move_reason(move: Move, tz: tzinfo) -> str:
    """Lý do dời 1 đơn, sinh từ chính kết quả. Vd "Line A dừng → Line B 11:00–14:45: …"."""
    if move.pulled:
        why = "Kéo sớm lấp khe trống sau sự cố"
    elif move.bumped:
        why = f"Nhường Line {move.old.line.value} cho đơn ưu tiên cao hơn đang trễ (priority override)"
    else:
        why = f"Line {move.old.line.value} dừng"
    return f"{why} → {placement_reason(move.placement, tz)}"


@dataclass(frozen=True)
class MoveSummary:
    """1 dòng của phương án để tóm tắt — dựng lại được từ DB (GET /api/incidents/{id})."""

    label: str  # tên sản phẩm hoặc mã đơn
    priority: Priority
    old: Slot
    new: Slot
    requested_return: datetime
    bumped: bool
    pulled: bool = False  # không bị ảnh hưởng, kéo sớm lấp khe trống (ADR-0011)


def summarize(move: Move, label: str) -> MoveSummary:
    c = move.candidate
    return MoveSummary(label, c.priority, move.old, move.new, c.requested_return, move.bumped, move.pulled)


def incident_explanation(
    line: Line, start: datetime, end: datetime, moves: Sequence[MoveSummary], tz: tzinfo, *, resolved: bool = False
) -> str:
    """Tóm tắt phương án bằng ngôn ngữ nghiệp vụ, từng dòng theo thứ tự xử lý; giờ theo `tz`.

    Các mốc rơi vào nhiều ngày (vd đơn dời sang ca hôm sau) → mốc nào cũng kèm ngày cho khỏi hiểu nhầm.
    """
    marks = [
        start,
        end,
        *(t for m in moves for t in (m.old.start, m.old.end, m.new.start, m.new.end, m.requested_return)),
    ]
    dated = len({t.astimezone(tz).date() for t in marks}) > 1

    def hm(t: datetime) -> str:
        return t.astimezone(tz).strftime("%H:%M %d/%m" if dated else "%H:%M")

    def span(a: datetime, b: datetime) -> str:
        la, lb = a.astimezone(tz), b.astimezone(tz)
        if la.date() == lb.date():
            return f"{la:%H:%M}–{lb:%H:%M}" + (f" {la:%d/%m}" if dated else "")
        return f"{hm(a)}–{hm(b)}"

    window = f"Line {line.value} dừng {span(start, end)}" + (" (đã hồi phục)" if resolved else " (dự kiến)")
    if not moves:
        return f"{window}: không có đơn bị ảnh hưởng."
    hit = sum(1 for m in moves if not m.pulled)
    head = f"{window}: {hit} đơn phải xếp lại, theo thứ tự VIP → Khẩn → Thường rồi giờ trả sớm hơn."
    if pulled := len(moves) - hit:
        head += f" {pulled} đơn khác được kéo sớm để lấp khe trống."
    lines = [head]
    late = 0
    for m in moves:
        head = f"- {m.label} ({PRIORITY_LABEL[m.priority]})"
        if m.pulled:
            head += " được kéo sớm lấp khe trống"
        elif m.bumped:
            head += " bị đẩy lùi nhường đơn ưu tiên cao hơn"
        moved = f"Line {m.old.line.value} {span(m.old.start, m.old.end)} → Line {m.new.line.value} {span(m.new.start, m.new.end)}"
        if m.new.end <= m.requested_return:
            sla = f"kịp giờ trả {hm(m.requested_return)}"
        else:
            late += 1
            sla = f"trễ giờ trả {hm(m.requested_return)} {late_minutes(m)} phút → SLA_RISK"
        lines.append(f"{head}: {moved}, {sla}.")
    tail = "Phương án chờ duyệt, lịch đang chạy chưa đổi."
    if late:
        tail = f"{late} đơn trễ giờ trả cần kinh doanh báo khách (escalation). " + tail
    lines.append(tail)
    return "\n".join(lines)


def late_minutes(m: MoveSummary) -> int:
    """Số phút xong sau giờ trả (0 nếu kịp)."""
    return max(0, int((m.new.end - m.requested_return) / timedelta(minutes=1)))
