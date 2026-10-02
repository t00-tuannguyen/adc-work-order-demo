"""JSON schema output của các agent LLM (ADR-0001: mọi agent có input/output schema cố định).

Trường không có trong nguồn → value = null, không đoán (AGENTS.md §3).
Order Agent chạy trên Gemini (ADR-0010) → mỗi trường có kiểu `value` cụ thể (response_schema không nhận Any).
"""

from pydantic import BaseModel, Field

from src.modules.intake.schemas import SourceKind
from src.modules.types import Priority


class ExtractedField(BaseModel):
    source_kind: SourceKind | None = None
    page: int | None = Field(default=None, ge=1)
    snippet: str | None = None  # đoạn nguyên văn trong PDF chứa giá trị
    # [ymin, xmin, ymax, xmax] chuẩn hóa 0–1000 theo trang (quy ước bounding box của Gemini)
    box_2d: list[int] | None = None
    # Độ tin cậy 0–1 — TẠM do Gemini tự chấm (ADR-0010), hiệu chỉnh ở T-022. None = nhập tay.
    confidence: float | None = Field(default=None, ge=0, le=1)


class TextField(ExtractedField):
    value: str | None = None


class IntField(ExtractedField):
    value: int | None = None


class FloatField(ExtractedField):
    value: float | None = None


class Dimensions(BaseModel):
    length: float
    width: float
    height: float


class DimensionsField(ExtractedField):
    value: Dimensions | None = None


class PriorityField(ExtractedField):
    value: Priority | None = None


class DateTimeField(ExtractedField):
    value: str | None = None  # "YYYY-MM-DDTHH:MM" giờ địa phương như ghi trong ticket


class OrderExtraction(BaseModel):
    """8 trường của 1 ticket — ví dụ trong specs/api-contracts.md §1."""

    product_name: TextField = TextField()
    quantity: IntField = IntField()
    package_dimensions_cm: DimensionsField = DimensionsField()
    pkg_weight_kg: FloatField = FloatField()
    required_dose_kgy: FloatField = FloatField()
    priority: PriorityField = PriorityField()  # suy luận từ "gấp", "khẩn" → INFERRED
    expected_arrival: DateTimeField = DateTimeField()
    requested_return: DateTimeField = DateTimeField()


class TicketExtraction(BaseModel):
    page_from: int = Field(..., ge=1)
    page_to: int = Field(..., ge=1)
    boundary_uncertain: bool = False  # không chắc ticket bắt đầu/kết thúc ở đâu → REVIEW (BR-12)
    fields: OrderExtraction = OrderExtraction()


class DocumentExtraction(BaseModel):
    """Output Order Agent cho 1 file PDF: 0..n ticket. Không đọc được gì → tickets rỗng."""

    tickets: list[TicketExtraction] = []


class ScheduleExplanation(BaseModel):
    """Output Scheduler Agent — đoạn giải thích phương án sự cố (T-034); mọi giờ/line/số liệu qua validator."""

    text: str = Field(..., max_length=2000)


class EscalationDraft(BaseModel):
    """Output Risk & Escalation Agent — không hứa giờ khác dữ liệu, không nhắc an toàn/liều chiếu."""

    message: str = Field(..., max_length=2000)
