"""Data for the dashboard's pictures and charts (the chat agent doesn't need these).

    live_view       everything the live "digital twin" of the system shows: each panel string
                    (making / could make / problem), battery, inverter, NEPA, the appliances that
                    are probably on, and one plain sentence about right now
    today_view      today's curves for the chart: solar used, solar the panels could have made,
                    house use, battery %, NEPA on/off (15-minute points)
    money_history   naira saved by solar and spent on NEPA, month by month
    usage_view      any day or range of days the customer picks: hour by hour for one day,
                    day by day for several, with totals and a few plain sentences about them
"""

import re
from itertools import combinations

import numpy as np
import pandas as pd

from app.agent.tools import (
    STALE_MIN,
    ToolContext,
    battery_health_now,
    forecast_weather,
    latest_reading,
    next_morning,
    pricing,
    site_row,
    solar_value,
    tonight_outlook,
)
from app.detect.expected import expected_power
from app.simulator import store
from app.simulator.appliances import PROFILES
from app.simulator.battery import CHEMISTRIES
from app.simulator.faults import _iso

HOT_BATTERY_C = 35.0
HELD_BACK_MIN_W = 400          # below this, "holding back" is just noise


def _on_at(windows, hour: float) -> bool:
    for h0, h1 in windows:
        if (h0 <= hour < h1) if h0 < h1 else (hour >= h0 or hour < h1):
            return True
    return False


def likely_appliances(profile_name: str, hour: float, load_w: float) -> list[dict]:
    """Which appliances are probably on, explaining the measured house power.

    Real inverters only measure the total. Always-on things inside their hours count first;
    then we pick the combination of appliances usually used at this hour (and fridge
    compressors) whose watts add up closest to the rest. It's an estimate, shown as such.
    """
    apps = PROFILES[profile_name].appliances
    base, candidates = [], []
    for a in apps:
        w = a.watts * a.qty
        if a.kind == "always" and _on_at(a.windows, hour):
            base.append(a)
        elif a.kind == "cycle" or _on_at(a.windows, hour):
            candidates.append((a, w))
    rest = load_w - sum(a.watts * a.qty for a in base)
    best, best_err = (), abs(rest)
    for k in range(1, min(len(candidates), 6) + 1):
        for combo in combinations(candidates, k):
            err = abs(rest - sum(w for _, w in combo))
            if err < best_err - 1:
                best, best_err = combo, err
    on = {a.name for a in base} | {a.name for a, _ in best}
    return [{"name": a.name.replace("_", " "), "watts": round(a.watts * a.qty), "on": a.name in on}
            for a in apps]


ALWAYS_ON = re.compile(r"router|cctv|camera|wifi|decoder")


def site_appliances(site, client) -> list[dict]:
    """The appliances the customer listed (empty if they haven't, or before migration 009)."""
    try:
        rows = (client.table("site_appliances").select("name,watts,qty").eq("site_id", site.id)
                .order("name").execute().data)
    except Exception:  # noqa: BLE001 - table not created yet
        return []
    return [{"name": r["name"], "watts": float(r["watts"]), "qty": int(r["qty"])} for r in rows]


def likely_from_list(items: list[dict], load_w: float) -> list[dict]:
    """Same idea as likely_appliances, for the customer's own list (no usual hours known):
    always-on things first, then the combination closest to the measured power."""
    base = [i for i in items if ALWAYS_ON.search(i["name"].lower())]
    rest = load_w - sum(i["watts"] * i["qty"] for i in base)
    candidates = [i for i in items if i not in base][:14]
    best, best_err = (), abs(rest)
    for k in range(1, min(len(candidates), 5) + 1):
        for combo in combinations(candidates, k):
            err = abs(rest - sum(i["watts"] * i["qty"] for i in combo))
            if err < best_err - 1:
                best, best_err = combo, err
    on = {i["name"] for i in base} | {i["name"] for i in best}
    return [{"name": i["name"], "watts": round(i["watts"] * i["qty"]), "on": i["name"] in on}
            for i in items]


