"""Cổng tiếp nhận sau trích xuất — validator (BR-01) + cổng tin cậy (BR-12, BR-13, ADR-0007). T-020.

Thuần, deterministic: nhận trường + tín hiệu nguồn, trả quyết định; việc ghi DB / chuyển trạng thái do caller làm.
Tên trường trong yêu cầu bổ sung / cảnh báo theo tên trường trích xuất (vd `package_dimensions_cm`) để UI highlight.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.modules.intake.confidence import (
    FieldSignal,
    FlagCode,
    IntakeAssessment,
    ReviewDecision,
    ReviewThresholds,
    TicketSignal,
    assess,
)
from src.modules.intake.models import (
    ClarificationRequest,
    ClarificationStatus,
    FieldExtraction,
    IntakeWarning,
    ReviewStatus,
    WorkOrder,
)
from src.modules.intake.schemas import COLUMN_TO_EXTRACTION, EXTRACTION_COLUMNS, SourceKind, WorkOrderFields
from src.modules.intake.validator import ErrorCode, FieldError, validate

FIELD_LABELS: dict[str, str] = {
    "product_name": "tên sản phẩm",
    "quantity": "số lượng thùng",
    "package_dimensions_cm": "kích thước thùng (dài × rộng × cao, cm)",
    "pkg_weight_kg": "khối lượng mỗi thùng (kg)",
    "required_dose_kgy": "liều chiếu yêu cầu (kGy)",
    "priority": "mức ưu tiên",
    "expected_arrival": "giờ hàng đến",
    "requested_return": "giờ trả mong muốn",
}

_QUESTION: dict[ErrorCode, str] = {
    ErrorCode.MISSING: "Anh/chị vui lòng cho biết {label}.",
    ErrorCode.NOT_POSITIVE: "Giá trị {label} trong phiếu chưa hợp lệ, anh/chị vui lòng xác nhận lại.",
    ErrorCode.RETURN_NOT_AFTER_ARRIVAL: "Giờ trả mong muốn đang sớm hơn hoặc bằng giờ hàng đến, anh/chị vui lòng xác nhận lại.",
    ErrorCode.DOSE_OUT_OF_RANGE: "Liều chiếu trong phiếu phải lớn hơn 0 và không quá 25 kGy, anh/chị vui lòng xác nhận lại liều.",
}


@dataclass(frozen=True)
class Clarification:
    field: str
    code: ErrorCode
    question: str


@dataclass(frozen=True)
class WarningItem:
    field: str | None
    code: FlagCode


@dataclass(frozen=True)
class GateResult:
    errors: list[FieldError]
    assessment: IntakeAssessment

    @property
    def review_status(self) -> ReviewStatus:
        if self.errors:
            return ReviewStatus.NEEDS_CLARIFICATION
        return {
            ReviewDecision.REVIEW: ReviewStatus.NEEDS_REVIEW,
            ReviewDecision.WARN: ReviewStatus.ACCEPTED_WITH_WARNINGS,
            ReviewDecision.AUTO: ReviewStatus.AUTO_ACCEPTED,
        }[self.assessment.decision]

    @property
    def proceeds(self) -> bool:
        """Tự vào FEASIBILITY_CHECK, không cần người bấm (AUTO / WARN)."""
        return self.review_status in (ReviewStatus.AUTO_ACCEPTED, ReviewStatus.ACCEPTED_WITH_WARNINGS)

    @property
    def clarifications(self) -> list[Clarification]:
        seen: dict[str, Clarification] = {}
        for e in self.errors:
            name = COLUMN_TO_EXTRACTION.get(e.field, e.field)
            if name not in seen:
                label = FIELD_LABELS.get(name, name)
                seen[name] = Clarification(name, e.code, _QUESTION[e.code].format(label=label))
        return list(seen.values())

    @property
    def unconfirmed_fields(self) -> list[str]:
        """Trường REVIEW người chưa xác nhận/sửa (cờ cấp ticket không tính — submit chính là xác nhận)."""
        return _dedupe(COLUMN_TO_EXTRACTION.get(f.field, f.field) for f in self.assessment.review_flags if f.field)

    @property
    def warnings(self) -> list[WarningItem]:
        out: dict[tuple, WarningItem] = {}
        for f in self.assessment.warnings:
            name = COLUMN_TO_EXTRACTION.get(f.field, f.field) if f.field else None
            out.setdefault((name, f.code), WarningItem(name, f.code))
        return list(out.values())


def run_gate(
    fields: WorkOrderFields,
    signals: dict[str, FieldSignal],
    thresholds: ReviewThresholds,
    *,
    ticket: TicketSignal | None = None,
) -> GateResult:
    errors = validate(fields)
    # Chỉ đánh giá độ tin cậy trường có giá trị (trường thiếu đã là lỗi validator)
    present = {k: v for k, v in signals.items() if getattr(fields, k, None) is not None}
    return GateResult(errors, assess(present, thresholds, ticket))


def signals_from_extractions(rows: Iterable[FieldExtraction]) -> dict[str, FieldSignal]:
    """Tín hiệu theo cột work order từ nguồn đã lưu (dùng lại khi người sửa / submit)."""
    signals: dict[str, FieldSignal] = {}
    for r in rows:
        for column in EXTRACTION_COLUMNS.get(r.field, (r.field,)):
            signals[column] = FieldSignal(source_kind=SourceKind(r.source_kind), confidence=r.confidence)
    return signals


def record_gate(db: Session, wo: WorkOrder, result: GateResult, *, now: datetime, auto: bool = True) -> None:
    """Ghi kết quả cổng: review_status, yêu cầu bổ sung (mở mới / đóng khi đã có), cảnh báo (chỉ khi tự đi tiếp).

    `auto=False` (người đang sửa đơn DRAFT): không tự đi tiếp → đủ trường thì NEEDS_REVIEW chờ người submit,
    không tạo cảnh báo. Không commit, không đổi `state` (việc của Orchestration).
    """
    wo.review_status = result.review_status
    if not auto and not result.errors:
        wo.review_status = ReviewStatus.NEEDS_REVIEW
    open_requests = {
        r.field: r
        for r in db.scalars(
            select(ClarificationRequest).where(
                ClarificationRequest.work_order_id == wo.id, ClarificationRequest.status == ClarificationStatus.OPEN
            )
        )
    }
    needed = {c.field: c for c in result.clarifications}
    for name, req in open_requests.items():
        if name not in needed:
            req.status, req.answered_at = ClarificationStatus.ANSWERED, now
    for name, c in needed.items():
        if name not in open_requests:
            db.add(ClarificationRequest(work_order_id=wo.id, field=name, question=c.question, created_at=now))
    if auto and result.proceeds:
        db.add_all(
            IntakeWarning(work_order_id=wo.id, field=w.field, code=w.code, created_at=now) for w in result.warnings
        )


def _dedupe(items: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(items))
