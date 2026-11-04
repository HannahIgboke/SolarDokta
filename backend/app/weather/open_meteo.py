"""Open-Meteo hourly weather (sunlight, temperature, cloud cover), UTC.

Two services, same format:
- forecast API: the last few weeks and the next days.  https://open-meteo.com/en/docs
- archive API (ERA5 reanalysis): any past date up to about 5 days ago.
  https://open-meteo.com/en/docs/historical-weather-api
Both are free for non-commercial use, no API key.
Note: Open-Meteo hourly values describe the hour BEFORE their timestamp ("right" labelled).
"""

import httpx
import pandas as pd
from tenacity import retry, stop_after_attempt, wait_exponential

BASE_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
HISTORICAL_FORECAST_URL = "https://historical-forecast-api.open-meteo.com/v1/forecast"
HOURLY = {"shortwave_radiation": "ghi_wm2", "temperature_2m": "temp_c", "cloud_cover": "cloud_cover_pct"}
LABEL = "right"


@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=2, max=30), reraise=True)
def _get(params: dict, url: str = BASE_URL) -> dict:
    resp = httpx.get(url, params=params, timeout=60)
    resp.raise_for_status()
    return resp.json()


def parse_response(payload: dict) -> pd.DataFrame:
    try:
        hourly = payload["hourly"]
        times = hourly["time"]
    except KeyError as exc:
        raise ValueError(f"Unexpected Open-Meteo response: {list(payload)[:5]}") from exc

    df = pd.DataFrame({col: hourly.get(api_name) for api_name, col in HOURLY.items()})
    # We request timezone=UTC, so timestamps arrive without an offset; mark them as UTC.
    df.index = pd.to_datetime(times, utc=True)
    df.index.name = "ts"
    return df.astype("float64")


def fetch_hourly(latitude: float, longitude: float, past_days: int = 0, forecast_days: int = 3) -> pd.DataFrame:
    """Hourly weather from `past_days` ago up to `forecast_days` ahead (past_days max 92)."""
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": ",".join(HOURLY),
        "past_days": past_days,
        "forecast_days": forecast_days,
        "timezone": "UTC",
    }
    return parse_response(_get(params))


def fetch_forecast(latitude: float, longitude: float, days: int = 3) -> pd.DataFrame:
    return fetch_hourly(latitude, longitude, past_days=0, forecast_days=days)


def fetch_archive(latitude: float, longitude: float, start_date: str, end_date: str) -> pd.DataFrame:
    """Hourly past weather between two dates (YYYY-MM-DD, inclusive).

    Tries the reanalysis archive first; if that server is down, falls back to Open-Meteo's
    stored past forecasts (a separate server, also free). The newest ~5 days may be empty (NaN).
    """
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": ",".join(HOURLY),
        "start_date": start_date,
        "end_date": end_date,
        "timezone": "UTC",
    }
    try:
        return parse_response(_get(params, url=ARCHIVE_URL))
    except httpx.HTTPError as first_error:
        try:
            return parse_response(_get(params, url=HISTORICAL_FORECAST_URL))
        except httpx.HTTPError:
            raise RuntimeError(
                "Both Open-Meteo past-weather servers failed (archive said: "
                f"{first_error}). Try again in a few minutes, or on another network.") from first_error
