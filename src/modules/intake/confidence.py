"""Cổng HITL theo độ tin cậy sau OCR/trích xuất — ADC-001, ADR-0007, BR-12, BR-13.

Deterministic: chỉ đọc nhãn nguồn + độ tin cậy OCR do code gắn (không dùng độ tin cậy LLM tự khai).
- REVIEW: có trường tin cậy thấp → giữ DRAFT, người dùng phải xác nhận (HITL).
- WARN: kết quả không rõ ràng → vẫn tự đi tiếp nhưng tạo cảnh báo cho người.
- AUTO: rõ ràng → tự chuyển FEASIBILITY_CHECK, không cần người xác nhận.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from src.modules.intake.schemas import SourceKind


class ReviewDecision(StrEnum):
    AUTO = "AUTO"
    WARN = "WARN"
    REVIEW = "REVIEW"


class FlagCode(StrEnum):
    # → REVIEW
    LOW_CONFIDENCE = "LOW_CONFIDENCE"  # OCR dưới low_confidence_threshold hoặc nhãn OCR_LOW
    BOUNDARY_UNCERTAIN = "BOUNDARY_UNCERTAIN"  # không chắc ranh giới ticket trong file nhiều ticket
    # → WARN
    AMBIGUOUS_OCR = "AMBIGUOUS_OCR"  # OCR trong vùng xám [low, warn)
    INFERRED_VALUE = "INFERRED_VALUE"  # AI suy luận (vd ưu tiên từ "gấp")
    DEFAULT_VALUE = "DEFAULT_VALUE"  # giá trị mặc định, không có trong nguồn
    POSSIBLE_DUPLICATE = "POSSIBLE_DUPLICATE"  # file trùng sha256


REVIEW_CODES: frozenset[FlagCode] = frozenset({FlagCode.LOW_CONFIDENCE, FlagCode.BOUNDARY_UNCERTAIN})


@dataclass(frozen=True)
class FieldSignal:
    source_kind: SourceKind | None = None
    confidence: float | None = None  # None = không qua OCR (text layer, nhập tay) → coi như chắc chắn


@dataclass(frozen=True)
class TicketSignal:
    boundary_uncertain: bool = False
    possible_duplicate: bool = False


@dataclass(frozen=True)
class ReviewThresholds:
    low: float = 0.8
    warn: float = 0.9

    def __post_init__(self) -> None:
        if not 0 <= self.low <= self.warn <= 1:
            raise ValueError(f"cần 0 ≤ low ≤ warn ≤ 1, nhận low={self.low}, warn={self.warn}")

    @classmethod
    def from_config(cls, raw: Mapping) -> "ReviewThresholds":
        """Đọc mục `ocr` trong throughput.yaml."""
        ocr = raw.get("ocr") or {}
        return cls(
            low=float(ocr.get("low_confidence_threshold", cls.low)),
            warn=float(ocr.get("warn_confidence_threshold", cls.warn)),
        )


@dataclass(frozen=True)
class IntakeFlag:
    code: FlagCode
    field: str | None = None  # None = cờ cấp ticket


@dataclass(frozen=True)
class IntakeAssessment:
    decision: ReviewDecision
    flags: list[IntakeFlag] = field(default_factory=list)

    @property
    def review_flags(self) -> list[IntakeFlag]:
        return [f for f in self.flags if f.code in REVIEW_CODES]

    @property
    def warnings(self) -> list[IntakeFlag]:
        return [f for f in self.flags if f.code not in REVIEW_CODES]


def _field_flag(signal: FieldSignal, thresholds: ReviewThresholds) -> FlagCode | None:
    if signal.source_kind == SourceKind.MANUAL:
        return None  # người đã nhập/xác nhận
    if signal.source_kind == SourceKind.OCR_LOW:
        return FlagCode.LOW_CONFIDENCE
    if signal.confidence is not None:
        if signal.confidence < thresholds.low:
            return FlagCode.LOW_CONFIDENCE
        if signal.confidence < thresholds.warn:
            return FlagCode.AMBIGUOUS_OCR
    if signal.source_kind == SourceKind.INFERRED:
        return FlagCode.INFERRED_VALUE
    if signal.source_kind == SourceKind.DEFAULT:
        return FlagCode.DEFAULT_VALUE
    return None


def assess(
    signals: Mapping[str, FieldSignal],
    thresholds: ReviewThresholds,
    ticket: TicketSignal | None = None,
) -> IntakeAssessment:
    """Chỉ đánh giá trường có giá trị; trường thiếu do validator xử lý (BR-01)."""
    flags: list[IntakeFlag] = []
    ticket = ticket or TicketSignal()
    if ticket.boundary_uncertain:
        flags.append(IntakeFlag(FlagCode.BOUNDARY_UNCERTAIN))
    if ticket.possible_duplicate:
        flags.append(IntakeFlag(FlagCode.POSSIBLE_DUPLICATE))
    for name, signal in signals.items():
        code = _field_flag(signal, thresholds)
        if code is not None:
            flags.append(IntakeFlag(code, name))

    if any(f.code in REVIEW_CODES for f in flags):
        decision = ReviewDecision.REVIEW
    elif flags:
        decision = ReviewDecision.WARN
    else:
        decision = ReviewDecision.AUTO
    return IntakeAssessment(decision, flags)
