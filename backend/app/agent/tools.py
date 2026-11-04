"""The agent's tools: small functions that look up real numbers for ONE site.

Gemini never sees the database. It asks for a tool by name ("can_i_run" with
{"appliance": "pressing iron"}), we run the function here and hand back a small dict of facts,
and Gemini turns those facts into a friendly WhatsApp reply in English or Pidgin.

Safety: the site is fixed by our code (from the customer's phone number), never chosen by
Gemini, so a customer can only ever ask about their own system.

Tools:
    battery_now      battery level, charging or not, how long it will last
    can_i_run        can I use this appliance right now? (inverter limit + battery + night ahead)
    tomorrow_plan    tomorrow's expected solar vs normal use, and the best hours for heavy loads
    money_view       naira saved by solar, NEPA spend, fuel avoided
    battery_card     battery health report (for warranty or resale)
    open_problems    problems SolarDokta has found, in plain words, with what to do
"""

import logging
from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np
import pandas as pd

from app.agent.appliances import find_appliance
from app.db import get_client
from app.detect.battery import FADE_ALARM, FADE_WINDOW, fade_per_year
from app.detect.expected import expected_power
from app.simulator import store
from app.simulator.battery import CHEMISTRIES
from app.simulator.dispatch import SBU_BACK_TO_GRID_SOC
from app.simulator.engine import TELEMETRY_COLUMNS
from app.simulator.faults import _iso
from app.simulator.grid import BAND_HOURS, supply
from app.simulator.site import SiteConfig
from app.weather import open_meteo
from app.weather.points import weather_point

log = logging.getLogger(__name__)

STALE_MIN = 20              # a reading older than this means the inverter may be offline
MORNING_HOUR = 7            # solar takes over from the battery around 7am
HEAVY_SPARE_W = 800         # "spare sun" big enough for an iron or pumping machine
SURGE_LIMIT = 2.0           # inverters survive about 2x their rating for a second (motor start)


@dataclass
class ToolContext:
    site: SiteConfig
    client: object = None
    role: str = "customer"                 # "customer" or "staff"
    now: pd.Timestamp | None = None        # fixed time for tests; None = real time
    cache: dict = field(default_factory=dict)

    def __post_init__(self):
        self.client = self.client or get_client()

    @property
    def time(self) -> pd.Timestamp:
        t = self.now if self.now is not None else pd.Timestamp.now(tz="UTC")
        return t.tz_convert(self.site.timezone)


# ---------- shared lookups ----------

def site_row(ctx: ToolContext) -> dict:
    """Extra site details not in SiteConfig (name, generator, install date)."""
    if "site_row" not in ctx.cache:
        rows = ctx.client.table("sites").select("*").eq("id", ctx.site.id).execute().data
        ctx.cache["site_row"] = rows[0] if rows else {}
    return ctx.cache["site_row"]


def latest_reading(ctx: ToolContext) -> dict | None:
    rows = (ctx.client.table("telemetry").select("ts," + ",".join(TELEMETRY_COLUMNS))
            .eq("site_id", ctx.site.id).lte("ts", _iso(ctx.time)).order("ts", desc=True)
            .range(0, 0).execute().data)
    if not rows:
        return None
    r = dict(rows[0])
    r["ts"] = pd.Timestamp(r["ts"]).tz_convert(ctx.site.timezone)
    return r


def battery_health_now(ctx: ToolContext) -> tuple[float, bool]:
    """(state of health, measured?) from the last month of deep-discharge estimates."""
    est = store.load_battery_estimates(ctx.site, ctx.time - pd.Timedelta(days=60), ctx.client)
    if len(est) < 3:
        return 1.0, False                   # not enough deep discharges yet: assume healthy
    recent = est.loc[est.index[-1] - pd.Timedelta(days=30):]
    return float(np.clip(recent.median(), 0.3, 1.0)), True


def hourly_profile(ctx: ToolContext, days: int = 7) -> pd.DataFrame | None:
    """Average use and solar (kWh) for each hour of the day over the last week."""
    since = ctx.time - pd.Timedelta(days=days)
    rows = (ctx.client.table("telemetry_hourly").select("hour_ts,load_kwh,pv_kwh,samples")
            .eq("site_id", ctx.site.id).gte("hour_ts", _iso(since)).lt("hour_ts", _iso(ctx.time))
            .order("hour_ts").range(0, 9999).execute().data)
    if not rows:
        return None
    df = pd.DataFrame(rows)
    df = df[df["samples"] >= 10]
    if df.empty:
        return None
    hour = pd.to_datetime(df["hour_ts"], utc=True).dt.tz_convert(ctx.site.timezone).dt.hour
    prof = df[["load_kwh", "pv_kwh"]].astype(float).groupby(hour.to_numpy()).mean()
    return prof.reindex(range(24)).fillna(prof.mean())


