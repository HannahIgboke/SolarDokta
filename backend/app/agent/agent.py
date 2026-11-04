"""SolarDokta's chat agent: the loop between the customer, Gemini and the tools.

One reply works like this:
1. Fast path: we guess the tools a question needs from its words ("iron" -> can_i_run,
   "tomorrow" -> tomorrow_plan) and run them straight away, at the same time, BEFORE asking
   Gemini. Their results go along with the question, so most replies need only ONE Gemini call.
2. We send Gemini the instructions (who it is, this customer's system, the rules), the recent
   conversation, the question (+ the data already fetched) and the list of tools.
3. If Gemini still needs something, it asks for more tools; we run them on THIS customer's
   site and send the results back (max 4 rounds).
4. Gemini writes the final reply from the real numbers, in English or Pidgin.
"""

import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from app.agent import offline
from app.agent.appliances import find_appliance
from app.agent.llm import LLMError
from app.agent.tools import TOOL_SPECS, ToolContext, run_tool, site_row

log = logging.getLogger(__name__)

MAX_ROUNDS = 4             # tool rounds per reply (stops runaway loops and saves free quota)
HISTORY_TURNS = 10         # earlier messages sent along for context
MAX_PREFETCH = 3

SYSTEM = """You are SolarDokta, a friendly solar assistant on WhatsApp for homes and small \
businesses in Nigeria. You help with ONE customer's solar system, described below.

THE SYSTEM
{system}
Local time now: {now}.
{role_note}
RULES
- Use the tools for every number (battery %, watts, naira, forecasts, problems). Never guess \
or make up numbers. If a tool returns an error or no data, say so simply.
- A message may end with a LIVE DATA block: tool results we already fetched for that question. \
Use them and don't call those tools again; call other tools only if something is missing.
- Answer ONLY the customer's latest message. Earlier messages are background, never re-answer \
them. Never contradict the data or add claims that are not in it.
- Never guess a cause the data doesn't show. If there is no record of something (e.g. no \
trip in the data), say so plainly and suggest what to check, without inventing reasons.
- If a panel string is producing nothing, say exactly that ("string 2 is not working"), \
never soften it to "a bit weak".
- Language: each message ends with [Reply in English], [Reply in Nigerian Pidgin] or \
[Reply in Igbo]: follow it. Good Pidgin sounds like: "Your battery dey 78%. You fit iron now, \
no wahala." For Igbo use simple everyday Igbo with the tone marks (ọ, ị, ụ, ṅ) and keep numbers \
and words like NEPA, AC, inverter and battery as they are.
- Keep it short for WhatsApp: at most 5 short lines, plain words, no tables or headings. \
Round numbers. Write money like N12,500. Call the grid "NEPA" or "light".
- Lead with the answer (yes / no / yes but...), then the reason, then one practical tip.
- Safety: never tell a customer to open the inverter or battery, or touch wiring or climb \
the roof. For a "critical" problem, tell them to call their installer.
- If a tool says prices are placeholders, mention that the naira figures are estimates.
- Only talk about solar, power and appliances. Politely steer other topics back.
"""

STAFF_NOTE = ("You are talking to a technician or admin of the installer, not a customer: "
              "you may be more technical and include finding kinds and details.\n")

FALLBACK = {
    "en": "Sorry, I can't answer right now. Please try again in a few minutes.",
    "pcm": "Sorry, I no fit answer now. Abeg try again small time.",
    "ig": "Ndo, enweghị m ike ịza ugbu a. Biko nwaa ọzọ n'oge na-adịghị anya.",
}
LANG_NAME = {"en": "English", "pcm": "Nigerian Pidgin", "ig": "Igbo"}

# Words (English and Pidgin) that tell us which tool a question needs.
KEYWORDS = {
    "battery_now": r"batt|charg|percent|%|how long|go last|light|nepa|power now|level",
    "open_problems": r"wrong|problem|issue|fault|wahala|spoil|alert|broke|not work|no dey work|"
                     r"why|went off|go off|trip|recent",
    "light_tracker": r"hours of light|light don|light (this|dey|for)|how (is|e be) light|"
                     r"nepa (this|dey|hours)|blackout|electricity supply|supply (this|don)",
    "heat_outlook": r"heat|hot|temperature|el ?ni[nñ]o|warm|weather (dey|don) hot",
    "tomorrow_plan": r"tomorrow|tmrw|tomoro|tomorow|next day|weather|rain|cloud|sunny|"
                     r"best time|when (should|can|fit|i fit)",
    "money_view": r"sav(e|ed|ing)|money|naira|cost|spend|spent|bill|fuel|diesel|petrol",
    "battery_card": r"health|warranty|resale|sell|condition|replace|weak battery",
}


