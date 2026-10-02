from langchain_openai import ChatOpenAI

from src.settings import get_settings


def get_llm() -> ChatOpenAI:
    """LLM client dùng chung. Luôn gọi kèm `.with_structured_output(<schema>)` (AGENTS.md §3)."""
    settings = get_settings()
    return ChatOpenAI(
        model=settings.model_name,
        api_key=settings.openai_api_key,
        temperature=settings.llm_temperature,
        timeout=settings.llm_timeout_s,
        max_retries=1,
    )
