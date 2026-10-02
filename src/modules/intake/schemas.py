"""Schema ticket / work order — ADC-001, specs/domains.md §3."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel

from src.modules.types import Priority


class SourceKind(StrEnum):
    VERBATIM = "VERBATIM"  # Nguyên văn
    INFERRED = "INFERRED"  # AI suy luận
    CONVERTED = "CONVERTED"  # Đã quy đổi
    OCR_LOW = "OCR_LOW"  # OCR tin cậy thấp
    MANUAL = "MANUAL"  # Nhập tay
    DEFAULT = "DEFAULT"  # Mặc định


class TicketSourceType(StrEnum):
    PDF = "PDF"
    TEXT = "TEXT"
    MANUAL = "MANUAL"


# Trường trích xuất (1 dòng field_extractions) → cột work order. Quy cách: 1 nguồn cho 3 cột kích thước.
EXTRACTION_COLUMNS: dict[str, tuple[str, ...]] = {
    "product_name": ("product_name",),
    "quantity": ("quantity",),
    "package_dimensions_cm": ("pkg_length_cm", "pkg_width_cm", "pkg_height_cm"),
    "pkg_weight_kg": ("pkg_weight_kg",),
    "required_dose_kgy": ("required_dose_kgy",),
    "priority": ("priority",),
    "expected_arrival": ("expected_arrival",),
    "requested_return": ("requested_return",),
}
COLUMN_TO_EXTRACTION: dict[str, str] = {c: name for name, cols in EXTRACTION_COLUMNS.items() for c in cols}


class WorkOrderFields(BaseModel):
    """8 trường ticket, đã chuẩn hóa đơn vị (cm, kg, kGy). Trường không có trong nguồn → None."""

    product_name: str | None = None
    quantity: int | None = None
    pkg_length_cm: float | None = None
    pkg_width_cm: float | None = None
    pkg_height_cm: float | None = None
    pkg_weight_kg: float | None = None
    required_dose_kgy: float | None = None
    priority: Priority | None = None
    expected_arrival: datetime | None = None
    requested_return: datetime | None = None