def net_need_until_morning(prof: pd.DataFrame, now: pd.Timestamp) -> float:
    """Energy (kWh) the house normally needs beyond solar from now until 7am."""
    end = now.normalize() + pd.Timedelta(hours=MORNING_HOUR)
    if end <= now:
        end += pd.Timedelta(days=1)
    need, t = 0.0, now
    while t < end:
        nxt = min(t.floor("1h") + pd.Timedelta(hours=1), end)
        frac = (nxt - t) / pd.Timedelta(hours=1)
        h = prof.loc[t.hour]
        need += max(0.0, h["load_kwh"] - h["pv_kwh"]) * frac
        t = nxt
    return need


def next_morning(now: pd.Timestamp) -> pd.Timestamp | None:
    """7am next morning if it's evening or night now (no solar until then), else None."""
    if MORNING_HOUR <= now.hour < 17:
        return None
    t = now.normalize() + pd.Timedelta(hours=MORNING_HOUR)
    return t if t > now else t + pd.Timedelta(days=1)


def open_finding_targets(ctx: ToolContext, kind: str) -> set[str]:
    rows = (ctx.client.table("findings").select("kind,details").eq("site_id", ctx.site.id)
            .eq("status", "open").execute().data)
    return {(r.get("details") or {}).get("target") for r in rows if r["kind"] == kind}


def _clock(t: pd.Timestamp) -> str:
    return t.strftime("%I:%M %p").lstrip("0")


# ---------- tools ----------

def battery_now(ctx: ToolContext) -> dict:
    site, r = ctx.site, latest_reading(ctx)
    if r is None:
        return {"error": "no readings from this system yet"}
    chem = CHEMISTRIES[site.battery_chemistry]
    soh, measured = battery_health_now(ctx)
    usable = site.battery_kwh * soh
    soc = float(r["batt_soc"])
    batt_w = float(r["batt_v"]) * float(r["batt_a"])
    left_kwh = max(0.0, soc - chem.min_soc) * usable * chem.eff_discharge
    out = {
        "battery_percent": round(soc * 100),
        "status": "charging" if batt_w > 20 else "discharging" if batt_w < -20 else "resting",
        "battery_power_w": round(batt_w),
        "solar_now_w": round(float(r["pv1_w"]) + float(r["pv2_w"])),
        "house_using_w": round(float(r["load_w"])),
        "nepa_on": float(r["grid_v"]) > 100,
        "energy_left_kwh": round(left_kwh, 1),
        "battery_cuts_off_at_percent": round(chem.min_soc * 100),
        "reading_time": _clock(r["ts"]),
    }
    if batt_w < -20:
        hours = left_kwh / (-batt_w / 1000)
        out["hours_left_at_this_rate"] = round(hours, 1)
        empty = ctx.time + pd.Timedelta(hours=hours)
        sunrise = next_morning(ctx.time)
        evening = ctx.time.normalize() + pd.Timedelta(hours=17)
        if sunrise is not None and empty >= sunrise:
            out["lasts_until_morning_sun"] = True          # solar takes over before it's empty
        elif sunrise is None and empty >= evening:
            out["lasts_through_the_day"] = True            # and the sun can recharge it meanwhile
        elif hours < 24:
            day = "" if empty.date() == ctx.time.date() else "tomorrow "
            out["empty_around"] = day + _clock(empty)
    if r.get("fault_code"):
        out["inverter_fault_now"] = r["fault_code"]
    age = (ctx.time - r["ts"]) / pd.Timedelta(minutes=1)
    if age > STALE_MIN:
        out["warning"] = f"last reading is {age:.0f} minutes old; the inverter may be offline"
    out.update(tonight_outlook(ctx, left_kwh, (1 - chem.min_soc) * usable * chem.eff_discharge))
    if not measured:
        out["note"] = "battery health not measured yet; assumed as new"
    return out


def tonight_outlook(ctx: ToolContext, left_kwh: float, full_kwh: float) -> dict:
    """Will the battery get through tonight, judged from what this house normally uses?"""
    prof = hourly_profile(ctx)
    if prof is None:
        return {}
    now = ctx.time
    if next_morning(now) is None:                     # daytime: judge tonight from 6pm
        need = net_need_until_morning(prof, now.normalize() + pd.Timedelta(hours=18))
        return {"normal_night_use_kwh": round(need, 1),
                "full_battery_holds_kwh": round(full_kwh, 1),
                "tonight": ("enough for a normal night if the battery is full by evening"
                            if full_kwh >= need else
                            "a normal night uses more than a full battery holds")}
    need = net_need_until_morning(prof, now)
    return {"needed_until_morning_kwh": round(need, 1),
            "tonight": ("enough to last until the morning sun" if left_kwh >= need
                        else "may run out before morning at normal use")}


