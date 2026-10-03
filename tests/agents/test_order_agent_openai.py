"""T-059 — Order Agent chạy trên OpenAI (ADR-0013): gửi PDF dạng file input, cùng schema & luật thử lại như Gemini."""

import base64

import httpx
import openai
import pytest
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai.chat_models.base import OpenAIRefusalError

from src.agents.order_agent import SYSTEM_PROMPT, ExtractionFailedError, OpenAIOrderAgent
from src.agents.schemas import DocumentExtraction
from src.api.intake import get_order_agent
from src.settings import Settings
from tests.agents.test_order_agent import RECEIVED, full_ticket

GOOD = DocumentExtraction.model_validate({"tickets": [full_ticket()]})
REQ = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")


class FakeLLM:
    def __init__(self, *replies):
        self.replies, self.calls, self.schema = list(replies), [], None

    def with_structured_output(self, schema):
        self.schema = schema
        return self

    def invoke(self, messages):
        self.calls.append(messages)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def status_error(code: int) -> openai.APIStatusError:
    return openai.APIStatusError("lỗi", response=httpx.Response(code, request=REQ), body=None)


def agent(*replies, sleeps=None):
    llm = FakeLLM(*replies)
    sleep = sleeps.append if sleeps is not None else lambda s: None
    return OpenAIOrderAgent(llm, sleep=sleep), llm


def test_sends_whole_pdf_as_file_with_schema_and_prompt():
    a, llm = agent(GOOD)
    doc = a.extract_pdf(b"%PDF-1.7 ...", page_count=1, received_at=RECEIVED)
    assert doc == GOOD and llm.schema is DocumentExtraction
    system, human = llm.calls[0]
    assert isinstance(system, SystemMessage) and system.content == SYSTEM_PROMPT
    assert isinstance(human, HumanMessage)
    text, file = human.content
    assert "2026-10-01 08:00" in text["text"] and "1 trang" in text["text"]  # giờ Việt Nam
    assert file["type"] == "file" and file["mime_type"] == "application/pdf"
    assert base64.b64decode(file["base64"]) == b"%PDF-1.7 ..."


def test_extract_text_sends_text_as_one_page():
    a, llm = agent(GOOD)
    a.extract_text("Gửi 120 thùng bột ớt", received_at=RECEIVED)
    parts = llm.calls[0][1].content
    assert [p["type"] for p in parts] == ["text", "text"] and parts[1]["text"] == "Gửi 120 thùng bột ớt"


def test_overloaded_waits_with_backoff_then_succeeds():
    sleeps = []
    a, llm = agent(status_error(503), status_error(429), status_error(500), GOOD, sleeps=sleeps)
    assert a.extract_pdf(b"%PDF", page_count=1, received_at=RECEIVED) == GOOD
    assert len(llm.calls) == 4 and sleeps == [1.0, 2.0, 4.0]


def test_connection_error_is_transient():
    sleeps = []
    a, _ = agent(openai.APIConnectionError(request=REQ), GOOD, sleeps=sleeps)
    a.extract_pdf(b"%PDF", page_count=1, received_at=RECEIVED)
    assert sleeps == [1.0]


def test_client_error_and_bad_pages_retry_without_waiting_then_fail():
    sleeps = []
    out_of_file = DocumentExtraction.model_validate({"tickets": [full_ticket() | {"page_to": 3}]})
    a, llm = agent(status_error(400), out_of_file, ValueError("parse"), OpenAIRefusalError("từ chối"), sleeps=sleeps)
    with pytest.raises(ExtractionFailedError, match="OpenAI"):
        a.extract_pdf(b"%PDF", page_count=1, received_at=RECEIVED)
    assert len(llm.calls) == 4 and sleeps == []


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ({"gemini_api_key": "g"}, "GeminiOrderAgent"),
        ({"order_agent_provider": "openai", "openai_api_key": "sk-test"}, "OpenAIOrderAgent"),
        ({"order_agent_provider": "openai", "openai_api_key": "", "gemini_api_key": "g"}, None),
        ({"gemini_api_key": "", "openai_api_key": "sk-test"}, None),
    ],
)
def test_provider_is_chosen_by_setting(env, expected, monkeypatch):
    monkeypatch.setattr("src.api.intake.get_gemini_client", lambda: object())
    settings = Settings(_env_file=None, **env)
    monkeypatch.setattr("src.services.llm.get_settings", lambda: settings)
    agent = get_order_agent(settings)
    assert (type(agent).__name__ if agent else None) == expected
