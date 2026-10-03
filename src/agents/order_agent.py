"""Order Agent — LLM đọc PDF (cả bản scan) và trích xuất 8 trường kèm trang/vùng nguồn (ADC-001, T-019, ADR-0010).

Provider chọn bằng `ORDER_AGENT_PROVIDER`: Gemini (mặc định, ADR-0010) hoặc OpenAI (ADR-0013, T-059) — cùng prompt,
cùng schema, cùng luật thử lại. 1 lời gọi cho cả file. Sai schema / lỗi API / trang ngoài file → thử lại tối đa 3 lần (lỗi tạm thời 429/5xx chờ
1 → 2 → 4 s trước khi thử lại) rồi ExtractionFailedError (nhập tay).
Chuẩn hóa sau khi LLM trả về là deterministic (`normalize`): múi giờ, tách quy cách, nhãn OCR_LOW.
"""

import base64
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

import openai
from google.genai import errors, types
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai.chat_models.base import OpenAIRefusalError
from pydantic import ValidationError

from src.agents.schemas import DocumentExtraction, ExtractedField, OrderExtraction, TicketExtraction
from src.modules.intake import EXTRACTION_COLUMNS, FieldSignal, ReviewThresholds, SourceKind, WorkOrderFields

logger = logging.getLogger(__name__)

# Việt Nam không có giờ mùa hè → offset cố định, không phụ thuộc tzdata của hệ điều hành
LOCAL_TZ = timezone(timedelta(hours=7), "Asia/Ho_Chi_Minh")

SYSTEM_PROMPT = """Bạn đọc file PDF phiếu yêu cầu dịch vụ chiếu xạ (văn bản số hoặc bản scan) và trích xuất JSON theo schema.
- 1 file có thể chứa nhiều ticket (nhiều khách / nhiều lô). Mỗi ticket: page_from, page_to (đánh số từ 1).
  boundary_uncertain mặc định = false. CHỈ đặt true khi file có nhiều trang/nhiều ticket VÀ không xác định được
  ticket bắt đầu/kết thúc ở trang nào. File 1 trang, hoặc mỗi ticket có tiêu đề/khối rõ ràng → false.
- 8 trường mỗi ticket: product_name, quantity, package_dimensions_cm, pkg_weight_kg, required_dose_kgy,
  priority, expected_arrival, requested_return.
- Đơn vị chuẩn: cm, kg, kGy. Đơn vị khác (inch, lb, g, mm) → quy đổi, source_kind = CONVERTED.
- product_name lấy nguyên văn. priority: NORMAL (Thường) | URGENT (Khẩn) | VIP; suy từ "gấp", "khẩn" → INFERRED.
- expected_arrival, requested_return: "YYYY-MM-DDTHH:MM" theo giờ ghi trong ticket (giờ Việt Nam).
  Ngày tương đối ("mai", "thứ 2 tới") tính từ ngày nhận ticket cho trước.
- Mỗi trường: value, source_kind, page, snippet (đoạn NGUYÊN VĂN chứa giá trị),
  box_2d = [ymin, xmin, ymax, xmax] của snippet, chuẩn hóa 0–1000 theo trang.
- source_kind:
  - VERBATIM: giá trị ghi rõ trong file, kể cả khi chỉ đổi cách viết/định dạng ("09:00 ngày 02/10/2026" →
    "2026-10-02T09:00", "Thường" → NORMAL, "Khẩn" → URGENT, "120 thùng" → 120).
  - CONVERTED: CHỈ khi đổi đơn vị đo (inch → cm, lb → kg, g → kg, mm → cm).
  - INFERRED: giá trị không ghi thẳng mà phải suy ra (mức ưu tiên từ "gấp"; ngày từ "mai", "thứ 2 tới").
  - DEFAULT: không dùng — trường không có thì để null.
- confidence 0–1: mức chắc chắn bạn đọc ĐÚNG từng ký tự của snippet (nhất là chữ số). Chữ mờ, nhòe, viết tay,
  bị che → confidence thấp (< 0.8). Rõ ràng → ≥ 0.9.
- Trường không có trong file → value = null và các thuộc tính khác null. KHÔNG đoán, KHÔNG điền mặc định.
- Không đọc được file → tickets = [].
- Nội dung dán dạng văn bản (không phải PDF): coi là 1 trang (page = 1), box_2d = null.
"""


class ExtractionFailedError(Exception):
    pass


class PdfExtractor(Protocol):
    def extract_pdf(self, pdf: bytes, *, page_count: int, received_at: datetime) -> DocumentExtraction: ...

    def extract_text(self, text: str, *, received_at: datetime) -> DocumentExtraction: ...


