import hashlib
import io

import pytest

from src.services.storage import FileTooLargeError, store_stream


def test_store_stream_writes_file_and_hash(tmp_path):
    data = b"x" * 3_000_000  # > 1 chunk
    stored = store_stream(io.BytesIO(data), tmp_path / "a.pdf", max_bytes=len(data), head_bytes=8)
    assert stored.path.read_bytes() == data
    assert (stored.sha256, stored.size_bytes, stored.head) == (hashlib.sha256(data).hexdigest(), len(data), b"x" * 8)


def test_store_stream_over_limit_leaves_nothing(tmp_path):
    with pytest.raises(FileTooLargeError):
        store_stream(io.BytesIO(b"x" * 11), tmp_path / "a.pdf", max_bytes=10)
    assert list(tmp_path.iterdir()) == []