def _expected_today(ctx: ToolContext) -> pd.DataFrame | None:
    """What each string could make today (5-minute steps), from the weather forecast."""
    try:
        hourly, label = forecast_weather(ctx)
    except Exception:  # noqa: BLE001 - no weather: the twin still works, just without "could make"
        return None
    day = ctx.time.normalize()
    idx = pd.date_range(day, day + pd.Timedelta(days=1), freq="5min", inclusive="left")
    return expected_power(ctx.site, hourly[["ghi_wm2", "temp_c"]], label, idx)


def _open_kinds(ctx: ToolContext) -> dict[str, set]:
    rows = (ctx.client.table("findings").select("kind,details").eq("site_id", ctx.site.id)
            .eq("status", "open").execute().data)
    out: dict[str, set] = {}
    for r in rows:
        out.setdefault(r["kind"], set()).add((r.get("details") or {}).get("target"))
    return out


HEADLINES = {   # one plain sentence about right now, in English, Pidgin and Igbo
    "stale": ("We haven't heard from your inverter since {t}.",
              "We never hear from your inverter since {t}.",
              "Anyị anụbeghị ihe site n'inverter gị kemgbe {t}."),
    "fault": ("Your inverter is reporting a fault right now. Switch off big appliances.",
              "Your inverter dey show fault now. Off the big appliances.",
              "Inverter gị na-egosi nsogbu ugbu a. Gbanyụọ ngwa ndị buru ibu."),
    "dead": ("Panel group {n} has stopped producing. Call your installer.",
             "Panel group {n} don stop to produce. Call your installer.",
             "Otu panel {n} akwụsịla ịrụ ọrụ. Kpọọ onye rụnyere ya."),
    "full": ("Battery full. Your panels are holding back about {kw} kW: a good time to iron, pump water or wash.",
             "Battery don full. Your panels still get about {kw} kW extra: na good time to iron, pump water or wash.",
             "Batrị ejupụtala. Panel gị nwere ihe dị ka {kw} kW fọdụrụ: oge dị mma ịgba ígwè, ịkpọ mmiri ma ọ bụ ịsa ákwà."),
    "nepa": ("NEPA is on and helping power the house. Battery at {p}%.",
             "NEPA dey and e dey help power the house. Battery dey {p}%.",
             "NEPA nọ ma na-enyere ụlọ aka. Batrị dị na {p}%."),
    "night_low": ("Battery at {p}%. It may not last until morning: go easy on big appliances.",
                  "Battery dey {p}%. E fit no reach morning: take am easy with big appliances.",
                  "Batrị dị na {p}%. O nwere ike ọ gaghị eru ụtụtụ: jiri nwayọọ were ngwa ndị buru ibu."),
    "night_ok": ("Running on battery ({p}%). Enough to last until the morning sun.",
                 "Na battery we dey use now ({p}%). E go reach morning sun.",
                 "Ọ na-eji batrị arụ ọrụ ({p}%). Ọ ga-eru ruo mgbe anyanwụ ụtụtụ."),
    "charging": ("Solar is powering the house and charging your battery ({p}%).",
                 "Solar dey power the house and dey charge your battery ({p}%).",
                 "Anyanwụ na-enye ụlọ ọkụ ma na-achaji batrị gị ({p}%)."),
    "partial": ("Battery at {p}%. Solar is covering part of what you use.",
                "Battery dey {p}%. Solar dey carry part of wetin you dey use.",
                "Batrị dị na {p}%. Anyanwụ na-ebu akụkụ nke ihe ị na-eji."),
}
LANG_INDEX = {"en": 0, "pcm": 1, "ig": 2}


def headline(live: dict, lang: str = "en") -> str:
    """One plain sentence about the system right now."""
    i = LANG_INDEX.get(lang, 0)
    b = live["battery"]
    p = b["percent"]
    if live.get("stale"):
        return HEADLINES["stale"][i].format(t=live["reading_time"])
    if live["inverter"].get("fault"):
        return HEADLINES["fault"][i]
    dead = [s for s in live["strings"] if s["status"] == "dead"]
    if dead:
        return HEADLINES["dead"][i].format(n=dead[0]["number"])
    held = live.get("held_back_w", 0)
    if p >= 97 and held >= HELD_BACK_MIN_W:
        return HEADLINES["full"][i].format(kw=f"{held / 1000:.1f}")
    if live["nepa_on"] and live["house_w"] > live["solar_w"]:
        return HEADLINES["nepa"][i].format(p=p)
    if not live["is_day"]:
        if b.get("tonight") == "may run out before morning at normal use":
            return HEADLINES["night_low"][i].format(p=p)
        return HEADLINES["night_ok"][i].format(p=p)
    if b["power_w"] > 50:
        return HEADLINES["charging"][i].format(p=p)
    return HEADLINES["partial"][i].format(p=p)


