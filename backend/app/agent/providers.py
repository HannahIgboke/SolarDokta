"""More than one AI company behind the chat, so one being busy or down doesn't break it.

    make_llm()  ->  a ChainLLM that tries, in the order set by LLM_PROVIDERS in .env:
        gemini      Google (GeminiLLM in llm.py, with its own backup models)
        groq        very fast open models (Llama, Qwen, gpt-oss), free tier, no card
        cerebras    also very fast open models, free tier, no card
        openrouter  one key for many free models
        github      GitHub Models (free with a GitHub account)
        mistral     Mistral's own models (free "Experiment" plan)

All except Gemini speak the same "OpenAI-style" API, so one small class (OpenAICompatLLM)
talks to every one of them: only the web address, key and model name change.

If a provider fails (busy, out of quota, slow, offline), the chain moves straight to the next
one and skips the failed provider for a few minutes, so the next customer doesn't wait for it
again. A provider with no key in .env is simply left out.
"""

import json
import logging
import time

import httpx

from app.agent.llm import LLMError, LLMTurn
from app.config import get_settings

log = logging.getLogger(__name__)

# name -> (web address, settings field with the key, settings field with the model)
OPENAI_STYLE = {
    "groq": ("https://api.groq.com/openai/v1", "groq_api_key", "groq_model"),
    "cerebras": ("https://api.cerebras.ai/v1", "cerebras_api_key", "cerebras_model"),
    "openrouter": ("https://openrouter.ai/api/v1", "openrouter_api_key", "openrouter_model"),
    "github": ("https://models.github.ai/inference", "github_models_token", "github_model"),
    "mistral": ("https://api.mistral.ai/v1", "mistral_api_key", "mistral_model"),
}


class OpenAICompatLLM:
    """Any provider with an OpenAI-style /chat/completions endpoint."""

    def __init__(self, name: str, base_url: str, api_key: str, model: str,
                 timeout_s: float = 12.0, transport: httpx.BaseTransport | None = None):
        if not api_key:
            raise LLMError(f"No API key for {name}")
        self.name, self.model = name, model
        self.models = [model]
        self.last_model = None
        self.http = httpx.Client(base_url=base_url, timeout=timeout_s, transport=transport,
                                 headers={"Authorization": f"Bearer {api_key}"})

    @staticmethod
    def _messages(system: str, messages: list[dict]) -> list[dict]:
        out = [{"role": "system", "content": system}]
        ids: list[str] = []                    # ids of the last tool calls (Gemini may not give any)
        for n, m in enumerate(messages):
            if m["role"] == "user":
                out.append({"role": "user", "content": m["text"]})
            elif m["role"] == "model":
                calls = m.get("calls") or []
                ids = [c.get("id") or f"call_{n}_{k}" for k, c in enumerate(calls)]
                msg = {"role": "assistant", "content": m.get("text") or ""}
                if calls:
                    msg["tool_calls"] = [
                        {"id": i, "type": "function",
                         "function": {"name": c["name"], "arguments": json.dumps(c.get("args") or {})}}
                        for i, c in zip(ids, calls, strict=True)]
                out.append(msg)
            elif m["role"] == "tool":
                for k, r in enumerate(m["results"]):
                    out.append({"role": "tool",
                                "tool_call_id": r.get("id") or (ids[k] if k < len(ids) else f"call_{k}"),
                                "content": json.dumps(r["result"], default=str)})
        return out

    def generate(self, system: str, messages: list[dict], tools: list[dict],
                 allow_tools: bool = True) -> LLMTurn:
        body = {"model": self.model, "messages": self._messages(system, messages),
                "temperature": 0.3, "max_tokens": 400}
        if tools:
            body["tools"] = [{"type": "function", "function": {
                "name": t["name"], "description": t["description"], "parameters": t["parameters"]}}
                for t in tools]
            body["tool_choice"] = "auto" if allow_tools else "none"
        try:
            resp = self.http.post("/chat/completions", json=body)
        except httpx.HTTPError as exc:          # timeout, offline, connection reset
            raise LLMError(f"{self.name}: {type(exc).__name__}") from exc
        if resp.status_code != 200:
            raise LLMError(f"{self.name} error {resp.status_code}: {resp.text[:200]}")
        try:
            msg = resp.json()["choices"][0]["message"]
            calls = [{"id": c["id"], "name": c["function"]["name"],
                      "args": json.loads(c["function"].get("arguments") or "{}")}
                     for c in (msg.get("tool_calls") or [])]
        except (KeyError, IndexError, ValueError) as exc:
            raise LLMError(f"{self.name} sent an answer we couldn't read") from exc
        self.last_model = f"{self.name}:{self.model}"
        return LLMTurn(text=(msg.get("content") or "").strip(), calls=calls, raw=None)


class ChainLLM:
    """Try each provider in turn; skip one that just failed for SKIP seconds."""

    SKIP = 300

    def __init__(self, providers: list):
        if not providers:
            raise LLMError("No AI provider is set up: add GEMINI_API_KEY or GROQ_API_KEY to .env")
        self.providers = providers
        self._down: dict[int, float] = {}       # provider index -> skip until (time)
        self.last_model = None
        self.model = getattr(providers[0], "model", "?")
        self.models = [m for p in providers for m in getattr(p, "models", [])]

    def generate(self, system, messages, tools, allow_tools=True) -> LLMTurn:
        now = time.time()
        up = [i for i in range(len(self.providers)) if self._down.get(i, 0) <= now]
        order = up + [i for i in range(len(self.providers)) if i not in up]   # all down: try anyway
        problem = "none tried"
        for i in order:
            p = self.providers[i]
            try:
                turn = p.generate(system, messages, tools, allow_tools)
            except LLMError as exc:
                problem = str(exc)
                self._down[i] = time.time() + self.SKIP
                log.warning("%s failed (%s); trying the next provider", _name(p), problem[:200])
                continue
            self._down.pop(i, None)
            self.last_model = getattr(p, "last_model", None) or _name(p)
            return turn
        raise LLMError(f"Every AI provider failed (last: {problem})")


def _name(p) -> str:
    return getattr(p, "name", type(p).__name__)


def make_llm() -> ChainLLM:
    from app.agent.llm import GeminiLLM

    s = get_settings()
    providers = []
    for name in [n.strip().lower() for n in s.llm_providers.split(",") if n.strip()]:
        try:
            if name == "gemini":
                if s.gemini_api_key:
                    providers.append(GeminiLLM())
            elif name in OPENAI_STYLE:
                url, key_field, model_field = OPENAI_STYLE[name]
                if getattr(s, key_field):
                    providers.append(OpenAICompatLLM(name, url, getattr(s, key_field),
                                                     getattr(s, model_field), s.llm_timeout_s))
            else:
                log.warning("Unknown provider %r in LLM_PROVIDERS", name)
        except LLMError as exc:
            log.warning("Skipping %s: %s", name, exc)
    return ChainLLM(providers)