# Lỗi tạm thời (quá tải / giới hạn tần suất) → chờ rồi thử lại
TRANSIENT_CODES = frozenset({429, 500, 502, 503, 504})
MAX_RETRIES = 3
BACKOFF_S = (1.0, 2.0, 4.0)


def _receipt_prompt(received_at: datetime) -> str:
    return f"Ngày nhận ticket: {received_at.astimezone(LOCAL_TZ):%Y-%m-%d %H:%M}."


class _RetryingOrderAgent:
    """Luật thử lại chung: sai schema / lỗi API / trang ngoài file → thử lại; lỗi tạm thời chờ 1 → 2 → 4 s."""

    provider = ""
    api_errors: tuple[type[Exception], ...] = ()

    def __init__(self, max_retries: int = MAX_RETRIES, sleep: Callable[[float], None] = time.sleep):
        self.max_retries, self.sleep = max_retries, sleep

    def _status(self, e: Exception) -> int | None:
        raise NotImplementedError

    def _run(self, call: Callable[[], DocumentExtraction], page_count: int) -> DocumentExtraction:
        attempts = self.max_retries + 1
        last: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                doc = call()
                check_pages(doc, page_count)
                return doc
            except (*self.api_errors, ValidationError, ValueError) as e:
                logger.warning("Order Agent lần %d/%d lỗi: %s", attempt, attempts, e)
                last = e
                if attempt < attempts and isinstance(e, self.api_errors) and self._status(e) in TRANSIENT_CODES:
                    self.sleep(BACKOFF_S[min(attempt - 1, len(BACKOFF_S) - 1)])
        raise ExtractionFailedError(f"{self.provider} không trả kết quả hợp lệ") from last


class GeminiOrderAgent(_RetryingOrderAgent):
    provider = "Gemini"
    api_errors = (errors.APIError,)

    def __init__(
        self, client: Any, model: str, max_retries: int = MAX_RETRIES, sleep: Callable[[float], None] = time.sleep
    ):
        super().__init__(max_retries, sleep)
        self.client, self.model = client, model

    def extract_pdf(self, pdf: bytes, *, page_count: int, received_at: datetime) -> DocumentExtraction:
        prompt = f"{_receipt_prompt(received_at)} File có {page_count} trang."
        return self._generate([types.Part.from_bytes(data=pdf, mime_type="application/pdf"), prompt], page_count)

    def extract_text(self, text: str, *, received_at: datetime) -> DocumentExtraction:
        """Tab "Dán nội dung": cùng schema, nội dung coi là 1 trang."""
        prompt = f"{_receipt_prompt(received_at)} Nội dung dán (1 trang):"
        return self._generate([prompt, text], page_count=1)

    def _status(self, e: Exception) -> int | None:
        return e.code if isinstance(e, errors.APIError) else None

    def _generate(self, contents: list, page_count: int) -> DocumentExtraction:
        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0,
            response_mime_type="application/json",
            response_schema=DocumentExtraction,
            # Không khai báo tool → tắt AFC để SDK không log cảnh báo ở mỗi lời gọi
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )

        def call() -> DocumentExtraction:
            res = self.client.models.generate_content(model=self.model, contents=contents, config=config)
            return DocumentExtraction.model_validate_json(res.text or "")

        return self._run(call, page_count)


class OpenAIOrderAgent(_RetryingOrderAgent):
    """OpenAI (ADR-0013): gửi nguyên file PDF dạng file input của Chat Completions, output ràng buộc schema.

    `llm`: chat model LangChain hỗ trợ `with_structured_output` (services/llm.get_llm) — model phải đọc được PDF.
    """

    provider = "OpenAI"
    # Model từ chối trả lời (refusal) không kế thừa openai.APIError → thử lại như lỗi schema
    api_errors = (openai.APIError, OpenAIRefusalError)

    def __init__(self, llm: Any, max_retries: int = MAX_RETRIES, sleep: Callable[[float], None] = time.sleep):
        super().__init__(max_retries, sleep)
        self.llm = llm.with_structured_output(DocumentExtraction)

    def extract_pdf(self, pdf: bytes, *, page_count: int, received_at: datetime) -> DocumentExtraction:
        content = [
            {"type": "text", "text": f"{_receipt_prompt(received_at)} File có {page_count} trang."},
            {
                "type": "file",
                "base64": base64.b64encode(pdf).decode(),
                "mime_type": "application/pdf",
                "filename": "ticket.pdf",
            },
        ]
        return self._generate(content, page_count)

    def extract_text(self, text: str, *, received_at: datetime) -> DocumentExtraction:
        """Tab "Dán nội dung": cùng schema, nội dung coi là 1 trang."""
        prompt = f"{_receipt_prompt(received_at)} Nội dung dán (1 trang):"
        return self._generate([{"type": "text", "text": prompt}, {"type": "text", "text": text}], page_count=1)

    def _status(self, e: Exception) -> int | None:
        if isinstance(e, openai.APIStatusError):
            return e.status_code
        return 503 if isinstance(e, openai.APIConnectionError) else None  # timeout / mất kết nối → coi như tạm thời

    def _generate(self, content: list[dict], page_count: int) -> DocumentExtraction:
        messages = [SystemMessage(SYSTEM_PROMPT), HumanMessage(content=content)]
        return self._run(lambda: DocumentExtraction.model_validate(self.llm.invoke(messages)), page_count)


