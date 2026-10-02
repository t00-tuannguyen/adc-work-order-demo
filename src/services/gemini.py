"""Gemini client dùng chung — ADR-0010 (đọc PDF, OCR, trích xuất ticket). Luôn gọi kèm `response_schema`."""

from functools import lru_cache

from google import genai
from google.genai import types

from src.settings import get_settings


@lru_cache
def get_gemini_client() -> genai.Client:
    settings = get_settings()
    if not settings.gemini_api_key:
        raise RuntimeError("Thiếu GEMINI_API_KEY")
    return genai.Client(
        api_key=settings.gemini_api_key,
        http_options=types.HttpOptions(timeout=int(settings.gemini_timeout_s * 1000)),
    )