def live_view(ctx: ToolContext, lang: str = "en") -> dict:
    site, r = ctx.site, latest_reading(ctx)
    if r is None:
        return {"error": "no readings from this system yet"}
    chem = CHEMISTRIES[site.battery_chemistry]
    soh, _ = battery_health_now(ctx)
    usable = site.battery_kwh * soh
    soc, batt_w = float(r["batt_soc"]), float(r["batt_v"]) * float(r["batt_a"])
    left = max(0.0, soc - chem.min_soc) * usable * chem.eff_discharge
    full = (1 - chem.min_soc) * usable * chem.eff_discharge
    temp = float(r["batt_temp_c"]) if r.get("batt_temp_c") is not None else None
    problems = _open_kinds(ctx)
    exp = _expected_today(ctx)
    ts = r["ts"].floor("5min")
    now_exp = exp.loc[ts] if exp is not None and ts in exp.index else None

    strings, could_make = [], 0.0
    for i, (s, kwp) in enumerate(site.strings.items(), start=1):
        now_w = float(r[f"{s}_w"])
        exp_w = float(now_exp[f"{s}_exp_w"]) if now_exp is not None else None
        could_make += exp_w or 0.0
        status = ("dead" if s in problems.get("string_failure", set()) else
                  "weak" if s in problems.get("underrated_panel", set()) else
                  "shaded" if s in problems.get("shading", set()) else
                  "dusty" if problems.get("soiling") else "ok")
        strings.append({"id": s, "number": i, "kwp": kwp, "panels": site.panels_in(kwp),
                        "now_w": round(now_w), "could_make_w": None if exp_w is None else round(exp_w),
                        "status": status})
    solar_w = sum(s["now_w"] for s in strings)
    peak = max(1.0, sum(site.strings.values()) * 1000 * 0.86)          # clear-noon output
    age = (ctx.time - r["ts"]) / pd.Timedelta(minutes=1)
    load = float(r["load_w"])

    battery = {"percent": round(soc * 100), "power_w": round(batt_w), "energy_left_kwh": round(left, 1),
               "full_kwh": round(full, 1), "size_kwh": site.battery_kwh, "temp_c": temp,
               "hot": bool(temp is not None and temp > HOT_BATTERY_C) or "hot_battery_room" in problems,
               "fading": "battery_fade" in problems,
               "status": "charging" if batt_w > 20 else "discharging" if batt_w < -20 else "resting"}
    battery.update({k: v for k, v in tonight_outlook(ctx, left, full).items() if k == "tonight"})
    out = {
        "reading_time": r["ts"].strftime("%I:%M %p").lstrip("0"),
        "stale": age > STALE_MIN,
        "is_day": next_morning(ctx.time) is None and (now_exp is None or could_make > 20 or solar_w > 20),
        "sun": round(min(1.0, (could_make if now_exp is not None else solar_w) / peak), 2),
        "solar_w": round(solar_w),
        "held_back_w": round(max(0.0, could_make - solar_w)) if now_exp is not None else 0,
        "house_w": round(load),
        "nepa_on": float(r["grid_v"]) > 100,
        "nepa_w": round(max(0.0, float(r["grid_w"]))),
        "strings": strings,
        "battery": battery,
        "inverter": {"kw": site.inverter_kw, "mode": site.inverter_mode,
                     "load_percent": round(100 * load / (site.inverter_kw * 1000)),
                     "fault": r.get("fault_code")},
        "appliances": (likely_from_list(own, load) if (own := site_appliances(site, ctx.client))
                       else likely_appliances(site.load_profile, ctx.time.hour + ctx.time.minute / 60, load)),
        "appliances_source": "yours" if own else "usual",
        "problems": sorted(problems),
    }
    out["device"] = device_status(ctx, age)
    out["headline"] = headline(out, lang)
    return out


