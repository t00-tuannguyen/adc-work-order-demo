"""T-048 — kiểm tra PDF deterministic (pypdf, ADR-0010)."""

import pytest

from src.modules.intake import (
    IngestError,
    PdfCorruptError,
    PdfEncryptedError,
    PdfTooManyPagesError,
    TicketFile,
    check_ocr_allowed,
    inspect_pdf,
)
from tests.pdf_samples import SCAN_PDF, TEXT_PDF, TICKET_TEXT, make_pdf


def _write(tmp_path, data: bytes):
    path = tmp_path / "f.pdf"
    path.write_bytes(data)
    return path


def test_text_pdf(tmp_path):
    info = inspect_pdf(_write(tmp_path, TEXT_PDF), max_pages=20)
    assert (info.page_count, info.text_pages, info.has_text_layer, info.needs_ocr) == (1, (True,), True, False)


def test_scan_and_mixed_pdf_need_ocr(tmp_path):
    assert inspect_pdf(_write(tmp_path, SCAN_PDF), max_pages=20).needs_ocr
    info = inspect_pdf(_write(tmp_path, make_pdf([TICKET_TEXT, None, TICKET_TEXT])), max_pages=20)
    assert info.text_pages == (True, False, True) and not info.has_text_layer


def test_owner_password_only_is_readable(tmp_path):
    """Chỉ khóa quyền chỉnh sửa (mật khẩu mở rỗng) → vẫn đọc được."""
    info = inspect_pdf(_write(tmp_path, make_pdf([TICKET_TEXT], password="")), max_pages=20)
    assert info.page_count == 1


def test_user_password_is_rejected(tmp_path):
    with pytest.raises(PdfEncryptedError):
        inspect_pdf(_write(tmp_path, make_pdf([TICKET_TEXT], password="x")), max_pages=20)


def test_page_limit_is_inclusive(tmp_path):
    assert inspect_pdf(_write(tmp_path, make_pdf([TICKET_TEXT] * 3)), max_pages=3).page_count == 3
    with pytest.raises(PdfTooManyPagesError):
        inspect_pdf(_write(tmp_path, make_pdf([TICKET_TEXT] * 4)), max_pages=3)


@pytest.mark.parametrize("data", [TEXT_PDF[:200], b"%PDF-1.4\n%%EOF", b""])
def test_corrupt_pdf(tmp_path, data):
    with pytest.raises(PdfCorruptError):
        inspect_pdf(_write(tmp_path, data), max_pages=20)


@pytest.mark.parametrize(
    ("ocr_used", "enabled", "fails"), [(True, False, True), (True, True, False), (False, False, False)]
)
def test_ocr_feature_flag(ocr_used, enabled, fails):
    f = TicketFile(ocr_used=ocr_used)
    if fails:
        with pytest.raises(IngestError) as e:
            check_ocr_allowed(f, enabled=enabled)
        assert e.value.error_code == "OCR_FAILED"
    else:
        check_ocr_allowed(f, enabled=enabled)
