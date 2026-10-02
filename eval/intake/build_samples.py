"""Sinh bộ PDF mẫu vào src/seed/pdfs/ (T-022). Chỉ chạy trên máy dev macOS: cần Google Chrome (in HTML → PDF)
và `sips` (raster → JPEG → PDF cho bản scan). File sinh ra được commit, CI không cần chạy lại.

    .venv/bin/python -m eval.intake.build_samples
"""

import json
import subprocess
import tempfile
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from eval.intake.samples import RECEIVED_AT, SCAN_SAMPLES, TEXT_SAMPLES, answer_key

OUT = Path("src/seed/pdfs")
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def html_to_pdf(html: str, dest: Path, tmp: Path) -> None:
    src = tmp / f"{dest.stem}.html"
    src.write_text(html, encoding="utf-8")
    subprocess.run(
        [CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={dest}", src.as_uri()],
        check=True,
        capture_output=True,
    )


def merge(parts: list[Path], dest: Path) -> None:
    writer = PdfWriter()
    for p in parts:
        for page in PdfReader(p).pages:
            writer.add_page(page)
    writer.add_metadata({"/Title": dest.stem, "/Producer": "ADC sample generator (du lieu gia lap)"})
    with dest.open("wb") as f:
        writer.write(f)


def sips(*args: str) -> None:
    subprocess.run(["sips", *args], check=True, capture_output=True)


def scan_page(page_pdf: Path, dest: Path, *, px: int, quality: int, rotate: float, tmp: Path) -> None:
    """1 trang PDF văn bản → ảnh nhỏ, nén JPEG, nghiêng → PDF chỉ có ảnh (không text layer)."""
    png, jpg = tmp / f"{dest.stem}.png", tmp / f"{dest.stem}.jpg"
    sips("-s", "format", "png", "-Z", str(px), str(page_pdf), "--out", str(png))
    if rotate:
        # sips hiểu số âm là tùy chọn → đổi sang góc dương tương đương
        sips("-r", str(rotate % 360), "--padColor", "FFFFFF", str(png))
    sips("-s", "format", "jpeg", "-s", "formatOptions", str(quality), str(png), "--out", str(jpg))
    sips("-s", "format", "pdf", str(jpg), "--out", str(dest))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        page_pdfs: dict[str, list[Path]] = {}
        for s in TEXT_SAMPLES:
            parts = []
            for i, html in enumerate(s["pages"], 1):
                part = tmp / f"{s['id']}_p{i}.pdf"
                html_to_pdf(html, part, tmp)
                parts.append(part)
            page_pdfs[s["id"]] = parts
            merge(parts, OUT / f"{s['id']}.pdf")
        for s in SCAN_SAMPLES:
            parts = []
            for i, page_pdf in enumerate(page_pdfs[s["source"]], 1):
                part = tmp / f"{s['id']}_p{i}.pdf"
                scan_page(page_pdf, part, px=s["px"], quality=s["quality"], rotate=s["rotate"], tmp=tmp)
                parts.append(part)
            merge(parts, OUT / f"{s['id']}.pdf")
    answers = {"received_at": RECEIVED_AT, "samples": answer_key()}
    (OUT / "answers.json").write_text(json.dumps(answers, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(answers['samples'])} PDF + answers.json → {OUT}")


if __name__ == "__main__":
    main()