def device_status(ctx: ToolContext, age_min: float) -> dict:
    """The SolarDokta Link box on the inverter: is it sending readings?"""
    today = ctx.time.normalize()
    try:
        rows = (ctx.client.table("telemetry_hourly").select("samples").eq("site_id", ctx.site.id)
                .gte("hour_ts", _iso(today)).range(0, 99).execute().data)
        readings = int(sum(int(r.get("samples") or 0) for r in rows))
    except Exception:  # noqa: BLE001 - only a nice-to-have number
        readings = None
    expected = int((ctx.time - today) / pd.Timedelta(minutes=5))
    simulated = bool(site_row(ctx).get("is_simulated", True))
    return {"name": "SolarDokta Link", "connected": age_min <= STALE_MIN,
            "last_seen_minutes": max(0, round(age_min)), "connection": "Wi-Fi",
            "readings_today": readings, "readings_expected_today": expected,
            "simulated": simulated}


def usage_view(ctx: ToolContext, start: str | None = None, end: str | None = None) -> dict:
    """Energy for the days the customer picked. One day: by hour. Several days: by day."""
    tz = ctx.site.timezone
    try:
        d0 = pd.Timestamp(start or ctx.time.strftime("%Y-%m-%d")).tz_localize(tz)
        d1 = pd.Timestamp(end or start or ctx.time.strftime("%Y-%m-%d")).tz_localize(tz)
    except (ValueError, TypeError):
        return {"error": "dates must look like 2026-11-03"}
    if d1 < d0:
        d0, d1 = d1, d0
    d1 = min(d1, ctx.time.normalize())
    d0 = max(d0, d1 - pd.Timedelta(days=91))                      # at most about 3 months
    one_day = d0 == d1
    pr = pricing(ctx)
    if one_day:
        rows = (ctx.client.table("telemetry_hourly")
                .select("hour_ts,pv_kwh,load_kwh,grid_import_kwh,soc_min,soc_max,batt_temp_max,grid_on_minutes")
                .eq("site_id", ctx.site.id).gte("hour_ts", _iso(d0))
                .lt("hour_ts", _iso(d0 + pd.Timedelta(days=1))).order("hour_ts").range(0, 99).execute().data)

        def label(r):
            h = pd.Timestamp(r["hour_ts"]).tz_convert(tz).hour
            return f"{(h + 11) % 12 + 1} {'am' if h < 12 else 'pm'}"
    else:
        rows = (ctx.client.table("telemetry_daily")
                .select("day,pv_kwh,load_kwh,grid_import_kwh,soc_min,soc_max,batt_temp_max,grid_on_minutes")
                .eq("site_id", ctx.site.id).gte("day", d0.strftime("%Y-%m-%d"))
                .lte("day", d1.strftime("%Y-%m-%d")).order("day").range(0, 199).execute().data)

        def label(r):
            d = pd.Timestamp(r["day"])
            return f"{d:%a} {d.day} {d:%b}"

    def num(v, nd=2):
        return None if v is None else round(float(v), nd)

    points = [{"label": label(r), "solar_kwh": num(r["pv_kwh"]), "use_kwh": num(r["load_kwh"]),
               "nepa_kwh": num(r["grid_import_kwh"]),
               "battery_low": num(float(r["soc_min"]) * 100, 0) if r.get("soc_min") is not None else None,
               "battery_high": num(float(r["soc_max"]) * 100, 0) if r.get("soc_max") is not None else None,
               "battery_temp": num(r.get("batt_temp_max"), 1),
               "light_hours": num(float(r["grid_on_minutes"]) / 60, 1)} for r in rows]
    span = (f"{d0:%A} {d0.day} {d0:%B}" if one_day else f"{d0.day} {d0:%b} to {d1.day} {d1:%b %Y}")
    if not points:
        return {"mode": "hours" if one_day else "days", "span": span, "points": [],
                "message": "No readings for these dates."}
    solar = sum(p["solar_kwh"] or 0 for p in points)
    use = sum(p["use_kwh"] or 0 for p in points)
    nepa = sum(p["nepa_kwh"] or 0 for p in points)
    light = sum(p["light_hours"] or 0 for p in points)
    lows = [p for p in points if p["battery_low"] is not None]
    lowest = min(lows, key=lambda p: p["battery_low"]) if lows else None
    hottest = max((p for p in points if p["battery_temp"] is not None), key=lambda p: p["battery_temp"], default=None)
    days = 1 if one_day else len(points)
    share = light / (24 * days)
    saved = solar_value(solar, share, pr)
    from_solar = round(100 * min(1.0, max(0.0, (use - nepa) / use))) if use > 0 else None
    story = [f"Your panels made {solar:.1f} kWh and your home used {use:.1f} kWh."]
    if from_solar is not None:
        story.append(f"About {from_solar}% of what you used came from your solar and battery; "
                     f"the rest ({nepa:.1f} kWh) came from NEPA.")
    story.append(f"NEPA was on for {light:.1f} hours" + ("." if one_day else f", about {light / days:.1f} hours a day."))
    if lowest:
        story.append(f"The battery got as low as {lowest['battery_low']:.0f}% ({lowest['label']}).")
    if hottest and hottest["battery_temp"] >= 35:
        story.append(f"The battery reached {hottest['battery_temp']:.0f}°C ({hottest['label']}): hot enough to wear it faster.")
    return {"mode": "hours" if one_day else "days", "span": span, "points": points,
            "totals": {"solar_kwh": round(solar, 1), "use_kwh": round(use, 1), "nepa_kwh": round(nepa, 1),
                       "light_hours": round(light, 1), "from_solar_percent": from_solar,
                       "saved_ngn": round(saved, -2), "days": days},
            "story": story, "estimate": pr["placeholder"]}


