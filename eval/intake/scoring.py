"""Chấm điểm trích xuất ADC-001 (T-022) — thuần, deterministic.

So kết quả SAU chuẩn hóa (`normalize`, như hệ thống thật lưu vào work order) với đáp án `answers.json`.
- Độ chính xác trường: 8 trường / ticket đáp án; đúng khi khớp giá trị, hoặc cả hai cùng trống (không đoán).
- Phát hiện trường thiếu: trường đáp án trống → hệ thống cũng để trống.
- Trang nguồn đúng: trang của trường nằm trong khoảng trang của ticket đáp án.
- AUTO sai: ticket được cổng cho AUTO (không cần người) nhưng có ≥ 1 trường sai — mục tiêu ≈ 0 (ADR-0007).
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

FIELDS = (
    "product_name",
    "quantity",
    "package_dimensions_cm",
    "pkg_weight_kg",
    "required_dose_kgy",
    "priority",
    "expected_arrival",
    "requested_return",
)
LOCAL_TZ = timezone(timedelta(hours=7))


def _num_ok(expected: float, got: float) -> bool:
    return abs(expected - got) <= max(0.01 * abs(expected), 0.02)


def _text(v: str) -> str:
    return re.sub(r"\s+", " ", v).strip().casefold()


def local_minute(value: datetime | str | None) -> str | None:
    """datetime có tz (hoặc ISO) → "YYYY-MM-DDTHH:MM" giờ Việt Nam."""
    if value is None:
        return None
    dt = datetime.fromisoformat(value) if isinstance(value, str) else value
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=LOCAL_TZ)
    return dt.astimezone(LOCAL_TZ).strftime("%Y-%m-%dT%H:%M")


def field_ok(name: str, expected, got) -> bool:
    if expected is None or got is None:
        return expected is None and got is None
    if name == "product_name":
        return _text(expected) == _text(got)
    if name == "package_dimensions_cm":
        return len(expected) == len(got) == 3 and all(_num_ok(e, g) for e, g in zip(expected, got, strict=True))
    if name in ("quantity", "pkg_weight_kg", "required_dose_kgy"):
        return _num_ok(float(expected), float(got))
    if name in ("expected_arrival", "requested_return"):
        return local_minute(expected) == local_minute(got)
    return expected == got


def comparable(fields) -> dict:
    """WorkOrderFields (đã chuẩn hóa) → dict cùng dạng đáp án."""
    dims = (fields.pkg_length_cm, fields.pkg_width_cm, fields.pkg_height_cm)
    return {
        "product_name": fields.product_name,
        "quantity": fields.quantity,
        "package_dimensions_cm": list(dims) if any(d is not None for d in dims) else None,
        "pkg_weight_kg": fields.pkg_weight_kg,
        "required_dose_kgy": fields.required_dose_kgy,
        "priority": fields.priority.value if fields.priority else None,
        "expected_arrival": local_minute(fields.expected_arrival),
        "requested_return": local_minute(fields.requested_return),
    }


@dataclass
class TicketScore:
    fields_ok: dict[str, bool]
    missing_expected: int = 0  # số trường đáp án để trống
    missing_detected: int = 0  # trong đó hệ thống cũng để trống
    pages_checked: int = 0
    pages_ok: int = 0
    pages_range_ok: bool = False
    decision: str | None = None  # AUTO / WARN / REVIEW / CLARIFY (thiếu-sai trường)

    @property
    def all_ok(self) -> bool:
        return all(self.fields_ok.values())


@dataclass
class SampleScore:
    sample_id: str
    kind: str
    expected_tickets: int
    predicted_tickets: int
    tickets: list[TicketScore] = field(default_factory=list)
    error: str | None = None
    latency_s: float | None = None


def score_ticket(expected: dict, predicted: dict | None, pages: dict[str, int | None], range_: tuple[int, int] | None):
    """`predicted` = comparable(); `pages` = trang nguồn theo trường; None → ticket bị bỏ sót (mọi trường sai)."""
    exp_fields = expected["fields"]
    if predicted is None:
        ts = TicketScore({f: False for f in FIELDS})
        ts.missing_expected = sum(exp_fields[f] is None for f in FIELDS)
        return ts
    ts = TicketScore({f: field_ok(f, exp_fields[f], predicted[f]) for f in FIELDS})
    lo, hi = expected["page_from"], expected["page_to"]
    ts.pages_range_ok = range_ == (lo, hi)
    for f in FIELDS:
        if exp_fields[f] is None:
            ts.missing_expected += 1
            ts.missing_detected += predicted[f] is None
        elif predicted[f] is not None and pages.get(f) is not None:
            ts.pages_checked += 1
            ts.pages_ok += lo <= pages[f] <= hi
    return ts


def summarize(scores: list[SampleScore]) -> dict:
    """Tổng hợp theo loại (text / scan / all)."""

    def agg(items: list[SampleScore]) -> dict:
        tickets = [t for s in items for t in s.tickets]
        fields_total = len(tickets) * len(FIELDS)
        fields_ok = sum(sum(t.fields_ok.values()) for t in tickets)
        auto = [t for t in tickets if t.decision == "AUTO"]
        per_field = {
            f: round(sum(t.fields_ok[f] for t in tickets) / len(tickets), 3) if tickets else None for f in FIELDS
        }
        latencies = [s.latency_s for s in items if s.latency_s is not None]
        return {
            "samples": len(items),
            "tickets_expected": sum(s.expected_tickets for s in items),
            "ticket_count_ok": sum(s.expected_tickets == s.predicted_tickets for s in items),
            "failed_calls": sum(s.error is not None for s in items),
            "field_accuracy": round(fields_ok / fields_total, 3) if fields_total else None,
            "per_field": per_field,
            "missing_detection": _ratio(
                sum(t.missing_detected for t in tickets), sum(t.missing_expected for t in tickets)
            ),
            "page_accuracy": _ratio(sum(t.pages_ok for t in tickets), sum(t.pages_checked for t in tickets)),
            "page_range_accuracy": _ratio(sum(t.pages_range_ok for t in tickets), len(tickets)),
            "decisions": {d: sum(t.decision == d for t in tickets) for d in ("AUTO", "WARN", "REVIEW", "CLARIFY")},
            "auto_tickets": len(auto),
            "auto_wrong": sum(not t.all_ok for t in auto),
            "auto_wrong_rate": _ratio(sum(not t.all_ok for t in auto), len(auto)),
            "latency_s_max": round(max(latencies), 1) if latencies else None,
            "latency_s_avg": round(sum(latencies) / len(latencies), 1) if latencies else None,
        }

    return {
        "text": agg([s for s in scores if s.kind == "text"]),
        "scan": agg([s for s in scores if s.kind == "scan"]),
        "all": agg(scores),
    }


def _ratio(num: int, den: int) -> float | None:
    return round(num / den, 3) if den else None
