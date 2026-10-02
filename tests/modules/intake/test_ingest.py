"""T-018 — job xử lý: tiến độ theo bước, kiểm tra chữ ký PDF."""

import pytest

from src.modules.intake import PROGRESS, IngestStep, is_pdf


@pytest.mark.parametrize(
    ("head", "ok"),
    [(b"%PDF-1.4\n", True), (b"\xef\xbb\xbf  %PDF-2.0", True), (b"\x89PNG", False), (b"", False)],
)
def test_is_pdf_checks_magic_bytes(head, ok):
    assert is_pdf(head) is ok


def test_progress_is_monotonic_over_ui_steps():
    order = [IngestStep.UPLOADED, IngestStep.READING, IngestStep.DETECTING, IngestStep.EXTRACTING, IngestStep.DONE]
    values = [PROGRESS[s] for s in order]
    assert values == sorted(values) and values[-1] == 100
    assert set(PROGRESS) == set(IngestStep)
