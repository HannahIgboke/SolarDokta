"""NASA POWER hourly history: sunlight (GHI) and air temperature, in UTC.

API docs: https://power.larc.nasa.gov/api/pages/  (free, no API key)
"""

import logging
from datetime import date

import httpx
import pandas as pd
from tenacity import retry, stop_after_attempt, wait_exponential

log = logging.getLogger(__name__)

BASE_URL = "https://power.larc.nasa.gov/api/temporal/hourly/point"
PARAMS = {"ALLSKY_SFC_SW_DWN": "ghi_wm2", "T2M": "temp_c"}
DEFAULT_FILL = -999.0


@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=2, max=30), reraise=True)
def _get(params: dict) -> dict:
    resp = httpx.get(BASE_URL, params=params, timeout=120)
    resp.raise_for_status()
    return resp.json()


def parse_response(payload: dict) -> pd.DataFrame:
    """Turn a NASA POWER JSON payload into a DataFrame indexed by UTC hour."""
    try:
        series = payload["properties"]["parameter"]
    except KeyError as exc:
        raise ValueError(f"Unexpected NASA POWER response: {list(payload)[:5]}") from exc

    fill = payload.get("header", {}).get("fill_value", DEFAULT_FILL)
    units = {k: v.get("units") for k, v in payload.get("parameters", {}).items()}
    if units:
        log.info("NASA POWER units: %s", units)

    frames = {}
    for api_name, col in PARAMS.items():
        raw = series.get(api_name, {})
        s = pd.Series(raw, dtype="float64")
        s.index = pd.to_datetime(s.index, format="%Y%m%d%H", utc=True)
        frames[col] = s.where(s != fill)   # fill value -> NaN
    df = pd.DataFrame(frames).sort_index()
    df.index.name = "ts"
    # Sunlight can't be negative; tiny negatives are model noise.
    df["ghi_wm2"] = df["ghi_wm2"].clip(lower=0)
    return df


def fetch_year(latitude: float, longitude: float, year: int) -> pd.DataFrame:
    """One calendar year of hourly data (shorter if the year is not finished)."""
    end = min(date(year, 12, 31), date.today())
    params = {
        "parameters": ",".join(PARAMS),
        "community": "RE",
        "latitude": latitude,
        "longitude": longitude,
        "start": f"{year}0101",
        "end": end.strftime("%Y%m%d"),
        "format": "JSON",
        "time-standard": "UTC",
    }
    return parse_response(_get(params))


def fetch_range(latitude: float, longitude: float, start_year: int, end_year: int) -> pd.DataFrame:
    parts = []
    for year in range(start_year, end_year + 1):
        log.info("NASA POWER %s,%s %s", latitude, longitude, year)
        parts.append(fetch_year(latitude, longitude, year))
    df = pd.concat(parts)
    return df[~df.index.duplicated(keep="last")]
