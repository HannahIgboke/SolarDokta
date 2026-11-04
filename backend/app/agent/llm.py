"""The connection to Gemini (Google's LLM), behind a tiny interface so it can be swapped or faked.

The agent speaks in plain Python messages:
    {"role": "user",  "text": "Can I iron now?"}
    {"role": "model", "text": "...", "calls": [{"id", "name", "args"}], "raw": <Gemini content>}
    {"role": "tool",  "results": [{"id", "name", "result": {...}}]}
and an LLM answers with an LLMTurn: either text, or a list of tool calls to run first.

Built for speed, because a customer on WhatsApp won't wait:
- "thinking" is turned down as far as each model allows (it adds seconds and isn't needed
  for short answers). Models differ in which setting they accept, so we try the fastest first
- every call has a time limit; a slow or busy model is skipped at once for the next backup,
  instead of waiting and retrying
Tests use a scripted fake LLM instead of Gemini (no internet, no API key, no quota).
"""

import logging
import time
from dataclasses import dataclass, field

import httpx

from app.config import get_settings

log = logging.getLogger(__name__)


@dataclass
class LLMTurn:
    text: str = ""
    calls: list[dict] = field(default_factory=list)   # [{"id", "name", "args"}]
    raw: object = None                                # provider's own message, sent back as-is


class LLMError(RuntimeError):
    """The AI could not answer (no key, quota used up, server down, offline)."""


def _thinking_options():
    from google.genai import types

    return [types.ThinkingConfig(thinking_level="minimal"),   # newest models: fastest
            types.ThinkingConfig(thinking_level="low"),
            types.ThinkingConfig(thinking_budget=0),          # Gemini 2.5 models: thinking off
            None]                                             # model default


class GeminiLLM:
    SWITCH = frozenset({403, 404, 429, 500, 503, 504})   # busy, out of quota, not available
    STICK = 600                    # after switching, stay on the backup for 10 minutes

    def __init__(self, api_key: str | None = None, model: str | None = None):
        from google import genai  # imported here so tests don't need the package
        from google.genai import types

        s = get_settings()
        key = api_key or s.gemini_api_key
        if not key:
            raise LLMError("Set GEMINI_API_KEY in the .env file")
        self.model = model or s.gemini_model
        backups = [m.strip() for m in s.gemini_backup_models.split(",") if m.strip()]
        self.models = [self.model] + [m for m in backups if m != self.model]
        self._backup, self._backup_until = None, 0.0
        self._thinking: dict[str, int] = {}          # model -> which THINKING option it accepts
        self.last_model = None
        self.client = genai.Client(api_key=key, http_options=types.HttpOptions(
            timeout=int(s.gemini_timeout_s * 1000)))

    def _contents(self, messages: list[dict]):
        from google.genai import types

        out = []
        for m in messages:
            if m["role"] == "user":
                out.append(types.Content(role="user", parts=[types.Part.from_text(text=m["text"])]))
            elif m["role"] == "model":
                if isinstance(m.get("raw"), types.Content):   # keeps Gemini's "thought signatures"
                    out.append(m["raw"])
                else:                                # written by another provider (or no raw)
                    parts = [types.Part.from_text(text=m["text"])] if m.get("text") else []
                    parts += [types.Part(function_call=types.FunctionCall(
                        id=c.get("id"), name=c["name"], args=c.get("args") or {}))
                        for c in m.get("calls") or []]
                    out.append(types.Content(role="model", parts=parts or [types.Part.from_text(text="")]))
            elif m["role"] == "tool":
                out.append(types.Content(role="user", parts=[
                    types.Part(function_response=types.FunctionResponse(
                        id=r.get("id"), name=r["name"], response={"result": r["result"]}))
                    for r in m["results"]]))
        return out

    def _config(self, model: str, system: str, tools: list[dict], allow_tools: bool):
        from google.genai import types

        return types.GenerateContentConfig(
            system_instruction=system,
            tools=[types.Tool(function_declarations=[
                types.FunctionDeclaration(
                    name=t["name"], description=t["description"],
                    parameters_json_schema=t["parameters"] if t["parameters"].get("properties")
                    else None)                        # tools without arguments: no schema
                for t in tools])] if tools else None,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            tool_config=types.ToolConfig(function_calling_config=types.FunctionCallingConfig(
                mode="AUTO" if allow_tools else "NONE")) if tools else None,
            thinking_config=_thinking_options()[self._thinking.get(model, 0)],
            temperature=0.3,
            max_output_tokens=400,                    # WhatsApp replies are short
        )

    def generate(self, system: str, messages: list[dict], tools: list[dict],
                 allow_tools: bool = True) -> LLMTurn:
        resp = self._call(self._contents(messages), system, tools, allow_tools)
        if not resp.candidates or resp.candidates[0].content is None:
            raise LLMError(f"Gemini gave no answer (finish reason: "
                           f"{resp.candidates[0].finish_reason if resp.candidates else 'blocked'})")
        content = resp.candidates[0].content
        calls = [{"id": fc.id, "name": fc.name, "args": dict(fc.args or {})}
                 for fc in (resp.function_calls or [])]
        text = "".join(p.text for p in (content.parts or []) if p.text and not p.thought)
        return LLMTurn(text=text.strip(), calls=calls, raw=content)

    def _call(self, contents, system, tools, allow_tools):
        """Try the main model, then each backup at once if it is busy, slow or unavailable."""
        from google.genai import errors

        order = self.models
        if self._backup and time.time() < self._backup_until:     # recently switched: start there
            order = [self._backup] + [m for m in self.models if m != self._backup]
        problem = "no models configured"
        for model in order:
            while True:
                try:
                    config = self._config(model, system, tools, allow_tools)
                    resp = self.client.models.generate_content(model=model, contents=contents,
                                                               config=config)
                except errors.APIError as exc:
                    level = self._thinking.get(model, 0)
                    if exc.code == 400 and level < len(_thinking_options()) - 1:
                        self._thinking[model] = level + 1   # this model refuses that thinking
                        continue                            # setting: try the next one
                    if exc.code not in self.SWITCH | {400}:    # 400 here: this model refuses
                        raise LLMError(f"Gemini error {exc.code}: {exc.message}") from exc
                    problem = f"{exc.code} {exc.message}"
                except httpx.TimeoutException:
                    problem = "timed out"
                except httpx.HTTPError as exc:          # offline, DNS failure, connection reset
                    problem = type(exc).__name__
                else:
                    self.last_model = model
                    if model != self.model:
                        if model != self._backup:
                            log.warning("Using backup model %s", model)
                        self._backup, self._backup_until = model, time.time() + self.STICK
                    return resp
                log.warning("%s unavailable (%s); trying the next model", model, problem)
                break
        raise LLMError(f"All Gemini models failed (last: {problem})")

    def list_models(self) -> list[str]:
        return sorted(m.name.removeprefix("models/") for m in self.client.models.list()
                      if "generateContent" in (m.supported_actions or []))
