"""Gemini reads what customers upload: token receipts, fuel receipts, voice notes, photos.

Each kind has a short instruction and a list of JSON keys for the answer (Gemini's JSON mode),
so we always get structured fields back (amount, units, transcript...), never free text to parse.
Tests swap `read_file` for a fake.
"""

import json
import logging

import httpx

from app.agent.llm import GeminiLLM, LLMError

log = logging.getLogger(__name__)

PROMPTS = {
    "token_receipt": (
        "This is a Nigerian prepaid electricity token receipt, SMS or screenshot. Read the amount "
        "paid in naira, the units (kWh) bought, the date, the tariff band (A to E) and the "
        "distribution company if shown. Use null for anything you can't read. Never guess."),
    "fuel_receipt": (
        "This is a receipt or photo for petrol or diesel bought in Nigeria. Read the fuel type, "
        "litres, total amount in naira, price per litre and the date. Use null for anything "
        "you can't read. Never guess."),
    "voice_note": (
        "This is a short voice note from a Nigerian solar customer, in English or Nigerian Pidgin, "
        "about their solar system. Transcribe it exactly, then summarise it in one plain English "
        "sentence. Say whether it reports a problem (beeping, power going off, smell, heat, "
        "damage...) and whether it mentions a new appliance."),
    "question": (
        "This is a short voice message from a Nigerian solar customer or technician asking "
        "SolarDokta a question, in English, Nigerian Pidgin or Igbo. Transcribe exactly what they "
        "said, in the language they spoke. Don't answer it. Words they often use: battery, "
        "inverter, solar, panel, NEPA, light, AC, fan, fridge, freezer, pressing iron, pumping "
        "machine, washing machine, generator, fuel, token, units, charge, percent, tonight, "
        "tomorrow, heat. Nigerian accents may make 'battery' sound like 'batching' or 'battry'."),
    "photo": (
        "This is a photo from a Nigerian solar installation. Say what it shows (inverter, battery, "
        "solar panel, charge controller, distribution board, appliance or other). If a nameplate "
        "or label is readable, read the brand, model and ratings exactly as printed. Note any "
        "visible problem (burn marks, swelling, loose wires, heavy dust). Use null when unsure."),
}

FIELDS = {   # the JSON keys we want back for each kind
    "token_receipt": "readable (true/false), amount_ngn, units_kwh, date (YYYY-MM-DD), tariff_band, disco",
    "fuel_receipt": "readable (true/false), fuel (petrol or diesel), litres, amount_ngn, "
                    "price_per_litre, date (YYYY-MM-DD)",
    "voice_note": "language (en or pcm), transcript, summary, reports_problem (true/false), "
                  "problem, new_appliance",
    "question": "language (en, pcm or ig), transcript",
    "photo": "readable (true/false), shows, brand, model, rating_text, power_kw, capacity_kwh, "
             "voltage_v, panel_watts, problems_seen",
}


def read_file(kind: str, data: bytes, mime_type: str) -> dict:
    """Ask Gemini to read one uploaded file. Raises LLMError if no model can."""
    from google.genai import errors, types

    llm = GeminiLLM()
    config = types.GenerateContentConfig(
        response_mime_type="application/json", temperature=0,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True))
    ask = f"{PROMPTS[kind]}\nAnswer only with a JSON object with these keys: {FIELDS[kind]}."
    contents = [types.Content(role="user", parts=[types.Part.from_bytes(data=data, mime_type=mime_type),
                                                  types.Part.from_text(text=ask)])]
    problem = "no model"
    for model in llm.models:
        try:
            resp = llm.client.models.generate_content(model=model, contents=contents, config=config)
            return json.loads(resp.text or "{}")
        except errors.APIError as exc:
            problem = f"{exc.code} {exc.message}"
            if exc.code not in GeminiLLM.SWITCH | {400}:
                break
        except (httpx.TimeoutException, json.JSONDecodeError) as exc:
            problem = type(exc).__name__
        log.warning("%s couldn't read the %s (%s)", model, kind, problem)
    raise LLMError(f"Couldn't read the file: {problem}")
