"""Run the full virtual inverter for a site over several days and print what happened.

Weather comes from your local NASA files for dates they cover (no internet needed for weather),
otherwise from Open-Meteo. The battery and NEPA carry over from one day to the next.

Usage (from backend/):
    python -m scripts.sim_days --site lagos-001 --start 2026-08-10 --days 7
    python -m scripts.sim_days --site ph-001 --start 2026-08-10 --days 7 --show-day 2026-08-12
    python -m scripts.sim_days --site lagos-001 --start 2026-08-10 --days 7 --mode SBU
"""

import argparse
from dataclasses import replace

import pandas as pd

from app.simulator.engine import simulate_day, summarise
from app.simulator.site import load_site
from app.simulator.weather_source import hourly_weather


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", default="lagos-001")
    parser.add_argument("--start", default="2026-08-10", help="first local date, YYYY-MM-DD")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--show-day", help="print the hour-by-hour detail for this date")
    parser.add_argument("--mode", choices=["SUB", "SBU"], help="try a different inverter mode")
    args = parser.parse_args()

    site = load_site(args.site)
    if args.mode:
        site = replace(site, inverter_mode=args.mode)
    days = pd.date_range(args.start, periods=args.days, freq="D", tz=site.timezone)
    hourly, label = hourly_weather(site, days[0].tz_convert("UTC"),
                                   (days[-1] + pd.Timedelta(days=1)).tz_convert("UTC"))

    state, summaries, frames = None, [], {}
    for day in days:
        out, state = simulate_day(site, day, hourly, label, state)
        frames[day.strftime("%Y-%m-%d")] = out
        summaries.append({"date": day.strftime("%a %d %b"), **summarise(out, site)})

    print(f"\n{site.code}: {site.pv1_kwp}+{site.pv2_kwp} kWp, {site.inverter_kw} kW inverter, "
          f"{site.battery_kwh} kWh {site.battery_chemistry}, band {site.tariff_band}, "
          f"mode {site.inverter_mode}, {site.load_profile}")
    table = pd.DataFrame(summaries).set_index("date")
    show = table[["solar_available_kwh", "solar_used_kwh", "solar_curtailed_kwh", "house_kwh",
                  "grid_import_kwh", "soc_min", "batt_temp_max", "blackout_minutes"]].copy()
    show.columns = ["solar_avail", "solar_used", "wasted", "house", "nepa_kwh", "soc_min",
                    "batt_max_C", "blackout_min"]
    print("\nDaily totals (kWh unless marked):")
    print(show.round(2).to_string())
    faults = sorted({f for fs in table["faults"] for f in fs})
    print(f"\nFaults: {', '.join(faults) if faults else 'none'}")
    print(f"Battery health: {table['soh_end'].iloc[0] * 100:.3f}% -> {table['soh_end'].iloc[-1] * 100:.3f}%")

    day_key = args.show_day or days[min(2, len(days) - 1)].strftime("%Y-%m-%d")
    out = frames[day_key]
    hourly_view = pd.DataFrame({
        "solar_kw": (out["pv1_w"] + out["pv2_w"]).resample("1h").mean() / 1000,
        "house_kw": out["load_w"].resample("1h").mean() / 1000,
        "nepa_kw": out["grid_w"].resample("1h").mean() / 1000,
        "battery_kw": out["batt_w"].resample("1h").mean() / 1000,
        "soc_%": out["batt_soc"].resample("1h").last() * 100,
        "nepa_on_min": (out["grid_v"] > 0).resample("1h").sum() * 5,
    }).round(2)
    hourly_view.index = hourly_view.index.strftime("%H:00")
    print(f"\nHour by hour on {day_key} (battery_kw: + charging, - discharging):")
    print(hourly_view.to_string())


if __name__ == "__main__":
    main()
