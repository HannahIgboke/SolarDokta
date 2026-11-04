"""Save weather DataFrames into Supabase."""

import math

import pandas as pd

from app.db import upsert_rows
from app.weather.points import WeatherPoint


def _clean(x):
    """NaN -> None (JSON null); numpy numbers -> plain Python floats."""
    if x is None:
        return None
    x = float(x)
    return None if math.isnan(x) else round(x, 2)


def history_rows(point: WeatherPoint, df: pd.DataFrame):
    for ts, r in df.iterrows():
        yield {
            "latitude": point.latitude,
            "longitude": point.longitude,
            "ts": ts.isoformat(),
            "ghi_wm2": _clean(r["ghi_wm2"]),
            "temp_c": _clean(r["temp_c"]),
            "source": "nasa_power",
        }


def forecast_rows(point: WeatherPoint, df: pd.DataFrame):
    fetched_at = pd.Timestamp.now(tz="UTC").isoformat()
    for ts, r in df.iterrows():
        yield {
            "latitude": point.latitude,
            "longitude": point.longitude,
            "ts": ts.isoformat(),
            "ghi_wm2": _clean(r["ghi_wm2"]),
            "temp_c": _clean(r["temp_c"]),
            "cloud_cover_pct": _clean(r["cloud_cover_pct"]),
            "fetched_at": fetched_at,
            "source": "open_meteo",
        }


def save_history(point: WeatherPoint, df: pd.DataFrame, client=None) -> int:
    return upsert_rows("weather_history", history_rows(point, df),
                       on_conflict="latitude,longitude,ts", client=client)


def save_forecast(point: WeatherPoint, df: pd.DataFrame, client=None) -> int:
    return upsert_rows("weather_forecast", forecast_rows(point, df),
                       on_conflict="latitude,longitude,ts", client=client)
