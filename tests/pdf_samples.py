"""Sinh PDF thật (bằng pypdf) cho test — không commit file nhị phân."""

import io

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

TICKET_TEXT = "PHIEU YEU CAU DICH VU - So luong: 120 thung - Lieu: 10 kGy"


def make_pdf(pages: list[str | None], *, password: str | None = None) -> bytes:
    """`pages[i]` = chữ của trang i+1 (có text layer); None = trang trắng như bản scan không có text layer."""
    writer = PdfWriter()
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    for text in pages:
        page = writer.add_blank_page(width=595, height=842)
        if text is None:
            continue
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
        )
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 72 760 Td ({text}) Tj ET".encode("latin-1"))
        page[NameObject("/Contents")] = writer._add_object(stream)
    if password:
        writer.encrypt(user_password=password, owner_password=password)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


TEXT_PDF = make_pdf([TICKET_TEXT])
SCAN_PDF = make_pdf([None])