def can_i_run(ctx: ToolContext, appliance: str = "", watts: float | None = None,
              minutes: float | None = None) -> dict:
    site = ctx.site
    spec = find_appliance(appliance) if appliance else None
    w = float(watts) if watts else (spec.watts if spec else None)
    if not w:
        return {"verdict": "need_watts", "appliance": appliance,
                "message": "unknown appliance: ask for the watts written on its label"}
    mins = float(minutes) if minutes else (spec.minutes if spec else 30.0)
    surge = spec.surge if spec else 1.0
    name = spec.name if spec else appliance

    r = latest_reading(ctx)
    if r is None:
        return {"verdict": "no_data", "message": "no readings from this system yet"}
    chem = CHEMISTRIES[site.battery_chemistry]
    inv_w = site.inverter_kw * 1000
    load, pv = float(r["load_w"]), float(r["pv1_w"]) + float(r["pv2_w"])
    soc, grid_on = float(r["batt_soc"]), float(r["grid_v"]) > 100
    soh, _ = battery_health_now(ctx)
    usable = site.battery_kwh * soh

    out = {"appliance": name, "appliance_watts": round(w), "minutes": round(mins),
           "house_using_now_w": round(load), "inverter_limit_w": round(inv_w),
           "battery_percent": round(soc * 100), "solar_now_w": round(pv), "nepa_on": grid_on}
    reasons, tips = [], []

    def done(verdict):
        out.update(verdict=verdict, reasons=reasons, tips=tips)
        return out

    if r.get("fault_code"):
        reasons.append(f"the inverter is showing a fault right now ({r['fault_code']})")
        return done("no")
    if load + w > inv_w:
        reasons.append(f"it would push the inverter over its {inv_w:.0f} W limit and trip it")
        tips.append(f"switch off about {load + w - inv_w:.0f} W of other things first")
        return done("no")
    if load + w * surge > SURGE_LIMIT * inv_w:
        reasons.append("its starting kick (motor surge) could trip the inverter")
        tips.append("switch off other big things before starting it")
        return done("no")
    if load + w > 0.9 * inv_w:
        tips.append("the inverter will be near its limit: don't start anything else big")

    if grid_on and (site.inverter_mode == "SUB" or soc <= SBU_BACK_TO_GRID_SOC):
        reasons.append("NEPA is on and is powering the house, so the battery is not used")
        out["powered_by"] = "nepa"
        return done("yes")

    spare = max(0.0, pv - load)             # solar now going into the battery
    from_batt = max(0.0, w - spare) / 1000 * mins / 60
    soc_after = soc - from_batt / (usable * chem.eff_discharge)
    left_after = max(0.0, soc_after - chem.min_soc) * usable * chem.eff_discharge
    out["battery_percent_after"] = round(max(soc_after, 0) * 100)
    out["powered_by"] = "solar" if from_batt == 0 else "battery" if spare < 50 else "solar+battery"

    if soc_after <= chem.min_soc + 0.03:
        reasons.append("the battery would run down to its cut-off and the inverter would switch off")
        tips.append("wait for strong sun (late morning to mid-afternoon) or NEPA")
        return done("no")

    hour = ctx.time.hour
    if hour >= 17 or hour < MORNING_HOUR:
        prof = hourly_profile(ctx)
        if prof is not None:
            need = net_need_until_morning(prof, ctx.time)
            out["needed_until_morning_kwh"] = round(need, 1)
            out["left_after_kwh"] = round(left_after, 1)
            if left_after < need:
                reasons.append("the battery may not last until morning after this")
                tips.append("use it for a shorter time, switch off the AC or other big loads "
                            "tonight, or wait for NEPA or tomorrow's sun")
                return done("yes_but")
    if out["powered_by"] == "solar":
        reasons.append("there is enough spare solar right now")
    elif soc > 0.97 and 9 <= hour < 16:
        out["powered_by"] = "solar"         # full battery: the panels are holding back power
        reasons.append("the battery is full, so the extra sun is otherwise being wasted")
    else:
        reasons.append("the battery has enough charge")
    return done("yes")


@lru_cache(maxsize=16)
def _forecast_cached(lat: float, lon: float, hour: str) -> pd.DataFrame:
    return open_meteo.fetch_forecast(lat, lon, days=3)


FORECAST_FRESH = pd.Timedelta(hours=6)


def saved_forecast(ctx: ToolContext) -> tuple[pd.DataFrame | None, pd.Timestamp | None]:
    """The forecast the 'forecast' job saved in the database, and when it was fetched."""
    p = weather_point(ctx.site.latitude, ctx.site.longitude)
    rows = (ctx.client.table("weather_forecast")
            .select("ts,ghi_wm2,temp_c,cloud_cover_pct,fetched_at")
            .eq("latitude", p.latitude).eq("longitude", p.longitude)
            .gte("ts", _iso(ctx.time - pd.Timedelta(days=1))).order("ts")
            .range(0, 9999).execute().data)
    if not rows:
        return None, None
    df = pd.DataFrame(rows)
    fetched = pd.to_datetime(df.pop("fetched_at"), utc=True).min()
    df.index = pd.to_datetime(df.pop("ts"), utc=True)
    return df.astype(float), fetched


