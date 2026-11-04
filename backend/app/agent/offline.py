"""Answers without any AI: used when every AI service fails (no internet, a network that blocks
AI sites, all quotas used up).

The tools already worked out the facts (battery %, can I run the iron, tomorrow's solar, money
saved, hours of NEPA, heat); here we just put them into short fixed sentences, in English or
Pidgin. Igbo gets the English sentences with a one-line Igbo note, because fixed Igbo sentences
should be written by a fluent speaker. Less natural than the AI, but it always works.
"""

NOTE = {
    "en": "(Quick answer from your system's data: the assistant can't reach its AI right now.)",
    "pcm": "(Quick answer from your system data: the assistant no fit reach the AI now.)",
    "ig": "(Azịza dị mkpirikpi site na data usoro gị: enweghị ike iru AI ugbu a.)",
}


def _kw(w) -> str:
    w = float(w or 0)
    return f"{w / 1000:.1f} kW" if abs(w) >= 1000 else f"{w:.0f} W"


def _naira(n) -> str:
    return f"N{float(n):,.0f}"


def _can_i_run(r: dict, pcm: bool) -> str:
    v, thing = r.get("verdict"), r.get("appliance") or "it"
    if v == "need_watts":
        return (f"How many watts is your {thing}? Check its label, then ask again." if not pcm
                else f"How many watts your {thing} be? Check the label, then ask again.")
    if v == "no_data":
        return r.get("message", "No readings yet.")
    head = {"yes": ("Yes, you can use the {t} now.", "Yes, you fit use the {t} now."),
            "yes_but": ("Yes, but be careful with the {t}.", "Yes, but take am easy with the {t}."),
            "no": ("Better not use the {t} right now.", "No use the {t} now.")}.get(v, ("{t}:", "{t}:"))
    out = [head[1 if pcm else 0].format(t=thing)]
    out += [x[0].upper() + x[1:] + "." for x in (r.get("reasons") or [])[:1] if x]
    if r.get("battery_percent_after") is not None:
        out.append(f"Battery after: about {r['battery_percent_after']}%." if not pcm
                   else f"Battery go remain about {r['battery_percent_after']}%.")
    out += [x[0].upper() + x[1:] + "." for x in (r.get("tips") or [])[:1] if x]
    return " ".join(out)


def _battery_now(r: dict, pcm: bool) -> str:
    if r.get("error"):
        return r["error"]
    p, st = r.get("battery_percent"), r.get("status", "")
    nepa = ("NEPA dey" if r.get("nepa_on") else "NEPA no dey") if pcm else ("NEPA is on" if r.get("nepa_on") else "NEPA is off")
    out = [f"Battery dey {p}% and e dey {st}." if pcm else f"Battery is {p}% and {st}.",
           (f"Solar dey give {_kw(r.get('solar_now_w'))}, house dey use {_kw(r.get('house_using_w'))}, {nepa}." if pcm
            else f"Solar is giving {_kw(r.get('solar_now_w'))}, the house is using {_kw(r.get('house_using_w'))}, {nepa}.")]
    if r.get("lasts_until_morning_sun"):
        out.append("E go reach morning sun." if pcm else "It will last until the morning sun.")
    elif r.get("empty_around"):
        out.append(f"At this rate e fit finish around {r['empty_around']}." if pcm
                   else f"At this rate it could run out around {r['empty_around']}.")
    elif r.get("tonight"):
        out.append(r["tonight"][0].upper() + r["tonight"][1:] + ".")
    if r.get("warning"):
        out.append(r["warning"][0].upper() + r["warning"][1:] + ".")
    return " ".join(out)


def _tomorrow(r: dict, pcm: bool) -> str:
    if r.get("error"):
        return r["error"]
    out = [f"Tomorrow ({r.get('date')}) go be {r.get('sky')}: about {r.get('expected_solar_kwh')} kWh of solar." if pcm
           else f"Tomorrow ({r.get('date')}) looks {r.get('sky')}: about {r.get('expected_solar_kwh')} kWh of solar."]
    if r.get("best_hours_for_heavy_appliances"):
        hours = ", ".join(r["best_hours_for_heavy_appliances"])
        out.append(f"Best time for heavy things: {hours}.")
    if r.get("note"):
        out.append(r["note"][0].upper() + r["note"][1:] + ".")
    return " ".join(out)


