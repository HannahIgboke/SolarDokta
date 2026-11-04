"""Sanity-check the NASA POWER history before using it."""

from pathlib import Path

import pandas as pd

DATA = Path(__file__).resolve().parents[1] / "data" / "raw" / "nasa_power"

for path in sorted(DATA.glob("*.parquet")):
    df = pd.read_parquet(path)
    local = df.tz_convert("Africa/Lagos")
    ghi = local["ghi_wm2"]
    print(f"\n=== {path.stem} ===")

    # 1. Where are the missing hours?
    missing = ghi.isna()
    print("Missing hours by year:")
    print(missing.groupby(local.index.year).sum().loc[lambda s: s > 0].to_string())
    print("Last hour with sunlight data:", ghi.last_valid_index())
    print("Missing hours BEFORE that point:", int(missing[: ghi.last_valid_index()].sum()))

    # 2. Daily sunlight energy (kWh per m2 per day). Southern Nigeria is roughly 4-5.5.
    daily = ghi.resample("D").sum(min_count=20) / 1000
    print("Average daily sunlight by month (kWh/m2/day):")
    print(daily.groupby(daily.index.month).mean().round(2).to_string())

    # 3. El Nino check: average temperature per year (2015-16 was a super El Nino)
    print("Average temperature by year (C):")
    print(local["temp_c"].groupby(local.index.year).mean().round(2).to_string())