def forecast_weather(ctx: ToolContext) -> tuple[pd.DataFrame, str]:
    """Hourly forecast (UTC, Open-Meteo 'right' labels) covering today and tomorrow.

    Uses the copy the forecast job saved (fast) when it is fresh and reaches the end of
    tomorrow; otherwise asks Open-Meteo (cached for an hour); if that fails, any saved copy.
    """
    saved, fetched = saved_forecast(ctx)
    tomorrow_end = (ctx.time.normalize() + pd.Timedelta(days=2)).tz_convert("UTC")
    if (saved is not None and pd.Timestamp.now(tz="UTC") - fetched < FORECAST_FRESH
            and saved.index.max() >= tomorrow_end - pd.Timedelta(hours=1)):
        return saved, "right"
    p = weather_point(ctx.site.latitude, ctx.site.longitude)
    try:
        return _forecast_cached(p.latitude, p.longitude, f"{pd.Timestamp.now(tz='UTC'):%Y%m%d%H}"), "right"
    except Exception:                        # no internet: use whatever the forecast job saved
        log.warning("Live forecast failed; using the saved forecast", exc_info=True)
        if saved is None:
            raise
        return saved, "right"


def _ranges(hours: list[int]) -> list[str]:
    out, start = [], None
    for h in range(25):
        if h in hours and start is None:
            start = h
        if h not in hours and start is not None:
            out.append(f"{start:02d}:00-{h:02d}:00")
            start = None
    return out


def tomorrow_plan(ctx: ToolContext) -> dict:
    site = ctx.site
    day = ctx.time.normalize() + pd.Timedelta(days=1)
    hourly, label = forecast_weather(ctx)
    idx = pd.date_range(day, day + pd.Timedelta(days=1), freq="5min", inclusive="left")
    exp = expected_power(site, hourly[["ghi_wm2", "temp_c"]], label, idx)

    # Scale by how the panels have really been doing lately (dust, a dead string, shade).
    health = store.load_health(site, ctx.time - pd.Timedelta(days=14), ctx.client)
    factors = {}
    for s in site.strings:
        pr = health[f"pr_{s}"].dropna() if len(health) else pd.Series(dtype=float)
        factors[s] = float(np.clip(pr.median(), 0.0, 1.1)) if len(pr) >= 3 else 1.0
    for s in open_finding_targets(ctx, "string_failure") & set(factors):
        factors[s] = 0.0                    # a dead string makes nothing until it's repaired
    pv_w = sum(exp[f"{s}_exp_w"] * f for s, f in factors.items())
    solar_h = pv_w.groupby(pv_w.index.hour).mean() / 1000            # kWh in each hour
    solar_kwh = float(solar_h.sum())

    # How sunny: total sunlight on the ground tomorrow (kWh per m2).
    w = hourly.copy()
    w.index = w.index.tz_convert(site.timezone) - pd.Timedelta(hours=1)   # 'right' -> hour start
    tw = w.loc[day:day + pd.Timedelta(hours=23)]
    sun = float(tw["ghi_wm2"].sum()) / 1000
    sky = "sunny" if sun >= 5.5 else "partly cloudy" if sun >= 4.0 else "cloudy"

    out = {"date": day.strftime("%A %d %B"), "sky": sky, "sunlight_kwh_per_m2": round(sun, 1),
           "expected_solar_kwh": round(solar_kwh, 1),
           "expected_nepa_hours": BAND_HOURS.get(site.tariff_band),
           "battery_size_kwh": site.battery_kwh}
    if "cloud_cover_pct" in tw and tw["cloud_cover_pct"].notna().any():
        daylight = tw[tw["ghi_wm2"] > 50]
        out["daytime_cloud_percent"] = round(float(daylight["cloud_cover_pct"].mean()))
    weak = {s: round(f, 2) for s, f in factors.items() if f < 0.85}
    if weak:
        out["weak_panel_strings"] = weak
        out["note"] = "forecast lowered because some panels are underperforming (see open_problems)"
    dead = [f"string {s[-1]}" for s, f in factors.items() if f == 0.0]
    if dead:
        out["dead_panel_strings"] = dead
        out["note"] = (f"{' and '.join(dead)} is producing nothing (call the installer); "
                       "the forecast only counts the panels that work")

    prof = hourly_profile(ctx)
    if prof is not None:
        use_kwh = float(prof["load_kwh"].sum())
        spare = solar_h.reindex(range(24), fill_value=0) - prof["load_kwh"]
        out["normal_daily_use_kwh"] = round(use_kwh, 1)
        out["solar_covers_percent"] = round(min(100.0, 100 * solar_kwh / use_kwh)) if use_kwh else None
        out["hourly_solar_kw"] = [round(float(v), 2) for v in solar_h.reindex(range(24), fill_value=0)]
        out["hourly_use_kw"] = [round(float(v), 2) for v in prof["load_kwh"]]
        best = [h for h in range(24) if spare[h] * 1000 >= HEAVY_SPARE_W]
        out["best_hours_for_heavy_appliances"] = _ranges(best) or None
        out["peak_spare_solar_w"] = round(max(0.0, float(spare.max())) * 1000)
    return out