def _money(r: dict, pcm: bool) -> str:
    if r.get("error"):
        return r["error"]
    out = (f"For the last {r['period_days']} days, solar don save you about {_naira(r['saved_by_solar_ngn'])}, "
           f"and you spend about {_naira(r['nepa_cost_ngn'])} on NEPA." if pcm else
           f"In the last {r['period_days']} days solar saved you about {_naira(r['saved_by_solar_ngn'])}, "
           f"and you spent about {_naira(r['nepa_cost_ngn'])} on NEPA.")
    if r.get("warning"):
        out += " (Prices are estimates.)"
    return out


def _light(r: dict, pcm: bool) -> str:
    if r.get("error"):
        return r["error"]
    w = r.get("worst_day") or {}
    out = (f"NEPA give about {r['average_hours_per_day']} hours a day for the last {len(r['days'])} days "
           f"(normal na about {r.get('normal_hours_for_band')}). Worst day: {w.get('day')}, {w.get('hours')} h." if pcm else
           f"NEPA gave about {r['average_hours_per_day']} hours a day over the last {len(r['days'])} days "
           f"(normally about {r.get('normal_hours_for_band')}). Worst day: {w.get('day')}, {w.get('hours')} h.")
    if r.get("home_blackouts"):
        out += (f" Your house no get light at all for {r['home_blackout_hours']} h." if pcm
                else f" Your home was completely without power for {r['home_blackout_hours']} h.")
    return out


def _heat(r: dict, pcm: bool) -> str:
    out = []
    if r.get("battery_average_c") is not None:
        out.append(f"Your battery dey average {r['battery_average_c']}°C, so e dey age {r['ageing_speed_vs_25c']}× faster pass for cool room." if pcm
                   else f"Your battery has averaged {r['battery_average_c']}°C, so it is ageing {r['ageing_speed_vs_25c']}× as fast as in a cool room.")
    if r.get("tomorrow_high_c") is not None:
        out.append(f"Tomorrow go reach about {r['tomorrow_high_c']}°C." if pcm else f"Tomorrow will reach about {r['tomorrow_high_c']}°C.")
    if r.get("tips"):
        out.append(r["tips"][0][0].upper() + r["tips"][0][1:] + ".")
    return " ".join(out) or "No heat data yet."


def _problems(r: dict, pcm: bool) -> str:
    items = r.get("open_problems") or []
    if not items:
        return "No problem dey your system now." if pcm else "No problems with your system right now."
    return " ".join(f"{p['problem'][0].upper() + p['problem'][1:]}: {p['what_to_do']}." for p in items[:3])


def _battery_card(r: dict, pcm: bool) -> str:
    if r.get("health_percent") is None:
        return (r.get("health") or "Battery health not measured yet.")
    return (f"Battery health na {r['health_percent']}% ({r.get('status')}), about {r.get('usable_kwh_now')} kWh usable." if pcm
            else f"Battery health is {r['health_percent']}% ({r.get('status')}), about {r.get('usable_kwh_now')} kWh usable.")


WRITERS = {"can_i_run": _can_i_run, "battery_now": _battery_now, "tomorrow_plan": _tomorrow,
           "money_view": _money, "light_tracker": _light, "heat_outlook": _heat,
           "open_problems": _problems, "battery_card": _battery_card}

MENU = {
    "en": "I can still answer about your battery, an appliance (e.g. 'can I use the iron?'), tomorrow, money saved, NEPA hours, heat and problems.",
    "pcm": "I fit still answer about your battery, appliance (like 'I fit use iron?'), tomorrow, money wey you save, NEPA hours, heat and wahala.",
    "ig": "I can still answer about your battery, an appliance (e.g. 'can I use the iron?'), tomorrow, money saved, NEPA hours, heat and problems.",
}


def answer(results: list[dict], lang: str = "en") -> str:
    """results: [{"name", "result"}] from the tools already run for this question."""
    pcm = lang == "pcm"
    parts = []
    for r in results:
        write = WRITERS.get(r["name"])
        if write and isinstance(r.get("result"), dict):
            try:
                parts.append(write(r["result"], pcm))
            except (KeyError, TypeError, ValueError, IndexError):
                continue
    if not parts:
        return f"{NOTE.get(lang, NOTE['en'])}\n{MENU.get(lang, MENU['en'])}"
    return f"{' '.join(parts[:2])}\n{NOTE.get(lang, NOTE['en'])}"
