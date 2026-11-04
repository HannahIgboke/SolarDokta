"""What-if tests for technicians: "how would this site cope if...?"

We take the site's real state right now (battery level and health, the faults it really has) and
run the simulator for the next few days twice, entirely in memory:
    1. as things are (the forecast weather, NEPA as it has been), and
    2. with the technician's changes: fewer hours of NEPA, a heatwave, a hotter battery room,
       dust, a dead panel group, or a new appliance.
Then we compare the two: hours without power, nights the battery ran out, how low the battery
went, solar made, battery temperature and the extra battery wear.

Nothing is saved: the customer's dashboard never sees a what-if run.
"""

import copy
import logging

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from app.agent.tools import ToolContext, battery_health_now, latest_reading
from app.simulator import grid, store
from app.simulator.battery import CHEMISTRIES, BatteryState
from app.simulator.engine import STEP, SimState, simulate_window
from app.simulator.faults import Fault
from app.simulator.site import SiteConfig

log = logging.getLogger(__name__)


class NewAppliance(BaseModel):
    name: str = Field(default="New appliance", max_length=40)
    watts: float = Field(gt=0, le=10_000)
    hours_per_day: float = Field(gt=0, le=24)
    from_hour: float = Field(default=18, ge=0, lt=24)


class Scenario(BaseModel):
    days: int = Field(default=7, ge=2, le=7)
    nepa_hours: float | None = Field(default=None, ge=0, le=24)     # None = as it has been
    heatwave_c: float = Field(default=0, ge=0, le=10)                # hotter outdoor air
    battery_room_c: float = Field(default=0, ge=0, le=15)            # hotter battery room
    dust_percent: float = Field(default=0, ge=0, le=60)
    panel_group_off: str | None = Field(default=None, pattern="^pv[12]$")
    new_appliance: NewAppliance | None = None


def weather_for(site: SiteConfig, start: pd.Timestamp, end: pd.Timestamp) -> tuple[pd.DataFrame, str]:
    from app.simulator.weather_source import (
        hourly_weather,  # needs the internet (forecast)
    )
    return hourly_weather(site, start, end)


def _start_state(site: SiteConfig, ctx: ToolContext) -> tuple[SimState, pd.Timestamp]:
    state, last_ts = store.load_state(site, ctx.client)
    if state is not None and last_ts is not None:
        return state, last_ts
    r = latest_reading(ctx)                      # no saved simulator state: start from the last reading
    if r is None:
        raise ValueError("no readings from this site yet")
    soh, _ = battery_health_now(ctx)
    return SimState(BatteryState(soc=float(r["batt_soc"]), soh=soh)), r["ts"].floor("5min")


def _metrics(site: SiteConfig, out: pd.DataFrame, start_soh: float) -> dict:
    step_h = STEP / pd.Timedelta(hours=1)
    dark = out["unserved_w"] > 50 if "unserved_w" in out else pd.Series(False, index=out.index)
    solar = (out["pv1_w"] + out["pv2_w"]) * step_h / 1000
    temp = out["batt_temp_c"].astype(float)
    days = out.groupby(out.index.normalize())
    per_day = [{"day": f"{d:%a} {d.day}", "battery_low": round(float(g["batt_soc"].min()) * 100),
                "blackout_hours": round(float(dark.loc[g.index].sum()) * step_h, 1),
                "solar_kwh": round(float(solar.loc[g.index].sum()), 1),
                "nepa_hours": round(float((g["grid_v"] > 100).sum()) * step_h, 1)}
               for d, g in days]
    chem = CHEMISTRIES[site.battery_chemistry]
    speed = float(np.mean(2 ** ((temp - 25) / 10)))
    cycles = float((-out["batt_w"].clip(upper=0)).sum()) * step_h / 1000 / site.battery_kwh if "batt_w" in out else 0.0
    wear = (chem.calendar_fade_per_year * len(per_day) / 365 + cycles * chem.cycle_fade) * speed
    return {
        "blackout_hours": round(float(dark.sum()) * step_h, 1),
        "nights_without_power": int(sum(1 for p in per_day if p["blackout_hours"] > 0)),
        "battery_lowest_percent": round(float(out["batt_soc"].min()) * 100),
        "solar_kwh": round(float(solar.sum()), 1),
        "nepa_hours_per_day": round(float((out["grid_v"] > 100).sum()) * step_h / max(1, len(per_day)), 1),
        "battery_hottest_c": round(float(temp.max()), 1),
        "battery_ageing_speed": round(speed, 2),
        "battery_wear_percent": round(100 * wear, 3),
        "days": per_day,
    }