def latest_prices(client) -> dict[str, dict]:
    rows = (client.table("prices").select("*").order("effective_from", desc=True)
            .range(0, 999).execute().data)
    latest: dict[str, dict] = {}
    for r in rows:
        latest.setdefault(r["item"], r)
    return latest


def own_prices(ctx: ToolContext) -> dict[str, dict]:
    """This site's own newest prices (from the customer's receipts or the fuel form)."""
    try:
        rows = (ctx.client.table("site_prices").select("item,price_ngn,effective_from,source")
                .eq("site_id", ctx.site.id).order("effective_from", desc=True)
                .range(0, 99).execute().data)
    except Exception:  # noqa: BLE001 - table not created yet (migration 009)
        return {}
    out: dict[str, dict] = {}
    for r in rows:
        out.setdefault(r["item"], r)
    return out


def pricing(ctx: ToolContext) -> dict:
    """NEPA tariff and generator cost for this site. The customer's own receipts win over the
    city-wide prices table."""
    site, row, prices, own = ctx.site, site_row(ctx), latest_prices(ctx.client), own_prices(ctx)
    band = own.get("grid") or prices[f"grid_band_{site.tariff_band.lower()}"]
    fuel = row.get("generator_fuel", "petrol")
    fuel_row = own.get(fuel) or prices.get(fuel)
    kwh_per_litre = float(row.get("generator_kwh_per_litre") or 1.5)
    fuel_price = float(fuel_row["price_ngn"]) if fuel_row else None
    return {"tariff": float(band["price_ngn"]), "fuel": fuel, "fuel_price": fuel_price,
            "kwh_per_litre": kwh_per_litre,
            "gen_cost": fuel_price / kwh_per_litre if fuel_price else None,
            "own_prices": sorted(own),
            "placeholder": any(p and "PLACEHOLDER" in (p.get("source") or "").upper()
                               for p in (band, fuel_row))}


def solar_value(solar_kwh: float, nepa_share: float, pr: dict) -> float:
    """Naira the solar energy would have cost otherwise: NEPA price while NEPA was on,
    generator cost while it was off."""
    off = solar_kwh * (1 - nepa_share) * (pr["gen_cost"] or 0.0)
    return solar_kwh * nepa_share * pr["tariff"] + off


def money_view(ctx: ToolContext, days: int = 30) -> dict:
    site = ctx.site
    days = int(max(1, min(days or 30, 365)))
    today = ctx.time.normalize()
    rows = (ctx.client.table("telemetry_daily")
            .select("day,pv_kwh,load_kwh,grid_import_kwh,grid_on_minutes")
            .eq("site_id", site.id).gte("day", (today - pd.Timedelta(days=days)).strftime("%Y-%m-%d"))
            .lt("day", today.strftime("%Y-%m-%d")).order("day").range(0, 999).execute().data)
    if not rows:
        return {"error": "no daily totals yet"}
    d = pd.DataFrame(rows)
    n = len(d)
    solar, use = float(d["pv_kwh"].sum()), float(d["load_kwh"].sum())
    grid_kwh = float(d["grid_import_kwh"].sum())
    nepa_share = float(d["grid_on_minutes"].sum()) / (n * 1440)

    pr = pricing(ctx)
    tariff, fuel, fuel_price = pr["tariff"], pr["fuel"], pr["fuel_price"]
    kwh_per_litre, gen_cost = pr["kwh_per_litre"], pr["gen_cost"]
    no_nepa_kwh = solar * (1 - nepa_share)
    saved = solar_value(solar, nepa_share, pr)
    out = {
        "period_days": n,
        "solar_energy_kwh": round(solar, 1),
        "house_used_kwh": round(use, 1),
        "nepa_bought_kwh": round(grid_kwh, 1),
        "nepa_cost_ngn": round(grid_kwh * tariff, -1),
        "nepa_available_percent": round(100 * nepa_share),
        "saved_by_solar_ngn": round(saved, -2),
        "saved_per_month_ngn": round(saved * 30 / n, -2),
        "tariff": f"Band {site.tariff_band}: N{tariff:,.0f}/kWh",
    }
    if gen_cost:
        out["generator_fuel_avoided_litres"] = round(no_nepa_kwh / kwh_per_litre)
        out["fuel_price"] = f"{fuel}: N{fuel_price:,.0f}/litre"
    if pr["placeholder"]:
        out["warning"] = "prices are placeholders, not current market prices"
    if pr["own_prices"]:
        out["your_own_prices"] = pr["own_prices"]          # from their receipts / fuel form
    out["assumption"] = (f"generator makes {kwh_per_litre} kWh per litre; solar is valued at "
                         "NEPA price while NEPA is on and generator cost while it is off")
    return out