WHY = re.compile(r"why|went off|go off|recent|last (week|month)|yesterday")

PIDGIN = re.compile(r"\b(dey|wetin|abeg|una|oya|sabi|abi|sef|shey|wahala|comot|wey|wan|"
                    r"fit\s+(use|on|put|run|iron|pump)|e\s+go|no\s+be|how\s+far|make\s+i|"
                    r"na\s+(so|wetin|how))\b", re.IGNORECASE)


IGBO = re.compile(r"[ọịụṅỌỊỤṄ]|\b(kedu|biko|ugbu a|enwere|nwere ike|gịnị|maka|anyanwụ|batrị|ọkụ|"
                  r"abalị|ụtụtụ|echi|ee|mba)\b", re.IGNORECASE)


def reply_language(message: str, preferred: str = "en") -> str:
    """'ig' for Igbo, 'pcm' for Nigerian Pidgin, 'en' for English; the saved preference
    decides very short messages ("battery?") that could be any of them."""
    if IGBO.search(message):
        return "ig"
    if PIDGIN.search(message):
        return "pcm"
    return "en" if len(message.split()) >= 3 else preferred


@dataclass
class Reply:
    text: str
    tool_calls: list[dict] = field(default_factory=list)   # what was run, for the logs
    ok: bool = True
    timings: dict = field(default_factory=dict)


ECHO = re.compile(r"\s*\[(?:Reply in|LIVE DATA|That reply was)[^\]]*\]\s*", re.IGNORECASE)


def clean(text: str) -> str:
    """Remove our own instruction tags if a model repeats them ("... [Reply in English]")."""
    return ECHO.sub(" ", text).strip()


def guess_tools(message: str) -> list[tuple[str, dict]]:
    """Tools this question very likely needs, with their arguments."""
    t = message.lower()
    out = []
    spec = find_appliance(t)
    if spec:
        args = {"appliance": spec.name}
        if m := re.search(r"(\d{2,5})\s*(w\b|watt)", t):
            args["watts"] = float(m.group(1))
        if m := re.search(r"(\d+(?:\.\d+)?)\s*(min|hour|hr)", t):
            args["minutes"] = float(m.group(1)) * (1 if m.group(2) == "min" else 60)
        out.append(("can_i_run", args))
    for name, pattern in KEYWORDS.items():
        if re.search(pattern, t) and not (name == "battery_now" and spec):
            args = {"days": 30} if name == "open_problems" and WHY.search(t) else {}
            out.append((name, args))               # can_i_run already includes the battery
    return out[:MAX_PREFETCH]


def describe_system(ctx: ToolContext) -> str:
    s, row = ctx.site, site_row(ctx)
    strings = ", ".join(f"string {i}: {kwp:g} kWp ({s.panels_in(kwp)} panels)"
                        for i, kwp in ((1, s.pv1_kwp), (2, s.pv2_kwp)) if kwp > 0)
    mode = ("SUB: solar first, then NEPA, battery saved for outages" if s.inverter_mode == "SUB"
            else "SBU: solar first, then battery, then NEPA")
    chem = "lithium (LiFePO4)" if s.battery_chemistry == "lifepo4" else "lead-acid"
    return (f"- {row.get('name', s.code)} in {s.city} ({row.get('load_profile', s.load_profile)})\n"
            f"- Solar panels: {strings}\n"
            f"- Inverter: {s.inverter_kw:g} kW, mode {mode}\n"
            f"- Battery: {s.battery_kwh:g} kWh {chem}\n"
            f"- NEPA tariff band {s.tariff_band}; backup generator: "
            f"{row.get('generator_fuel', 'unknown')}")