def _scenario_faults(sc: Scenario, start: pd.Timestamp, end: pd.Timestamp) -> list[Fault]:
    out = []
    if sc.battery_room_c:
        out.append(Fault("hot_battery_room", start, end, "all", {"extra_c": sc.battery_room_c}))
    if sc.dust_percent:
        out.append(Fault("soiling", start, end, "all", {"max_loss": sc.dust_percent / 100, "ramp_days": 0.01}))
    if sc.panel_group_off:
        out.append(Fault("string_failure", start, end, sc.panel_group_off, {}))
    if a := sc.new_appliance:
        day = start.normalize()
        while day < end:
            s = day + pd.Timedelta(hours=a.from_hour)
            out.append(Fault("overload", s, s + pd.Timedelta(hours=a.hours_per_day), "all", {"extra_w": a.watts}))
            day += pd.Timedelta(days=1)
    return out


def run(site: SiteConfig, sc: Scenario, client=None) -> dict:
    ctx = ToolContext(site, client=client)
    grid.set_conditions(store.load_grid_conditions(ctx.client))
    state, after = _start_state(site, ctx)
    after = after.tz_convert(site.timezone)
    until = after + pd.Timedelta(days=sc.days)
    hourly, label = weather_for(site, after.normalize(), until.normalize() + pd.Timedelta(days=1))
    faults = store.load_faults(site, after, until, ctx.client)
    soh = state.battery.soh

    base, _ = simulate_window(site, after, until, hourly, label, copy.deepcopy(state), faults)

    hot = hourly.copy()
    hot["temp_c"] = hot["temp_c"] + sc.heatwave_c
    token = None
    if sc.nepa_hours is not None:
        token = grid.what_if_hours.set(grid.GridCondition(site.city, after.date(), None, sc.nepa_hours,
                                                          max(1.0, (24 - sc.nepa_hours) / 3), "what-if"))
    try:
        test, _ = simulate_window(site, after, until, hot, label, copy.deepcopy(state),
                                  faults + _scenario_faults(sc, after, until))
    finally:
        if token is not None:
            grid.what_if_hours.reset(token)

    b, t = _metrics(site, base, soh), _metrics(site, test, soh)
    return {"from": after.isoformat(), "days": sc.days, "as_is": b, "what_if": t,
            "summary": summary(b, t), "scenario": sc.model_dump()}


def summary(b: dict, t: dict) -> list[str]:
    """Plain sentences comparing the two runs."""
    out = []
    if t["blackout_hours"] > b["blackout_hours"] + 0.2:
        out.append(f"The home would be without power for {t['blackout_hours']:.0f} hours over the period "
                   f"(instead of {b['blackout_hours']:.0f}), on {t['nights_without_power']} different days.")
    elif t["blackout_hours"] > 0:
        out.append(f"About {t['blackout_hours']:.0f} hours without power, the same as now.")
    else:
        out.append("The home would keep power the whole time.")
    if t["battery_lowest_percent"] < b["battery_lowest_percent"] - 2:
        out.append(f"The battery would drop to {t['battery_lowest_percent']}% (now it gets to {b['battery_lowest_percent']}%).")
    if t["solar_kwh"] < b["solar_kwh"] * 0.95:
        out.append(f"The home would get {t['solar_kwh']:.0f} kWh from solar instead of {b['solar_kwh']:.0f} kWh "
                   f"({100 * (1 - t['solar_kwh'] / max(b['solar_kwh'], 0.1)):.0f}% less).")
    if t["battery_ageing_speed"] > b["battery_ageing_speed"] * 1.1:
        out.append(f"The battery would age {t['battery_ageing_speed']:.1f}× as fast as at 25°C "
                   f"(now {b['battery_ageing_speed']:.1f}×), peaking at {t['battery_hottest_c']:.0f}°C.")
    if t["blackout_hours"] > b["blackout_hours"] + 2:
        out.append("Worth suggesting: more battery, fewer heavy loads at night, or more panels.")
    elif t["battery_hottest_c"] >= 40:
        out.append("Worth suggesting: move the battery somewhere cooler or add ventilation.")
    return out
