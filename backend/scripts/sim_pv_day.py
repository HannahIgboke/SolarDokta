"""Simulate one day of solar output for a site and compare with a real reading.

Uses Open-Meteo's recent weather (last 92 days available), so it works for any recent date.

Usage (from backend/):
    python -m scripts.sim_pv_day --site lagos-001 --date 2026-10-27 --at 13:05
    python -m scripts.sim_pv_day --site lagos-001 --date 2026-10-27 --at 13:05 --pv2-soiling 0.6
"""

import argparse

import pandas as pd

from app.simulator.pv import day_seed, pv_power, spread_hourly_ghi
from app.simulator.site import load_site
from app.weather import open_meteo


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", default="lagos-001")
    parser.add_argument("--date", default="2026-10-27", help="local date, YYYY-MM-DD")
    parser.add_argument("--at", default="13:05", help="local time to compare, HH:MM")
    parser.add_argument("--pv2-soiling", type=float, default=0.0,
                        help="test: fraction of PV2 output lost (0.6 = 60%%)")
    args = parser.parse_args()

    site = load_site(args.site)
    day_local = pd.Timestamp(args.date, tz=site.timezone)
    start, end = day_local.tz_convert("UTC"), (day_local + pd.Timedelta(days=1)).tz_convert("UTC")

    past_days = (pd.Timestamp.now(tz="UTC") - start).days + 2
    if past_days > 92:
        raise SystemExit("Open-Meteo only keeps the last 92 days; pick a more recent date.")
    hourly = open_meteo.fetch_hourly(site.latitude, site.longitude, past_days=past_days, forecast_days=1)

    w5 = spread_hourly_ghi(hourly, site, start, end, label=open_meteo.LABEL, seed=day_seed(site.code, day_local))
    pv = pv_power(w5, site, soiling={"pv2": args.pv2_soiling})
    local = pv.tz_convert(site.timezone)

    # Summary of the day
    total_w = local["pv1_w"] + local["pv2_w"]
    energy_kwh = total_w.sum() * (5 / 60) / 1000
    print(f"\n{site.code}: PV1 {site.pv1_kwp} kWp + PV2 {site.pv2_kwp} kWp, tilt {site.tilt_deg}, "
          f"azimuth {site.azimuth_deg}")
    print(f"{args.date}: simulated energy {energy_kwh:.1f} kWh, peak {total_w.max() / 1000:.2f} kW "
          f"at {total_w.idxmax():%H:%M}")

    # Hourly profile
    hourly_kw = (local[["pv1_w", "pv2_w"]].resample("1h").mean() / 1000).round(2)
    hourly_kw = hourly_kw[(hourly_kw.sum(axis=1) > 0.01)]
    hourly_kw.index = hourly_kw.index.strftime("%H:00")
    print("\nAverage kW per hour:")
    print(hourly_kw.to_string())

    # Compare with the reading from the inverter screen
    t = pd.Timestamp(f"{args.date} {args.at}", tz=site.timezone)
    row = local.loc[local.index.asof(t)]
    print(f"\nAt {args.at}: PV1 {row.pv1_w:,.0f} W ({row.pv1_v:.0f} V), PV2 {row.pv2_w:,.0f} W "
          f"({row.pv2_v:.0f} V), total {(row.pv1_w + row.pv2_w) / 1000:.2f} kW, "
          f"panel temp {row.t_cell_c:.0f} C")


if __name__ == "__main__":
    main()
