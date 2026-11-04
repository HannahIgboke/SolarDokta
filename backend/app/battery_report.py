"""The battery health report: everything about the battery from the day it was installed to the
day it will need replacing, for the customer, a warranty claim or a buyer.

    SOH (state of health)  how much the battery can hold now, compared with when it was new
    SOC (state of charge)  how full it is right now (the "battery %")
    cycles                 full charge-and-empty equivalents so far, against what it is rated for

Where it's heading: we project SOH month by month with two speeds of ageing,
    - "as now": the ageing speed the battery is showing (measured, or modelled from its use and
      its temperature), with the hotter El Niño months until the end of February 2027, and
    - "kept cool": the same use, but at 25°C,
so the difference is what the heat is costing.
"""

import numpy as np
import pandas as pd

from app.agent.tools import ToolContext, battery_card, latest_reading, site_row
from app.simulator import store
from app.simulator.battery import CHEMISTRIES
from app.simulator.faults import _iso

EL_NINO_END = pd.Timestamp("2027-02-28")
WARRANTY_LINE = 0.80


def _grade(soh: float) -> tuple[str, str]:
    if soh >= 0.90:
        return "A", "Excellent: like new. Good resale value."
    if soh >= 0.80:
        return "B", "Good: normal wear, still above the usual 80% warranty line."
    if soh >= 0.70:
        return "C", "Fair: noticeably smaller than new. Sell cheaply or plan a replacement."
    return "D", "Worn: time to replace."


def _project(soh: float, start: pd.Timestamp, hot_rate: float, after_rate: float) -> list[dict]:
    """Monthly SOH from now until it reaches 70% (or 15 years)."""
    out, s, t = [], soh, start
    for _ in range(180):
        out.append({"ts": _iso(t), "soh": round(s, 4)})
        if s <= 0.70:
            break
        rate = hot_rate if t.tz_localize(None) < EL_NINO_END else after_rate
        s -= rate / 12
        t += pd.DateOffset(months=1)
    return out


def _when(points: list[dict], line: float) -> str | None:
    for p in points:
        if p["soh"] <= line:
            return p["ts"]
    return None