class Agent:
    def __init__(self, llm, ctx: ToolContext, language: str = "en"):
        self.llm, self.ctx, self.language = llm, ctx, language

    def system_prompt(self) -> str:
        return SYSTEM.format(
            system=describe_system(self.ctx),
            now=self.ctx.time.strftime("%A %d %B %Y, %I:%M %p"),
            role_note=STAFF_NOTE if self.ctx.role == "staff" else "",
            language=LANG_NAME.get(self.language, "English"),
        )

    def _run_tools(self, calls: list[tuple[str, dict]]) -> list[dict]:
        """Run several tools at the same time (each one waits on the database or internet)."""
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda c: run_tool(self.ctx, c[0], c[1]), calls))
        return [{"name": n, "args": a, "result": r} for (n, a), r in zip(calls, results, strict=True)]

    def reply(self, message: str, history: list[dict] | None = None,
              language: str | None = None) -> Reply:
        """history: earlier turns as [{"role": "user"|"model", "text": ...}], oldest first.
        language: 'en', 'pcm' or 'ig' to force the reply language (the app's language switch);
        otherwise it follows the language of the message."""
        t0 = time.perf_counter()
        system = self.system_prompt()
        prefetched = self._run_tools(guess_tools(message))
        tools_s = time.perf_counter() - t0

        lang = language if language in LANG_NAME else reply_language(message, self.language)
        text = message
        if prefetched:
            data = {p["name"]: p["result"] for p in prefetched}
            text += "\n\n[LIVE DATA, fetched just now]\n" + json.dumps(data, default=str)
        text += f"\n\n[Reply in {LANG_NAME[lang]}]"
        messages = [{"role": m["role"], "text": m["text"]}
                    for m in (history or [])[-HISTORY_TURNS:] if m.get("text")]
        messages.append({"role": "user", "text": text})

        log_calls, calls_made, fixed_language = list(prefetched), 0, False

        def done(answer: str, ok: bool = True) -> Reply:
            timings = {"seconds": round(time.perf_counter() - t0, 1),
                       "prefetch_seconds": round(tools_s, 1), "gemini_calls": calls_made,
                       "model": getattr(self.llm, "last_model", None)}
            return Reply(answer, log_calls, ok, timings)

        try:
            for rnd in range(MAX_ROUNDS + 1):
                last = rnd == MAX_ROUNDS          # final round: answer with what you have
                turn = self.llm.generate(system, messages, TOOL_SPECS, allow_tools=not last)
                calls_made += 1
                if not turn.calls or last:
                    turn.text = clean(turn.text or "")
                    if not turn.text:
                        break
                    if reply_language(turn.text, lang) != lang and not (fixed_language or last):
                        fixed_language = True          # wrong language: ask once more
                        messages.append({"role": "model", "text": turn.text})
                        messages.append({"role": "user", "text": "[That reply was in the wrong "
                                         "language. Say the same thing again in "
                                         f"{LANG_NAME[lang]}.]"})
                        continue
                    return done(turn.text)
                messages.append({"role": "model", "text": turn.text, "calls": turn.calls,
                                 "raw": turn.raw})
                ran = self._run_tools([(c["name"], c.get("args") or {}) for c in turn.calls])
                messages.append({"role": "tool", "results": [
                    {"id": c.get("id"), "name": r["name"], "result": r["result"]}
                    for c, r in zip(turn.calls, ran, strict=True)]})
                log_calls += ran
            log.warning("Agent gave no final answer for %s", self.ctx.site.code)
        except LLMError as exc:
            log.error("LLM failed: %s", exc)
        return done(self._without_ai(prefetched, lang), ok=False)

    def _without_ai(self, prefetched: list[dict], lang: str) -> str:
        """No AI could answer: build a plain answer from the tool results (always works)."""
        try:
            if prefetched:
                return offline.answer(prefetched, lang)
            status = offline.answer(self._run_tools([("battery_now", {})]), lang).split("\n")[0]
            return "\n".join([status, offline.MENU.get(lang, offline.MENU["en"]),   # not recognised:
                               offline.NOTE.get(lang, offline.NOTE["en"])])           # status + what we can do
        except Exception:
            log.exception("Offline answer failed")
            return FALLBACK[lang]