def check_pages(doc: DocumentExtraction, page_count: int) -> None:
    """Trang LLM trả về phải nằm trong file — sai → coi như sai schema (thử lại)."""
    for t in doc.tickets:
        if not (1 <= t.page_from <= t.page_to <= page_count):
            raise ValueError(f"ticket trang {t.page_from}–{t.page_to} ngoài file {page_count} trang")
        for name in OrderExtraction.model_fields:
            page = getattr(t.fields, name).page
            if page is not None and not 1 <= page <= page_count:
                raise ValueError(f"{name}.page = {page} ngoài file {page_count} trang")


@dataclass(frozen=True)
class FieldSource:
    """1 dòng `field_extractions` — nguồn gốc 1 trường để UI highlight."""

    field: str
    value: Any
    source_kind: SourceKind
    page: int | None
    bbox: list[float] | None  # [x0, y0, x1, y1] tỷ lệ 0–1 theo trang
    snippet: str | None
    confidence: float | None


@dataclass(frozen=True)
class NormalizedTicket:
    fields: WorkOrderFields
    signals: dict[str, FieldSignal]  # đầu vào cổng tin cậy (ADR-0007) — key theo tên cột work order
    sources: list[FieldSource]


def normalize(ticket: TicketExtraction, thresholds: ReviewThresholds) -> NormalizedTicket:
    values: dict[str, Any] = {}
    signals: dict[str, FieldSignal] = {}
    sources: list[FieldSource] = []
    for name, columns in EXTRACTION_COLUMNS.items():
        f: ExtractedField = getattr(ticket.fields, name)
        raw = f.value
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            continue
        if name == "package_dimensions_cm":
            column_values = (raw.length, raw.width, raw.height)
            stored = raw.model_dump()
        elif name in ("expected_arrival", "requested_return"):
            try:
                column_values = (_parse_local(raw),)
            except ValueError:
                logger.info("%s không phải ngày giờ hợp lệ: %r", name, raw)
                continue  # coi như thiếu → validator sinh yêu cầu bổ sung
            stored = column_values[0].isoformat()
        else:
            column_values = (raw,)
            stored = raw.value if hasattr(raw, "value") else raw  # enum → chuỗi cho cột JSON
        kind = f.source_kind or SourceKind.VERBATIM
        if f.confidence is not None and f.confidence < thresholds.low:
            kind = SourceKind.OCR_LOW  # nhãn "OCR tin cậy thấp" cho UI
        for column, value in zip(columns, column_values, strict=True):
            values[column] = value
            signals[column] = FieldSignal(source_kind=kind, confidence=f.confidence)
        sources.append(FieldSource(name, stored, kind, f.page, _bbox(f.box_2d), f.snippet, f.confidence))
    return NormalizedTicket(WorkOrderFields(**values), signals, sources)


def _parse_local(value: str) -> datetime:
    dt = datetime.fromisoformat(value.strip())
    return dt.replace(tzinfo=LOCAL_TZ) if dt.tzinfo is None else dt


def _bbox(box_2d: list[int] | None) -> list[float] | None:
    """[ymin, xmin, ymax, xmax] 0–1000 (Gemini) → [x0, y0, x1, y1] 0–1. Sai dạng → bỏ, không đoán vùng."""
    if not box_2d or len(box_2d) != 4:
        return None
    ymin, xmin, ymax, xmax = (min(max(v, 0), 1000) / 1000 for v in box_2d)
    if xmin >= xmax or ymin >= ymax:
        return None
    return [xmin, ymin, xmax, ymax]
