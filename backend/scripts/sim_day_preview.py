"""Preview one simulated day of house usage and NEPA supply for a site.

Temperatures come from the local NASA POWER files for dates they cover (no internet needed for
weather), otherwise from Open-Meteo.

Usage (from backend/):
    python -m scripts.sim_day_preview --site lagos-001 --date 2026-08-14
    python -m scripts.sim_day_preview --site ph-001 --date 2026-08-14
"""

import argparse

import numpy as np
import pandas as pd

from app.config import REPO_ROOT
from app.simulator.grid import simulate_grid
from app.simulator.load import simulate_load
from app.simulator.site import SiteConfig, load_site
from app.weather import open_meteo
from app.weather.points import weather_point

NASA_DIR = REPO_ROOT / "ml" / "data" / "raw" / "nasa_power"


def day_temperatures(site: SiteConfig, day: pd.Timestamp) -> np.ndarray:
    """288 five-minute outdoor temperatures (C) for the local day."""
    idx = pd.date_range(day, periods=288, freq="5min")
    p = weather_point(site.latitude, site.longitude)
    path = NASA_DIR / f"lat{p.latitude}_lon{p.longitude}.parquet"
    hourly = None
    if path.exists():
        temps = pd.read_parquet(path)["temp_c"].tz_convert(site.timezone)
        window = temps.loc[day - pd.Timedelta(hours=2): day + pd.Timedelta(hours=26)]
        if window.notna().sum() >= 24:
            hourly = window
    if hourly is None:
        past = (pd.Timestamp.now(tz=site.timezone) - day).days + 2
        hourly = open_meteo.fetch_hourly(site.latitude, site.longitude, past_days=max(past, 1),
                                         forecast_days=2)["temp_c"].tz_convert(site.timezone)
    return hourly.reindex(hourly.index.union(idx)).interpolate("time").reindex(idx).to_numpy()


def preview(site: SiteConfig, day: pd.Timestamp, temps: np.ndarray) -> None:
    load = simulate_load(site, day, temps)
    grid, _ = simulate_grid(site, day)

    kwh = load["load_w"].sum() * (5 / 60) / 1000
    print(f"\n{site.code} ({site.load_profile}, band {site.tariff_band}) on {day:%A %d %B %Y}")
    print(f"Temperature {np.nanmin(temps):.0f}-{np.nanmax(temps):.0f} C | usage {kwh:.1f} kWh | "
          f"peak {load['load_w'].max() / 1000:.2f} kW at {load['load_w'].idxmax():%H:%M} | "
          f"NEPA on {grid['grid_on'].sum() / 12:.1f} h")

    hourly = pd.DataFrame({
        "usage_kw": (load["load_w"].resample("1h").mean() / 1000).round(2),
        "nepa_on_min": (grid["grid_on"].resample("1h").sum() * 5).astype(int),
    })
    hourly.index = hourly.index.strftime("%H:00")
    print("\nHour by hour:")
    print(hourly.to_string())

    # Outage spells
    off = ~grid["grid_on"]
    spells = (off != off.shift()).cumsum()[off]
    print("\nNEPA outages:")
    for _, s in grid[off].groupby(spells):
        end = s.index[-1] + pd.Timedelta(minutes=5)
        print(f"  {s.index[0]:%H:%M} - {end:%H:%M}  ({len(s) * 5 / 60:.1f} h)")

    # Which appliances used the most energy
    per_app = (load.drop(columns="load_w").sum() * (5 / 60) / 1000).sort_values(ascending=False)
    print("\nEnergy by appliance (kWh):")
    print(per_app[per_app > 0.05].round(2).to_string())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", default="lagos-001")
    parser.add_argument("--date", default="2026-08-14", help="local date, YYYY-MM-DD")
    args = parser.parse_args()

    site = load_site(args.site)
    day = pd.Timestamp(args.date, tz=site.timezone)
    preview(site, day, day_temperatures(site, day))


if __name__ == "__main__":
    main()
