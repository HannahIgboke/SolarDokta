"""Check every AI provider that has a key in .env: does it answer, can it use our tools, how fast?

Usage (from backend/):
    python -m scripts.llm_check            # test each provider in LLM_PROVIDERS order
    python -m scripts.llm_check --models   # also list the models each OpenAI-style provider offers
"""

import sys
import time

from app.agent.llm import LLMError
from app.agent.providers import OPENAI_STYLE, make_llm
from app.agent.tools import TOOL_SPECS

SYSTEM = "You are a solar assistant. Use the tools for numbers."


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    chain = make_llm()
    print("Providers with a key, in order:", ", ".join(getattr(p, "name", "gemini") for p in chain.providers))
    for p in chain.providers:
        name = getattr(p, "name", "gemini")
        print(f"\n== {name} ({p.model})")
        for label, msg, allow in (("plain reply", "Say hi in 3 words.", False),
                                  ("uses a tool", "What is my battery percent right now?", True)):
            t0 = time.perf_counter()
            try:
                turn = p.generate(SYSTEM, [{"role": "user", "text": msg}], TOOL_SPECS, allow_tools=allow)
                got = f"called {[c['name'] for c in turn.calls]}" if turn.calls else repr(turn.text[:50])
                print(f"  OK    {label:<12} {time.perf_counter() - t0:4.1f}s  {got}")
            except LLMError as exc:
                print(f"  FAIL  {label:<12} {time.perf_counter() - t0:4.1f}s  {str(exc)[:160]}")
        if "--models" in sys.argv and name in OPENAI_STYLE:
            try:
                ids = sorted(m["id"] for m in p.http.get("/models").json().get("data", []))
                print("  models:", ", ".join(ids))
            except Exception as exc:  # noqa: BLE001
                print("  (couldn't list models:", exc, ")")


if __name__ == "__main__":
    main()