def battery_card(ctx: ToolContext) -> dict:
    site = ctx.site
    row = site_row(ctx)
    est = store.load_battery_estimates(site, ctx.time - pd.Timedelta(days=365), ctx.client)
    daily = (ctx.client.table("telemetry_daily").select("day,batt_discharge_kwh,batt_temp_max")
             .eq("site_id", site.id).order("day").range(0, 9999).execute().data)
    out = {"chemistry": "lithium (LiFePO4)" if site.battery_chemistry == "lifepo4" else "lead-acid",
           "nameplate_kwh": site.battery_kwh, "deep_discharges_measured": len(est)}
    if row.get("install_date"):
        age = (ctx.time.tz_localize(None) - pd.Timestamp(row["install_date"])) / pd.Timedelta(days=365)
        out["age_years"] = round(age, 1)
    if daily:
        d = pd.DataFrame(daily)
        out["equivalent_full_cycles"] = round(float(d["batt_discharge_kwh"].astype(float).sum())
                                              / site.battery_kwh)
        hot = d["batt_temp_max"].dropna().astype(float)
        if len(hot):
            out["days_above_35C_percent"] = round(100 * float((hot > 35).mean()))
    if len(est) < 3:
        out["health"] = "not measured yet (needs a few nights where the battery drops by 30% or more)"
        return out

    soh = float(est.loc[est.index[-1] - pd.Timedelta(days=30):].median())
    recent = est.loc[est.index[-1] - FADE_WINDOW:]
    rate = fade_per_year(recent)
    if np.isnan(rate):                      # too few recent estimates: use the whole year
        recent, rate = est, fade_per_year(est)
    out.update({"health_percent": round(soh * 100), "usable_kwh_now": round(soh * site.battery_kwh, 1),
                "status": ("healthy" if soh >= 0.9 else "ageing normally" if soh >= 0.8
                           else "below the usual 80% warranty line")})
    if not np.isnan(rate):
        out["health_lost_per_year_percent"] = round(rate * 100, 1)
        out["trend_confidence"] = "good" if len(recent) >= 20 else "low (few deep discharges)"
        if rate > FADE_ALARM:
            out["warning"] = "losing health much faster than normal (normal is 2-5% a year)"
        if soh > 0.8 and rate > 0.005:
            out["years_until_80_percent"] = round((soh - 0.8) / rate, 1)
    return out


PLAIN = {   # what each finding means, and what to do (Gemini translates to Pidgin when needed)
    "string_failure": ("one set of panels has stopped producing completely",
                       "call your installer; don't climb up or touch the wiring yourself"),
    "underrated_panel": ("one set of panels gives much less than it should (maybe substandard)",
                         "ask your installer to test the panels; may be covered by warranty"),
    "soiling": ("dust or dirt on the panels is cutting solar power",
                "have the panels washed with clean water early morning or evening"),
    "shading": ("something casts shade on the panels for part of the day",
                "check for a tree, wall, tank or new building blocking the sun"),
    "hot_battery_room": ("the battery is staying hot, which ages it faster",
                         "improve airflow around the battery; keep it out of direct sun"),
    "battery_fade": ("the battery is losing capacity faster than normal",
                     "ask your installer to check it; it may be a warranty case"),
    "overload": ("too many appliances were on at once and the inverter tripped",
                 "don't run big appliances (iron, pump, AC, microwave) at the same time"),
    "battery_ran_out": ("the battery ran empty and the inverter switched off",
                        "use less at night, or run heavy appliances in the afternoon sun"),
    "unusual_day": ("the system behaved unusually (machine-learning check)",
                    "technician: review the day's charts"),
    "customer_report": ("you reported a problem (voice note)",
                        "your technician has been told and will follow up"),
    "heatwave": ("a very hot day is forecast",
                 "keep the battery room ventilated; expect a little less solar at midday"),
}
STAFF_ONLY = {"unusual_day"}


def open_problems(ctx: ToolContext, days: int = 7) -> dict:
    site = ctx.site
    since = ctx.time - pd.Timedelta(days=int(days or 7))
    rows = (ctx.client.table("findings").select("kind,severity,status,ts_start,ts_end,details")
            .eq("site_id", site.id).gte("ts_start", _iso(ctx.time - pd.Timedelta(days=400)))
            .order("ts_start", desc=True).range(0, 499).execute().data)
    current, recent = [], []
    for f in rows:
        if ctx.role != "staff" and f["kind"] in STAFF_ONLY:
            continue
        what, todo = PLAIN.get(f["kind"], (f["kind"].replace("_", " "), "contact your installer"))
        start = pd.Timestamp(f["ts_start"]).tz_convert(site.timezone)
        item = {"problem": what, "what_to_do": todo, "urgency": f["severity"],
                "since": start.strftime("%d %b %I:%M %p")}
        target = (f.get("details") or {}).get("target")
        if target in ("pv1", "pv2"):
            item["panel_string"] = "string 1" if target == "pv1" else "string 2"
        if ctx.role == "staff":
            item.update(kind=f["kind"], details=f.get("details"))
        if f["status"] == "open":
            current.append(item)
        elif start >= since:
            recent.append(item)
    order = {"critical": 0, "warning": 1, "info": 2}
    current.sort(key=lambda i: order.get(i["urgency"], 3))
    return {"open_problems": current, f"events_last_{int(days or 7)}_days": recent[:10],
            "all_clear": not current}


