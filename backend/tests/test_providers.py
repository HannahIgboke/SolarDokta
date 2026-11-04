"""The chain of AI providers: OpenAI-style message format, tool calls, and falling through."""

import json

import httpx
import pytest

from app.agent.llm import LLMError, LLMTurn
from app.agent.providers import ChainLLM, OpenAICompatLLM

TOOLS = [{"name": "battery_now", "description": "battery", "parameters": {"type": "object", "properties": {}}}]


def fake_provider(handler):
    return OpenAICompatLLM("groq", "https://api.test/v1", "key", "llama", transport=httpx.MockTransport(handler))


def test_openai_style_tool_call_and_reply():
    seen = []

    def handler(request):
        body = json.loads(request.content)
        seen.append(body)
        if len(seen) == 1:
            return httpx.Response(200, json={"choices": [{"message": {"content": None, "tool_calls": [
                {"id": "c1", "type": "function", "function": {"name": "battery_now", "arguments": "{}"}}]}}]})
        return httpx.Response(200, json={"choices": [{"message": {"content": "Your battery is 64%."}}]})

    p = fake_provider(handler)
    turn = p.generate("sys", [{"role": "user", "text": "battery?"}], TOOLS)
    assert turn.calls == [{"id": "c1", "name": "battery_now", "args": {}}]
    assert seen[0]["tools"][0]["function"]["name"] == "battery_now" and seen[0]["tool_choice"] == "auto"
    history = [{"role": "user", "text": "battery?"},
               {"role": "model", "text": "", "calls": turn.calls},
               {"role": "tool", "results": [{"id": "c1", "name": "battery_now", "result": {"percent": 64}}]}]
    final = p.generate("sys", history, TOOLS, allow_tools=False)
    assert final.text == "Your battery is 64%." and p.last_model == "groq:llama"
    msgs = seen[1]["messages"]
    assert [m["role"] for m in msgs] == ["system", "user", "assistant", "tool"]
    assert msgs[3]["tool_call_id"] == "c1" and seen[1]["tool_choice"] == "none"


def test_missing_call_ids_from_gemini_get_matched():
    msgs = OpenAICompatLLM._messages("s", [
        {"role": "user", "text": "q"},
        {"role": "model", "text": "", "calls": [{"id": None, "name": "battery_now", "args": {}}]},
        {"role": "tool", "results": [{"id": None, "name": "battery_now", "result": {}}]}])
    assert msgs[2]["tool_calls"][0]["id"] == msgs[3]["tool_call_id"]


def test_errors_become_llm_errors():
    p = fake_provider(lambda r: httpx.Response(429, text="rate limited"))
    with pytest.raises(LLMError, match="429"):
        p.generate("s", [{"role": "user", "text": "hi"}], TOOLS)

    def offline(request):
        raise httpx.ConnectError("getaddrinfo failed")
    with pytest.raises(LLMError, match="ConnectError"):
        fake_provider(offline).generate("s", [{"role": "user", "text": "hi"}], TOOLS)


class Down:
    name, model, calls = "gemini", "flash", 0

    def generate(self, *a, **k):
        Down.calls += 1
        raise LLMError("504")


class Up:
    name, model, last_model = "groq", "llama", "groq:llama"

    def generate(self, *a, **k):
        return LLMTurn(text="ok")


def test_chain_falls_through_and_skips_the_failed_one():
    Down.calls = 0
    chain = ChainLLM([Down(), Up()])
    assert chain.generate("s", [], TOOLS).text == "ok" and chain.last_model == "groq:llama"
    chain.generate("s", [], TOOLS)
    assert Down.calls == 1                       # skipped for a few minutes after failing
    with pytest.raises(LLMError, match="Every AI provider failed"):
        ChainLLM([Down()]).generate("s", [], TOOLS)
    with pytest.raises(LLMError, match="No AI provider"):
        ChainLLM([])
