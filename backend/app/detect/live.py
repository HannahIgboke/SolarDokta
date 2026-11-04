"""The rule detectors running for real: every hour, check each site and keep `findings` current.

For each site:
1. Load the last 14 days of 5-minute telemetry, the weather, and the physics "expected solar".
2. Save the long-term health numbers for each finished day (health_daily, battery_estimates).
   Raw telemetry is deleted after 30 days, but these small numbers are kept for good.
3. Run the detectors:
   - on the 14 days of raw data: dead string, weak string, shading, hot battery, overload,
     battery ran empty
   - on the stored long-term numbers: dust (needs months of clean-level history) and battery
     fade (needs a 4-month trend)
4. Bring the findings up to date: open new problems, resolve the ones that have cleared, and
   record one-off events. Phase 6C turns new findings into WhatsApp alerts.
Safe to run again: nothing is saved twice.
"""

import logging

import pandas as pd

from app.detect.battery import battery_fade_from_estimates, capacity_estimates
from app.detect.expected import expected_power
from app.detect.rules import (
    Alarm,
    battery_ran_out,
    daily_batt_heat,
    daily_performance,
    dead_string,
    hot_battery,
    overload,
    shading,
    soiling_from_daily,
    weak_string,
)
from app.findings import open_finding, open_findings, record_event, resolve_finding
from app.simulator import store
from app.simulator.faults import _iso
from app.simulator.site import SiteConfig
from app.simulator.weather_source import hourly_weather

log = logging.getLogger(__name__)

WINDOW = pd.Timedelta(days=14)       # raw data the fast detectors look at
LONG = pd.Timedelta(days=180)        # stored health history for dust and battery fade
STEP = pd.Timedelta(minutes=5)

# How urgent each problem is. "critical" = tell the customer now; "warning" = tell them today;
# "info" = mention it / show on the dashboard.
SEVERITY = {
    "string_failure": "critical",
    "battery_ran_out": "warning",
    "overload": "warning",
    "underrated_panel": "warning",
    "soiling": "warning",
    "hot_battery_room": "warning",
    "battery_fade": "warning",
    "shading": "info",
    "heatwave": "info",          # from the saved weather forecast (tomorrow very hot)
}
EVENT_KINDS = {"overload", "battery_ran_out"}          # one finding per occurrence
CONDITION_KINDS = set(SEVERITY) - EVENT_KINDS          # one open finding while it lasts
FAST_DETECTORS = [dead_string, weak_string, shading, hot_battery, overload, battery_ran_out]


def heatwave(site: SiteConfig, now: pd.Timestamp, client=None) -> list[Alarm]:
    """A heads-up when the saved forecast says tomorrow will be very hot (El Niño season)."""
    from app.agent.tools import HEATWAVE_C, ToolContext, saved_forecast

    fc, _ = saved_forecast(ToolContext(site, client=client, now=now))
    if fc is None:
        return []
    temps = fc["temp_c"].copy()
    temps.index = temps.index.tz_convert(site.timezone) - pd.Timedelta(hours=1)   # 'right' labels
    tomorrow = now.normalize() + pd.Timedelta(days=1)
    day = temps.loc[tomorrow:tomorrow + pd.Timedelta(hours=23)]
    if len(day) < 12 or day.max() < HEATWAVE_C:
        return []
    return [Alarm("heatwave", tomorrow, now, None, target=f"{tomorrow:%Y-%m-%d}",
                  details={"high_c": round(float(day.max()))})]


def sync_findings(site: SiteConfig, alarms: list[Alarm], now: pd.Timestamp,
                  window_start: pd.Timestamp, client=None) -> dict:
    created, resolved, active = [], [], set()
    for a in alarms:
        details = {**a.details, "target": a.target, "raised_at": _iso(a.raised_at)}
        if a.kind in EVENT_KINDS:
            if a.start <= window_start:               # cut off by the window: saved on an earlier run
                continue
            key = f"{a.kind}:{a.target}:{a.start:%Y%m%dT%H%M}"
            if record_event(site, a.kind, SEVERITY[a.kind], key, a.start, a.end, details, client):
                created.append(key)
        elif a.end is None:                           # a condition that is still going on
            key = f"{a.kind}:{a.target}"
            active.add(key)
            if open_finding(site, a.kind, SEVERITY[a.kind], key, a.start, None, details, client=client):
                created.append(key)
    for f in open_findings(site, CONDITION_KINDS, client):
        if f["dedupe_key"] not in active:             # the detector no longer sees the problem
            resolve_finding(f["id"], now, client)
            resolved.append(f["dedupe_key"])
    return {"new": created, "resolved": resolved}


def check_site(site: SiteConfig, now: pd.Timestamp | None = None, client=None) -> dict:
    now = (now or pd.Timestamp.now(tz="UTC")).tz_convert(site.timezone)
    tel = store.load_telemetry(site, now - WINDOW, now + STEP, client)
    if len(tel) < 288:
        return {"site": site.code, "skipped": "less than a day of telemetry"}
    hourly, label = hourly_weather(site, tel.index[0], tel.index[-1] + STEP)
    exp = expected_power(site, hourly, label, tel.index)

    # 1. long-term health numbers, for finished days only
    today = now.normalize()
    daily = daily_performance(site, tel, exp)
    daily["batt_heat_c"] = daily_batt_heat(tel, exp)
    complete = tel["batt_v"].resample("1D").count().reindex(daily.index) == 288
    store.save_health(site, daily[complete & (daily.index < today)], client)
    est = capacity_estimates(site, tel)
    est = est[est.index < tel.index[-1] - pd.Timedelta(minutes=30)]   # skip a discharge still going
    store.save_battery_estimates(site, est, client)

    # 2. detectors
    alarms = []
    for detector in FAST_DETECTORS:
        alarms += detector(site, tel, exp)
    alarms += soiling_from_daily(store.load_health(site, today - LONG, client))
    alarms += battery_fade_from_estimates(store.load_battery_estimates(site, now - LONG, client), now)
    alarms += heatwave(site, now, client)

    # 3. findings
    result = sync_findings(site, alarms, now, tel.index[0], client)
    return {"site": site.code, **result}


def run(sites: list[SiteConfig], now: pd.Timestamp | None = None, client=None) -> list[dict]:
    results = []
    for site in sites:
        try:
            results.append(check_site(site, now, client))
        except Exception as exc:
            log.exception("Detector check failed for %s", site.code)  # one bad site must not stop the rest
            results.append({"site": site.code, "error": repr(exc)})
    return results