def light_tracker(ctx: ToolContext, days: int = 14) -> dict:
    """How many hours of NEPA light the site got each day, against a normal period."""
    site = ctx.site
    days = int(max(3, min(days or 14, 60)))
    today = ctx.time.normalize()
    rows = (ctx.client.table("telemetry_daily").select("day,grid_on_minutes,soc_min")
            .eq("site_id", site.id).gte("day", (today - pd.Timedelta(days=days)).strftime("%Y-%m-%d"))
            .lt("day", today.strftime("%Y-%m-%d")).order("day").range(0, 999).execute().data)
    if not rows:
        return {"error": "no daily totals yet"}
    per_day = [{"day": pd.Timestamp(r["day"]).strftime("%a %d %b"),
                "hours": round(float(r["grid_on_minutes"]) / 60, 1)} for r in rows]
    hours = [d["hours"] for d in per_day]
    _, _, cond = supply(site, ctx.time)
    since = ctx.time - pd.Timedelta(days=days)
    outs = (ctx.client.table("findings").select("kind,details,ts_start").eq("site_id", site.id)
            .gte("ts_start", _iso(since)).range(0, 499).execute().data)
    blackout_min = sum(int((f.get("details") or {}).get("blackout_minutes", 0))
                       for f in outs if f["kind"] == "battery_ran_out")
    soc_min = [float(r["soc_min"]) for r in rows if r.get("soc_min") is not None]
    out = {
        "days": per_day,
        "average_hours_per_day": round(sum(hours) / len(hours), 1),
        "worst_day": min(per_day, key=lambda d: d["hours"]),
        "normal_hours_for_band": BAND_HOURS.get(site.tariff_band),
        "tariff_band": site.tariff_band,
        "home_blackout_hours": round(blackout_min / 60, 1),
        "home_blackouts": sum(1 for f in outs if f["kind"] == "battery_ran_out"),
        "battery_lowest_percent_avg": round(100 * sum(soc_min) / len(soc_min)) if soc_min else None,
    }
    if cond:
        out["situation"] = cond.note
        out["situation_since"] = cond.starts.strftime("%d %b")
    return out


HEAT_STRESS_C = 35.0       # battery temperature above which wear speeds up a lot
HEATWAVE_C = 35.0          # outdoor daytime high that counts as a heatwave
CELL_RISE_C = 28.0         # panels at midday run about this much hotter than the air
EL_NINO_NOTE = ("A strong El Niño is expected to keep Nigeria hotter than usual until early 2027 "
                "(WMO and NiMet). Heat ages batteries faster and panels make a little less.")


def heat_outlook(ctx: ToolContext) -> dict:
    """What the heat is doing to this system: battery temperature, extra wear, tomorrow's heat."""
    site = ctx.site
    chem = CHEMISTRIES[site.battery_chemistry]
    since = ctx.time - pd.Timedelta(days=30)
    rows = (ctx.client.table("telemetry_hourly").select("hour_ts,batt_temp_max,batt_discharge_kwh")
            .eq("site_id", site.id).gte("hour_ts", _iso(since)).order("hour_ts")
            .range(0, 9999).execute().data)
    out: dict = {"el_nino": EL_NINO_NOTE}
    temps = np.array([float(r["batt_temp_max"]) for r in rows if r.get("batt_temp_max") is not None])
    if len(temps) >= 24:
        factor = float(np.mean(2 ** ((temps - 25) / 10)))       # wear doubles every 10 C
        cycles_per_year = sum(float(r["batt_discharge_kwh"] or 0) for r in rows) / site.battery_kwh * 365 / 30
        normal = chem.calendar_fade_per_year + cycles_per_year * chem.cycle_fade      # at 25 C
        daily = pd.Series(temps, index=pd.to_datetime([r["hour_ts"] for r in rows
                                                        if r.get("batt_temp_max") is not None], utc=True))
        daily_max = daily.tz_convert(site.timezone).resample("1D").max().dropna()
        out.update({
            "battery_average_c": round(float(temps.mean()), 1),
            "battery_hottest_c": round(float(temps.max()), 1),
            "battery_hot_days_last_30": int((daily_max > HEAT_STRESS_C).sum()),
            "ageing_speed_vs_25c": round(factor, 2),
            "extra_wear_percent_per_year": round(100 * normal * max(0.0, factor - 1), 2),
            "extra_wear_this_el_nino_season_percent": round(100 * normal * max(0.0, factor - 1) / 2, 2),
            "normal_wear_percent_per_year": round(100 * normal, 2),
            # months of battery life the extra heat costs between now and the end of February
            "life_lost_months_this_season": round(12 * max(0.0, factor - 1) / 2, 1),
            "daily_max_c": [{"day": f"{d.day} {d:%b}", "c": round(float(v), 1)} for d, v in daily_max.items()],
        })
    try:
        hourly, label = forecast_weather(ctx)
        w = hourly["temp_c"].copy()
        w.index = w.index.tz_convert(site.timezone) - (pd.Timedelta(hours=1) if label == "right" else pd.Timedelta(0))
        tomorrow = ctx.time.normalize() + pd.Timedelta(days=1)
        high = float(w.loc[tomorrow:tomorrow + pd.Timedelta(hours=23)].max())
        cell = high + CELL_RISE_C
        out.update({
            "tomorrow_high_c": round(high),
            "heatwave_tomorrow": high >= HEATWAVE_C,
            "panel_midday_loss_percent": round(100 * 0.0035 * max(0.0, cell - 25)),
        })
    except Exception:  # noqa: BLE001 - forecast unavailable: still report the battery side
        log.info("No forecast for heat_outlook at %s", site.code)
    tips = ["keep the battery and inverter room well ventilated and out of direct sun",
            "don't block the inverter's air vents"]
    if out.get("battery_hot_days_last_30", 0) > 3:
        tips.insert(0, "the battery is getting hot often: ask your installer about moving it or adding a vent")
    if out.get("heatwave_tomorrow"):
        tips.append("run heavy appliances in the morning, before the hottest hours")
    out["tips"] = tips
    return out