def today_view(ctx: ToolContext) -> dict:
    day = ctx.time.normalize()
    tel = store.load_telemetry(ctx.site, day, ctx.time + pd.Timedelta(minutes=5), ctx.client)
    if tel.empty:
        return {"points": []}
    exp = _expected_today(ctx)
    df = pd.DataFrame({"solar_w": tel["pv1_w"] + tel["pv2_w"], "house_w": tel["load_w"],
                       "battery_percent": tel["batt_soc"] * 100,
                       "nepa_on": (tel["grid_v"] > 100).astype(float)})
    q = df.resample("15min").mean()
    if exp is not None:
        could = (exp["pv1_exp_w"] + exp["pv2_exp_w"]).resample("15min").mean()
        q["could_make_w"] = could.reindex(q.index)
    points = []
    for t, row in q.iterrows():
        p = {"time": t.strftime("%H:%M")}
        for k, v in row.items():
            if pd.notna(v):
                p[k] = round(float(v), 1) if k == "battery_percent" else (
                    round(float(v)) if k != "nepa_on" else bool(v >= 0.5))
        points.append(p)
    return {"date": day.strftime("%A %d %B"), "points": points,
            "solar_kwh": round(float(df["solar_w"].sum()) * 5 / 60 / 1000, 1),
            "house_kwh": round(float(df["house_w"].sum()) * 5 / 60 / 1000, 1)}


def money_history(ctx: ToolContext, months: int = 6) -> dict:
    months = int(np.clip(months or 6, 1, 24))
    start = (ctx.time.normalize().replace(day=1) - pd.DateOffset(months=months - 1))
    rows = (ctx.client.table("telemetry_daily")
            .select("day,pv_kwh,grid_import_kwh,grid_on_minutes").eq("site_id", ctx.site.id)
            .gte("day", start.strftime("%Y-%m-%d")).order("day").range(0, 999).execute().data)
    if not rows:
        return {"months": []}
    pr = pricing(ctx)
    d = pd.DataFrame(rows)
    d["month"] = d["day"].str[:7]
    out = []
    for month, g in d.groupby("month"):
        solar = float(g["pv_kwh"].astype(float).sum())
        share = float(g["grid_on_minutes"].astype(float).sum()) / (len(g) * 1440)
        out.append({"month": pd.Timestamp(month + "-01").strftime("%b"), "days": len(g),
                    "saved_ngn": round(solar_value(solar, share, pr), -2),
                    "nepa_spend_ngn": round(float(g["grid_import_kwh"].astype(float).sum()) * pr["tariff"], -2),
                    "solar_kwh": round(solar)})
    return {"months": out, "estimate": pr["placeholder"], "since": _iso(start)}


def battery_report_view(ctx: ToolContext) -> dict:
    from app.battery_report import report
    return report(ctx)


VIEWS = {"live": live_view, "today": today_view, "money_history": money_history, "usage": usage_view,
         "battery_report": battery_report_view}
