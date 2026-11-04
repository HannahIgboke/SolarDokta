"""Chat with SolarDokta in the terminal, as if you were a customer on WhatsApp.

Usage (from backend/):
    python -m scripts.chat --site lagos-001                  # chat (type /quit to stop)
    python -m scripts.chat --site lagos-001 --lang pcm       # customer prefers Pidgin
    python -m scripts.chat --site lagos-001 --staff          # technician view
    python -m scripts.chat --site lagos-001 --ask "Can I use my pressing iron now?"
    python -m scripts.chat --site lagos-001 --tool can_i_run --args '{"appliance": "iron"}'
    python -m scripts.chat --models                          # Gemini models your key can use

--tool runs one tool directly, without Gemini (no quota used): good for checking the numbers.
In chat: /tools shows or hides the tool calls, /reset forgets the conversation, /quit stops.
"""

import argparse
import json
import sys

from app.agent.agent import Agent
from app.agent.llm import GeminiLLM
from app.agent.providers import make_llm
from app.agent.tools import TOOLS, ToolContext, run_tool
from app.simulator.site import load_site


def show_calls(calls: list[dict]) -> None:
    for c in calls:
        print(f"  [tool] {c['name']}({json.dumps(c['args'])})")
        print("         " + json.dumps(c["result"], default=str)[:600])


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # Windows terminals + Pidgin/N
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", default="lagos-001")
    parser.add_argument("--lang", choices=["en", "pcm"], default="en")
    parser.add_argument("--staff", action="store_true", help="talk as a technician/admin")
    parser.add_argument("--ask", help="ask one question and exit")
    parser.add_argument("--tool", choices=sorted(TOOLS), help="run one tool without Gemini")
    parser.add_argument("--args", default="{}", help="JSON arguments for --tool")
    parser.add_argument("--show-tools", action="store_true")
    parser.add_argument("--models", action="store_true", help="list Gemini models and exit")
    args = parser.parse_args()

    if args.models:
        llm = GeminiLLM()
        print(f"Configured model: {llm.model}\nAvailable:")
        print("\n".join("  " + m for m in llm.list_models()))
        return

    ctx = ToolContext(load_site(args.site), role="staff" if args.staff else "customer")
    if args.tool:
        print(json.dumps(run_tool(ctx, args.tool, json.loads(args.args)), indent=2, default=str))
        return

    llm = make_llm()
    agent = Agent(llm, ctx, language=args.lang)
    if args.ask:
        r = agent.reply(args.ask)
        if args.show_tools:
            show_calls(r.tool_calls)
        print(r.text)
        print(f"  ({r.timings})")
        return

    print(f"SolarDokta chat for {args.site} (model {llm.model}). /quit to stop, /tools to "
          f"show tool calls, /reset to start over.\n")
    history, show = [], args.show_tools
    while True:
        try:
            msg = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not msg:
            continue
        if msg == "/quit":
            break
        if msg == "/tools":
            show = not show
            print(f"(tool calls {'shown' if show else 'hidden'})")
            continue
        if msg == "/reset":
            history = []
            print("(conversation forgotten)")
            continue
        r = agent.reply(msg, history)
        if show:
            show_calls(r.tool_calls)
        print(f"SolarDokta> {r.text}")
        t = r.timings
        print(f"  ({t['seconds']} s: data {t['prefetch_seconds']} s, {t['gemini_calls']} Gemini "
              f"call(s), model {t['model']})\n")
        if r.ok:
            history += [{"role": "user", "text": msg}, {"role": "model", "text": r.text}]


if __name__ == "__main__":
    main()