TOOLS = {f.__name__: f for f in
         (battery_now, can_i_run, tomorrow_plan, money_view, battery_card, open_problems,
          light_tracker, heat_outlook)}

# What Gemini is told about each tool (JSON Schema for the arguments).
TOOL_SPECS = [
    {"name": "battery_now",
     "description": "Current battery level, whether it is charging, solar power now, house use "
                    "now, whether NEPA (grid) is on, and how long the battery will last.",
     "parameters": {"type": "object", "properties": {}}},
    {"name": "can_i_run",
     "description": "Check if an appliance can be used right now without tripping the inverter "
                    "or emptying the battery before morning. Use for any 'can I use/put on X' "
                    "question.",
     "parameters": {"type": "object", "properties": {
         "appliance": {"type": "string", "description": "e.g. 'pressing iron', 'pumping machine', 'AC'"},
         "watts": {"type": "number", "description": "only if the customer gave the wattage"},
         "minutes": {"type": "number", "description": "how long they will use it, if they said"}},
         "required": ["appliance"]}},
    {"name": "tomorrow_plan",
     "description": "Tomorrow's weather and expected solar energy versus normal use, the best "
                    "hours for heavy appliances, and expected NEPA hours.",
     "parameters": {"type": "object", "properties": {}}},
    {"name": "money_view",
     "description": "Money: naira saved by solar, NEPA spending, generator fuel avoided.",
     "parameters": {"type": "object", "properties": {
         "days": {"type": "integer", "description": "period in days (default 30)"}}}},
    {"name": "battery_card",
     "description": "Battery health report: health %, usable capacity, how fast it is ageing, "
                    "cycles, heat. For warranty claims or selling the system.",
     "parameters": {"type": "object", "properties": {}}},
    {"name": "open_problems",
     "description": "Problems SolarDokta has detected on this system (dead or weak panels, dust, "
                    "shade, battery issues, overloads) with what to do.",
     "parameters": {"type": "object", "properties": {
         "days": {"type": "integer", "description": "also list events from the last N days (default 7; "
                  "use 30 for 'why did...' or 'recently' questions)"}}}},
    {"name": "light_tracker",
     "description": "NEPA (grid) supply: hours of light per day recently vs normal, the current "
                    "situation, and how often the home had no power at all.",
     "parameters": {"type": "object", "properties": {
         "days": {"type": "integer", "description": "how many days back (default 14)"}}}},
    {"name": "heat_outlook",
     "description": "What heat (and the El Niño season) is doing to this system: battery "
                    "temperature, extra battery wear, tomorrow's high and solar loss, tips.",
     "parameters": {"type": "object", "properties": {}}},
]


def run_tool(ctx: ToolContext, name: str, args: dict | None) -> dict:
    """Run one tool safely: errors come back as {'error': ...} for Gemini to explain."""
    fn = TOOLS.get(name)
    if fn is None:
        return {"error": f"unknown tool {name}"}
    try:
        return fn(ctx, **(args or {}))
    except TypeError as exc:
        return {"error": f"bad arguments for {name}: {exc}"}
    except Exception as exc:
        log.exception("Tool %s failed for %s", name, ctx.site.code)
        return {"error": f"{name} failed: {type(exc).__name__}"}