def report(ctx: ToolContext) -> dict:
    site = ctx.site
    chem = CHEMISTRIES[site.battery_chemistry]
    row = site_row(ctx)
    card = battery_card(ctx)
    now = ctx.time
    est = store.load_battery_estimates(site, now - pd.Timedelta(days=3 * 365), ctx.client)
    daily = (ctx.client.table("telemetry_daily").select("day,batt_discharge_kwh,batt_temp_max,soc_min,soc_max")
             .eq("site_id", site.id).order("day").range(0, 9999).execute().data)
    d = pd.DataFrame(daily) if daily else pd.DataFrame(columns=["day", "batt_discharge_kwh", "batt_temp_max", "soc_min", "soc_max"])
    if len(d):
        d["day"] = pd.to_datetime(d["day"])
        for c in ("batt_discharge_kwh", "batt_temp_max", "soc_min", "soc_max"):
            d[c] = pd.to_numeric(d[c], errors="coerce")

    r = latest_reading(ctx)
    soc_now = round(float(r["batt_soc"]) * 100) if r is not None else None
    soh = (card.get("health_percent") or 100) / 100
    measured = card.get("health_percent") is not None

    last90 = d[d["day"] >= (now - pd.Timedelta(days=90)).tz_localize(None)] if len(d) else d
    days90 = max(1, len(last90))
    cycles_per_year = float(last90["batt_discharge_kwh"].sum()) / site.battery_kwh * 365 / days90 if len(last90) else 0.0
    temps30 = d[d["day"] >= (now - pd.Timedelta(days=30)).tz_localize(None)]["batt_temp_max"].dropna() if len(d) else pd.Series(dtype=float)
    temps365 = d[d["day"] >= (now - pd.Timedelta(days=365)).tz_localize(None)]["batt_temp_max"].dropna() if len(d) else pd.Series(dtype=float)
    factor_now = float(np.mean(2 ** ((temps30 - 25) / 10))) if len(temps30) else 1.0
    factor_year = float(np.mean(2 ** ((temps365 - 25) / 10))) if len(temps365) >= 60 else max(1.0, factor_now * 0.85)

    model_25c = chem.calendar_fade_per_year + cycles_per_year * chem.cycle_fade         # at 25°C
    measured_rate = card.get("health_lost_per_year_percent")
    reliable = (measured_rate is not None and card.get("trend_confidence") == "good" and measured_rate >= 0.5)
    base_rate = measured_rate / 100 if reliable else model_25c * factor_year              # its usual pace
    hot_rate = base_rate * max(factor_now, factor_year) / max(factor_year, 0.5)          # El Niño months
    rate_cool = base_rate / max(1.0, factor_year)                 # same battery and use, kept at 25°C

    as_now = _project(soh, now, hot_rate, base_rate)
    cool = _project(soh, now, rate_cool, rate_cool)
    to80, to80_cool = _when(as_now, WARRANTY_LINE), _when(cool, WARRANTY_LINE)

    def years(ts):
        return round((pd.Timestamp(ts) - now) / pd.Timedelta(days=365), 1) if ts else None

    lost_months = max(0.0, round(12 * (years(to80_cool) - years(to80)), 0)) if to80 and to80_cool else None

    months_left = max(0.0, (EL_NINO_END - now.tz_localize(None)) / pd.Timedelta(days=30.4))
    el_nino_months = round(months_left * max(0.0, hot_rate / max(base_rate, 1e-6) - 1), 1)   # extra this season

    rated = round(0.20 / chem.cycle_fade)
    cycles = card.get("equivalent_full_cycles", 0) or 0
    install = row.get("install_date")
    history = [{"ts": _iso(t), "soh": round(float(v), 4)} for t, v in est.items()]
    if install:
        history.insert(0, {"ts": _iso(pd.Timestamp(install).tz_localize(site.timezone)), "soh": 1.0, "install": True})
    grade, grade_text = _grade(soh)
    dod = (100 - float(d["soc_min"].tail(30).mean()) * 100) if len(d) and d["soc_min"].notna().any() else None

    lines = [f"The battery can hold {round(soh * 100)}% of what it held when new "
             f"({round(soh * site.battery_kwh, 1)} of {site.battery_kwh:g} kWh)." if measured else
             "Health not measured yet: it needs a few nights where the battery drops by 30% or more."]
    if to80:
        lines.append(f"At the current pace it reaches the 80% line around {pd.Timestamp(to80):%B %Y} "
                     f"(in about {years(to80)} years).")
    if lost_months and lost_months >= 1:
        lines.append(f"Heat is costing about {lost_months:.0f} months of battery life overall: in a room kept at "
                     f"25°C it would reach 80% around {pd.Timestamp(to80_cool):%B %Y}.")
    if el_nino_months >= 0.5:
        lines.append(f"This El Niño season alone (to February 2027) adds about {el_nino_months:.1f} months of extra wear.")
    lines.append(f"It has done about {cycles} full cycles of the ~{rated:,} it is rated for "
                 f"({100 * cycles / rated:.1f}% used).")
    if dod is not None:
        lines.append(f"On a typical day it is emptied by about {dod:.0f}% (depth of discharge)."
                     + (" Deep daily discharges age lead-acid batteries quickly." if site.battery_chemistry == "lead_acid" and dod > 50 else ""))

    return {
        "chemistry": card.get("chemistry"), "nameplate_kwh": site.battery_kwh,
        "install_date": install, "age_years": card.get("age_years"),
        "soh_percent": round(soh * 100) if measured else None, "soc_percent": soc_now,
        "usable_kwh": round(soh * site.battery_kwh, 1),
        "cycles": cycles, "rated_cycles": rated, "cycles_per_year": round(cycles_per_year),
        "typical_depth_of_discharge_percent": round(dod) if dod is not None else None,
        "battery_avg_temp_c_30d": round(float(temps30.mean()), 1) if len(temps30) else None,
        "hot_days_percent_30d": round(100 * float((temps30 > 35).mean())) if len(temps30) else None,
        "ageing_speed_now": round(factor_now, 2),
        "fade_per_year_percent": round(base_rate * 100, 1), "fade_measured": reliable,
        "fade_el_nino_percent": round(hot_rate * 100, 1), "fade_cool_percent": round(rate_cool * 100, 1),
        "reaches_80_at": to80, "reaches_80_years": years(to80),
        "reaches_80_if_cool_at": to80_cool, "life_lost_to_heat_months": lost_months,
        "el_nino_extra_months": el_nino_months,
        "replace_around": _when(as_now, 0.70) or to80,
        "grade": grade, "grade_text": grade_text,
        "history": history, "projection": as_now, "projection_cool": cool,
        "measured": measured, "summary": lines,
    }
