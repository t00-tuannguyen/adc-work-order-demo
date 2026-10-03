"""Validator deterministic cho work order — ADC-001 (T-020), BR-01.

Thiếu trường bắt buộc → yêu cầu bổ sung, work order giữ DRAFT, không vào FEASIBILITY_CHECK.
"""

from dataclasses import dataclass
from enum import StrEnum

from src.modules.intake.schemas import WorkOrderFields

# FR 02: tên sản phẩm, số lượng, quy cách, liều, giờ trả.
# "Quy cách" = kích thước + khối lượng thùng (specs/domains.md §3) — cả hai cần cho estimate_duration.
REQUIRED_FIELDS: tuple[str, ...] = (
    "product_name",
    "quantity",
    "pkg_length_cm",
    "pkg_width_cm",
    "pkg_height_cm",
    "pkg_weight_kg",
    "required_dose_kgy",
    "requested_return",
)

POSITIVE_FIELDS: tuple[str, ...] = ("quantity", "pkg_length_cm", "pkg_width_cm", "pkg_height_cm", "pkg_weight_kg")

# Liều lấy nguyên giá trị quét từ ticket, chỉ kiểm tra khoảng 0 < liều ≤ 25 kGy (không đối chiếu `dose_factor`)
MAX_DOSE_KGY = 25


class ErrorCode(StrEnum):
    MISSING = "MISSING"
    NOT_POSITIVE = "NOT_POSITIVE"
    RETURN_NOT_AFTER_ARRIVAL = "RETURN_NOT_AFTER_ARRIVAL"
    DOSE_OUT_OF_RANGE = "DOSE_OUT_OF_RANGE"


@dataclass(frozen=True)
class FieldError:
    field: str
    code: ErrorCode


def validate(fields: WorkOrderFields) -> list[FieldError]:
    errors: list[FieldError] = []
    for name in REQUIRED_FIELDS:
        value = getattr(fields, name)
        if value is None or (isinstance(value, str) and not value.strip()):
            errors.append(FieldError(name, ErrorCode.MISSING))

    for name in POSITIVE_FIELDS:
        value = getattr(fields, name)
        if value is not None and value <= 0:
            errors.append(FieldError(name, ErrorCode.NOT_POSITIVE))

    dose = fields.required_dose_kgy
    if dose is not None and not 0 < dose <= MAX_DOSE_KGY:
        errors.append(FieldError("required_dose_kgy", ErrorCode.DOSE_OUT_OF_RANGE))

    if fields.expected_arrival and fields.requested_return and fields.requested_return <= fields.expected_arrival:
        errors.append(FieldError("requested_return", ErrorCode.RETURN_NOT_AFTER_ARRIVAL))

    return errors


def is_complete(fields: WorkOrderFields) -> bool:
    return not any(e.code == ErrorCode.MISSING for e in validate(fields))
