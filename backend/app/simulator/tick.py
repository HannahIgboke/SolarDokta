"""The 5-minute tick: bring every simulated site up to date.

For each site:
1. Read where its simulation stopped (simulator_state.last_ts and the saved state).
2. Simulate every 5-minute step from then until now (fills any gap, e.g. after downtime).
3. Save the new telemetry rows, then the new state.

Safe to run twice: telemetry is upserted, so a repeated tick rewrites the same rows.
Phase 3 calls run_tick() from FastAPI's /tick endpoint, triggered by Supabase Cron.
"""

import logging
from dataclasses import dataclass

import pandas as pd

from app.db import get_client
from app.simulator import grid, store
from app.simulator.engine import STEP, SimState, simulate_window
from app.simulator.site import SiteConfig
from app.simulator.weather_source import hourly_weather

log = logging.getLogger(__name__)

MAX_CATCH_UP = pd.Timedelta(days=14)     # longer gaps are filled over several ticks


@dataclass
class TickResult:
    site: str
    rows: int
    after: pd.Timestamp                  # last step before this tick
    last_ts: pd.Timestamp                # last step after this tick
    faults: list[str]


def tick_site(site: SiteConfig, now: pd.Timestamp | None = None, client=None) -> TickResult:
    client = client or get_client()
    now = (now or pd.Timestamp.now(tz="UTC")).tz_convert(site.timezone).floor("5min")
    state, last_ts = store.load_state(site, client)
    if last_ts is None:                  # never simulated: start at midnight today
        state, last_ts = SimState(), now.normalize() - STEP
    if last_ts >= now:
        return TickResult(site.code, 0, last_ts, last_ts, [])

    until = min(now, last_ts + MAX_CATCH_UP)
    first_day = (last_ts + STEP).normalize()
    hourly, label = hourly_weather(site, first_day, until.normalize() + pd.Timedelta(days=1))
    faults = store.load_faults(site, first_day, until + STEP, client)

    out, new_state = simulate_window(site, last_ts, until, hourly, label, state, faults)
    if len(out):
        store.save_telemetry(site, out, client)
    store.save_state(site, new_state, until, client)
    codes = sorted({c for c in out["fault_code"] if c}) if len(out) else []
    return TickResult(site.code, len(out), last_ts, until, codes)


def run_tick(sites: list[SiteConfig], now: pd.Timestamp | None = None, client=None) -> list[TickResult]:
    """Tick every site, then refresh the hourly/daily summaries once for all of them."""
    client = client or get_client()
    grid.set_conditions(store.load_grid_conditions(client))   # latest NEPA conditions per city
    results = []
    for site in sites:
        try:
            results.append(tick_site(site, now, client))
        except Exception:
            log.exception("Tick failed for %s", site.code)   # one bad site must not stop the rest
    changed = [r for r in results if r.rows]
    if changed:
        store.refresh_summaries(min(r.after for r in changed) + STEP,
                                max(r.last_ts for r in changed), sites[0].timezone, client)
    return results
