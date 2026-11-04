"""Re-run the virtual inverter from a date until now, e.g. after changing the grid conditions.

Only the recent days are rebuilt (much faster than generate_history). For each site:
- delete its telemetry, summaries, health numbers and detector findings from that date on
- simulate again from that date (keeping the planned/injected faults and battery health)
- save everything, and move the 5-minute tick's saved state to the new "now"
Then run the detectors once so findings match the new data.

Usage (from backend/):
    python -m scripts.resimulate --since 2026-10-01
    python -m scripts.resimulate --since 2026-10-01 --sites lagos-001 ph-001
"""

import argparse
import time

import pandas as pd

from app.db import get_client
from app.detect import live
from app.detect.battery import capacity_estimates
from app.detect.expected import expected_power
from app.detect.rules import daily_batt_heat, daily_performance
from app.jobs import active_sites
from app.simulator import grid, store
from app.simulator.battery import BatteryState
from app.simulator.engine import STEP, TELEMETRY_COLUMNS, SimState, simulate_window
from app.simulator.faults import _iso
from app.simulator.weather_source import hourly_weather


def clear_from(site, since: pd.Timestamp, client) -> None:
    iso, day = _iso(since), since.strftime("%Y-%m-%d")
    for table, col, val in (("telemetry", "ts", iso), ("telemetry_hourly", "hour_ts", iso),
                            ("telemetry_daily", "day", day), ("health_daily", "day", day),
                            ("battery_estimates", "ts", iso), ("findings", "ts_start", iso)):
        client.table(table).delete().eq("site_id", site.id).gte(col, val).execute()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--since", required=True, help="first local date to rebuild, e.g. 2026-10-01")
    p.add_argument("--sites", nargs="+", help="site codes (default: all active sites)")
    args = p.parse_args()
    client = get_client()
    grid.set_conditions(store.load_grid_conditions(client))
    sites = [s for s in active_sites(client) if not args.sites or s.code in args.sites]

    for site in sites:
        t0 = time.time()
        since = pd.Timestamp(args.since, tz=site.timezone)
        now = pd.Timestamp.now(tz=site.timezone).floor("5min")
        old_state, _ = store.load_state(site, client)
        soh = old_state.battery.soh if old_state else 1.0
        start = SimState(BatteryState(soc=0.8, soh=soh))
        hourly, label = hourly_weather(site, since, now.normalize() + pd.Timedelta(days=1))
        faults = store.load_faults(site, since, now + STEP, client)

        out, state = simulate_window(site, since - STEP, now, hourly, label, start, faults)
        clear_from(site, since, client)
        store.save_telemetry(site, out, client)
        store.save_summaries(site, out, client)
        tel = out[TELEMETRY_COLUMNS]
        exp = expected_power(site, hourly, label, out.index)
        health = daily_performance(site, tel, exp)
        health["batt_heat_c"] = daily_batt_heat(tel, exp)
        store.save_health(site, health.iloc[:-1], client)
        store.save_battery_estimates(site, capacity_estimates(site, tel), client)
        store.save_state(site, state, now, client)
        light = out["grid_v"].gt(100).resample("1D").mean() * 24
        print(f"{site.code}: {len(out):,} rows from {since:%d %b}; light per day since then: "
              f"{light.mean():.1f} h on average (min {light.min():.1f}, max {light.max():.1f}); "
              f"{time.time() - t0:.0f}s")

    print("\nRunning the detectors on the new data...")
    for r in live.run(sites, client=client):
        print(" ", r)


if __name__ == "__main__":
    main()
