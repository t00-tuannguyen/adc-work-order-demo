from langchain_openai import ChatOpenAI

from src.settings import get_settings


def get_llm(model: str | None = None, timeout_s: float | None = None) -> ChatOpenAI:
    """LLM client dùng chung. Luôn gọi kèm `.with_structured_output(<schema>)` (AGENTS.md §3).

    `model` / `timeout_s` ghi đè cho agent cần riêng (Order Agent đọc PDF, ADR-0013).
    """
    settings = get_settings()
    return ChatOpenAI(
        model=model or settings.model_name,
        api_key=settings.openai_api_key,
        temperature=settings.llm_temperature,
        timeout=timeout_s or settings.llm_timeout_s,
        max_retries=1,
    )
