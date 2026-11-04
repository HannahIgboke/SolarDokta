"""Download NASA POWER hourly history for every site's weather point.

- Full history (default 2001 to now) is saved as Parquet in ml/data/raw/nasa_power/ for ML work.
- Only recent years (default last 2) go into Supabase, to stay within the free 500 MB.

Usage (from backend/):
    python -m scripts.fetch_weather_history
    python -m scripts.fetch_weather_history --start-year 2014 --db-years 1
"""

import argparse
import logging
from datetime import date

from app.config import REPO_ROOT
from app.weather import nasa_power
from app.weather.points import site_weather_points
from app.weather.store import save_history

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)   # hide one log line per HTTP request
log = logging.getLogger("fetch_weather_history")

OUT_DIR = REPO_ROOT / "ml" / "data" / "raw" / "nasa_power"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-year", type=int, default=2001)
    parser.add_argument("--end-year", type=int, default=date.today().year)
    parser.add_argument("--db-years", type=int, default=2, help="recent years to load into Supabase")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    db_from_year = args.end_year - args.db_years + 1

    points = site_weather_points()
    log.info("Weather points: %s", points)

    for p in points:
        df = nasa_power.fetch_range(p.latitude, p.longitude, args.start_year, args.end_year)
        path = OUT_DIR / f"lat{p.latitude}_lon{p.longitude}.parquet"
        df.to_parquet(path)
        log.info("Saved %d rows to %s (%.1f%% missing GHI)",
                 len(df), path.name, df["ghi_wm2"].isna().mean() * 100)

        recent = df[df.index.year >= db_from_year]
        n = save_history(p, recent)
        log.info("Upserted %d rows into weather_history for %s", n, p)


if __name__ == "__main__":
    main()
