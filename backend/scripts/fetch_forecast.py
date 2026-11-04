"""Fetch the Open-Meteo forecast for every site's weather point and save it.

Usage (from backend/):
    python -m scripts.fetch_forecast
Later (Phase 3) the backend runs this automatically every evening.
"""

import logging

from app.weather import open_meteo
from app.weather.points import site_weather_points
from app.weather.store import save_forecast

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("fetch_forecast")


def main() -> None:
    for p in site_weather_points():
        df = open_meteo.fetch_forecast(p.latitude, p.longitude, days=3)
        n = save_forecast(p, df)
        log.info("%s: %d hours saved, peak sunlight %.0f W/m2", p, n, df["ghi_wm2"].max())


if __name__ == "__main__":
    main()
