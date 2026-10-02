"""Lưu file tải lên — thư mục cục bộ ngoài web root (ADR-0002). Không public; đọc lại qua API có kiểm quyền."""

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

CHUNK = 1024 * 1024


class FileTooLargeError(Exception):
    pass


@dataclass(frozen=True)
class StoredFile:
    path: Path
    sha256: str
    size_bytes: int
    head: bytes  # vài KB đầu để kiểm tra chữ ký định dạng


def store_stream(src: BinaryIO, dest: Path, *, max_bytes: int, head_bytes: int = 1024) -> StoredFile:
    """Ghi `src` ra `dest` theo chunk, tính sha256; vượt `max_bytes` → xóa file tạm, FileTooLargeError.

    Ghi vào file tạm cùng thư mục rồi rename → không bao giờ để lại file dở ở `dest`.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    digest, size, head = hashlib.sha256(), 0, b""
    fd, tmp = tempfile.mkstemp(dir=dest.parent, suffix=".part")
    try:
        with os.fdopen(fd, "wb") as out:
            while chunk := src.read(CHUNK):
                size += len(chunk)
                if size > max_bytes:
                    raise FileTooLargeError(f"file vượt {max_bytes} byte")
                if len(head) < head_bytes:
                    head += chunk[: head_bytes - len(head)]
                digest.update(chunk)
                out.write(chunk)
        os.replace(tmp, dest)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return StoredFile(path=dest, sha256=digest.hexdigest(), size_bytes=size, head=head)
