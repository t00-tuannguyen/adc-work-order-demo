import pytest

from src.services import gemini
from src.settings import Settings


def test_client_requires_api_key(monkeypatch):
    monkeypatch.setattr(gemini, "get_settings", lambda: Settings(_env_file=None, gemini_api_key=""))
    gemini.get_gemini_client.cache_clear()
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        gemini.get_gemini_client()
    gemini.get_gemini_client.cache_clear()
