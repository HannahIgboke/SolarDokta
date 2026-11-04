"""Find out which part of a Gemini request a model accepts (for "400 invalid argument" errors).

Usage (from backend/):
    python -m scripts.gemini_check                      # checks the main and backup models
    python -m scripts.gemini_check gemini-2.5-flash     # checks one model
"""

import sys

from google import genai
from google.genai import errors, types

from app.agent.tools import TOOL_SPECS
from app.config import get_settings


def declarations(with_schema_for_empty: bool):
    return [types.FunctionDeclaration(
        name=t["name"], description=t["description"],
        parameters_json_schema=t["parameters"]
        if (t["parameters"].get("properties") or with_schema_for_empty) else None)
        for t in TOOL_SPECS]


CHECKS = {
    "plain text": {},
    "system instruction": {"system_instruction": "You are a helpful assistant."},
    "thinking off": {"thinking_config": types.ThinkingConfig(thinking_budget=0)},
    "thinking level minimal": {"thinking_config": types.ThinkingConfig(thinking_level="minimal")},
    "thinking level low": {"thinking_config": types.ThinkingConfig(thinking_level="low")},
    "max output tokens": {"max_output_tokens": 400},
    "tools": {"tools": [types.Tool(function_declarations=declarations(False))]},
    "tools (empty schemas)": {"tools": [types.Tool(function_declarations=declarations(True))]},
    "tool config AUTO": {"tools": [types.Tool(function_declarations=declarations(False))],
                         "tool_config": types.ToolConfig(function_calling_config=
                                                         types.FunctionCallingConfig(mode="AUTO"))},
}


def main() -> None:
    s = get_settings()
    client = genai.Client(api_key=s.gemini_api_key,
                          http_options=types.HttpOptions(timeout=20_000))   # 20 s per check
    models = sys.argv[1:] or [s.gemini_model] + [m.strip() for m in s.gemini_backup_models.split(",")]
    for model in models:
        print(f"\n== {model}")
        for name, cfg in CHECKS.items():
            try:
                r = client.models.generate_content(model=model, contents="Say hi in 3 words.",
                                                   config=types.GenerateContentConfig(**cfg))
                print(f"  OK    {name:<22} {(r.text or '').strip()[:40]!r}")
            except errors.APIError as exc:
                print(f"  FAIL  {name:<22} {exc.code}: {exc.message}")
            except Exception as exc:  # noqa: BLE001 - show every kind of failure
                print(f"  FAIL  {name:<22} {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
