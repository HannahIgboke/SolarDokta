"""Generate months of virtual-inverter history for each site, with faults, up to right now.

Where the data goes:
- ml/data/sim/<site>.parquet  every 5-minute step, plus diagnostics and the fault label for
                              each step. This is the ML training/evaluation set (stays local).
- Supabase:
    injected_faults            the answer key (every planned fault)
    health_daily, battery_estimates  long-term health numbers (for the dust and battery checks)
    telemetry_hourly / _daily  summaries for the whole period (small)
    telemetry                  raw 5-minute rows for the last --raw-days only (free-tier space)
    simulator_state            where each site stopped, so the 5-minute tick carries on from there

Usage (from backend/):
    python -m scripts.generate_history                        # 4 sites from 2025-01-01
    python -m scripts.generate_history --sites lagos-001 --start 2026-06-01 --no-db

Re-running replaces each site's simulated data in Supabase (old telemetry, summaries, state
and injected faults for that site are deleted first), so you never get duplicates.
"""

import argparse
import time

import pandas as pd

from app.config import REPO_ROOT
from app.db import get_client
from app.detect.battery import capacity_estimates
from app.detect.expected import expected_power
from app.detect.rules import daily_batt_heat, daily_performance
from app.simulator import grid, store
from app.simulator.engine import STEP, TELEMETRY_COLUMNS, simulate_window
from app.simulator.faults import plan_faults
from app.simulator.site import load_site
from app.simulator.weather_source import hourly_weather

OUT_DIR = REPO_ROOT / "ml" / "data" / "sim"
DEFAULT_SITES = ["lagos-001", "lagos-002", "lagos-003", "ph-001"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sites", nargs="+", default=DEFAULT_SITES)
    parser.add_argument("--start", default="2025-01-01", help="first local date")
    parser.add_argument("--raw-days", type=int, default=30, help="days of raw rows to put in Supabase")
    parser.add_argument("--seed", type=int, default=0, help="change to get a different fault plan")
    parser.add_argument("--no-db", action="store_true", help="only write the local parquet files")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    client = None if args.no_db else get_client()
    grid.set_conditions(store.load_grid_conditions(client) if client else None)

    for code in args.sites:
        t0 = time.time()
        site = load_site(code)
        start = pd.Timestamp(args.start, tz=site.timezone)
        end = pd.Timestamp.now(tz=site.timezone).floor("5min")
        print(f"\n== {code}: {start:%Y-%m-%d} -> {end:%Y-%m-%d %H:%M}")

        faults = plan_faults(site, start, end, seed=args.seed)
        hourly, label = hourly_weather(site, start, end.normalize() + pd.Timedelta(days=1))

        # Simulate month by month (same result as one long run, but shows progress).
        state, parts, after = None, [], start - STEP
        months = pd.date_range(start, end, freq="MS")
        for month_end in [*(m - STEP for m in months if m > start), end]:
            out, state = simulate_window(site, after, month_end, hourly, label, state, faults)
            parts.append(out)
            after = month_end
            print(f"  simulated to {month_end:%Y-%m-%d}  battery health {state.battery.soh:.2%}",
                  end="\r")
        out = pd.concat(parts)
        print()

        path = OUT_DIR / f"{code}.parquet"
        out.to_parquet(path)
        labelled = out["fault_label"].notna().mean()
        print(f"  {len(out):,} rows -> ml/data/sim/{path.name} "
              f"({labelled:.0%} of steps have an injected fault)")
        print("  faults planned: " + ", ".join(
            f"{k} x{n}" for k, n in pd.Series([f.kind for f in faults]).value_counts().items()))
        codes = out["fault_code"].value_counts()
        print("  inverter fault codes: " + (", ".join(f"{k} x{v}" for k, v in codes.items()) or "none"))

        if client is not None:
            store.clear_site(site, client)
            store.save_faults(site, faults, client)
            nh, nd = store.save_summaries(site, out, client)
            raw = out[out.index > end - pd.Timedelta(days=args.raw_days)]
            nr = store.save_telemetry(site, raw, client)
            store.save_state(site, state, end, client)
            # long-term health numbers, so dust and battery-fade checks have history from day one
            tel = out[TELEMETRY_COLUMNS]
            exp = expected_power(site, hourly, label, out.index)
            health = daily_performance(site, tel, exp)
            health["batt_heat_c"] = daily_batt_heat(tel, exp)
            store.save_health(site, health.iloc[:-1], client)          # last day is unfinished
            store.save_battery_estimates(site, capacity_estimates(site, tel), client)
            print(f"  Supabase: {len(faults)} faults, {nh:,} hourly, {nd} daily, "
                  f"{nr:,} raw rows, state saved")
        print(f"  done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
