"""Kiểm tra file PDF deterministic lúc upload — ADC-001 §Trường hợp đặc biệt, ADR-0010 (pypdf).

Không đọc nội dung nghiệp vụ (việc của Gemini, T-048); chỉ đếm trang, phát hiện mật khẩu / hỏng, text layer.
"""

import logging
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PyPdfError

logger = logging.getLogger(__name__)
logging.getLogger("pypdf").setLevel(logging.ERROR)  # pypdf log cảnh báo cho mọi PDF lỗi nhẹ

# Trang có ít hơn số ký tự này (bỏ khoảng trắng) coi như không có text layer (bản scan)
MIN_TEXT_CHARS = 20


class InvalidPdfError(Exception):
    """PDF không xử lý được → 422, không tạo lệnh."""


class PdfEncryptedError(InvalidPdfError):
    pass


class PdfCorruptError(InvalidPdfError):
    pass


class PdfTooManyPagesError(InvalidPdfError):
    pass


@dataclass(frozen=True)
class PdfInfo:
    page_count: int
    text_pages: tuple[bool, ...]  # text_pages[i] = trang i+1 có text layer

    @property
    def has_text_layer(self) -> bool:
        return all(self.text_pages)

    @property
    def needs_ocr(self) -> bool:
        return not all(self.text_pages)


def inspect_pdf(path: Path, *, max_pages: int) -> PdfInfo:
    try:
        reader = PdfReader(path)
        # Chỉ có owner password (mật khẩu rỗng mở được) → vẫn đọc được, không coi là "có mật khẩu"
        if reader.is_encrypted and not reader.decrypt(""):
            raise PdfEncryptedError("PDF có mật khẩu")
        page_count = len(reader.pages)
        if page_count == 0:
            raise PdfCorruptError("PDF không có trang nào")
        if page_count > max_pages:
            raise PdfTooManyPagesError(f"PDF có {page_count} trang, tối đa {max_pages}")
        text_pages = tuple(len("".join((p.extract_text() or "").split())) >= MIN_TEXT_CHARS for p in reader.pages)
    except InvalidPdfError:
        raise
    except (PyPdfError, ValueError, KeyError, TypeError, AttributeError) as e:
        # pypdf ném nhiều loại lỗi khác nhau với file hỏng
        logger.info("PDF hỏng: %s", e)
        raise PdfCorruptError("PDF hỏng, không đọc được") from e
    return PdfInfo(page_count=page_count, text_pages=text_pages)
