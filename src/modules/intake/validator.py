"""Validator deterministic cho work order — ADC-001 (T-020), BR-01.

Thiếu trường bắt buộc → yêu cầu bổ sung, work order giữ DRAFT, không vào FEASIBILITY_CHECK.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from src.modules.estimation.estimator import dose_key
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


class ErrorCode(StrEnum):
    MISSING = "MISSING"
    NOT_POSITIVE = "NOT_POSITIVE"
    RETURN_NOT_AFTER_ARRIVAL = "RETURN_NOT_AFTER_ARRIVAL"
    DOSE_NEEDS_CONFIRMATION = "DOSE_NEEDS_CONFIRMATION"


@dataclass(frozen=True)
class FieldError:
    field: str
    code: ErrorCode


def validate(fields: WorkOrderFields, allowed_doses: Iterable[str] | None = None) -> list[FieldError]:
    errors: list[FieldError] = []
    for name in REQUIRED_FIELDS:
        value = getattr(fields, name)
        if value is None or (isinstance(value, str) and not value.strip()):
            errors.append(FieldError(name, ErrorCode.MISSING))

    for name in POSITIVE_FIELDS:
        value = getattr(fields, name)
        if value is not None and value <= 0:
            errors.append(FieldError(name, ErrorCode.NOT_POSITIVE))

    if fields.expected_arrival and fields.requested_return and fields.requested_return <= fields.expected_arrival:
        errors.append(FieldError("requested_return", ErrorCode.RETURN_NOT_AFTER_ARRIVAL))

    if allowed_doses is not None and fields.required_dose_kgy is not None:
        if dose_key(fields.required_dose_kgy) not in set(allowed_doses):
            errors.append(FieldError("required_dose_kgy", ErrorCode.DOSE_NEEDS_CONFIRMATION))

    return errors


def is_complete(fields: WorkOrderFields) -> bool:
    return not any(e.code == ErrorCode.MISSING for e in validate(fields))
