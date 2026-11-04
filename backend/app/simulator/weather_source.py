"""Hourly weather for the simulator and detectors, for any date range.

Three sources, best first:
1. Your local NASA POWER files (no internet needed). NASA runs ~2 months behind.
2. Open-Meteo archive (ERA5 reanalysis): fills from where NASA stops to ~5 days ago.
3. Open-Meteo forecast: the last few weeks and the next days.

Each hour is taken from the best source that has a real value for it. Open-Meteo labels each
hour at its END ("right") while NASA labels it at its START ("left"), so Open-Meteo times are
moved back one hour and the result is always "left" labelled.

Safety checks (a bad join here once made the simulator think September had no sun):
- a whole day of near-zero sunlight is impossible in Nigeria, so such days count as missing
- if any stretch of more than MAX_GAP_HOURS hours is still missing, we stop with an error
  instead of guessing
"""

from functools import lru_cache
from pathlib import Path

import pandas as pd

from app.config import REPO_ROOT
from app.simulator.site import SiteConfig
from app.weather import open_meteo
from app.weather.points import WeatherPoint, weather_point

NASA_DIR = REPO_ROOT / "ml" / "data" / "raw" / "nasa_power"
LABEL = "left"
PAD = pd.Timedelta(hours=3)
FORECAST_PAST_DAYS = 30           # trust the forecast service's "past days" only this far back
MAX_GAP_HOURS = 6
DARK_DAY_WH_M2 = 200              # even the rainiest Nigerian day gets more sunlight than this


@lru_cache(maxsize=8)
def _nasa(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    return pd.read_parquet(path)[["ghi_wm2", "temp_c"]]


def _to_left(df: pd.DataFrame) -> pd.DataFrame:
    df = df[["ghi_wm2", "temp_c"]].copy()
    df.index = df.index - pd.Timedelta(hours=1)          # "right" -> "left" labelling
    return df


@lru_cache(maxsize=8)
def _archive(point: WeatherPoint, start_date: str, end_date: str) -> pd.DataFrame:
    return _to_left(open_meteo.fetch_archive(point.latitude, point.longitude, start_date, end_date))


@lru_cache(maxsize=8)
def _forecast(point: WeatherPoint, past_days: int, forecast_days: int, hour: str) -> pd.DataFrame:
    """Cached per clock hour, so sites sharing a weather point make one request per tick."""
    return _to_left(open_meteo.fetch_hourly(point.latitude, point.longitude, past_days=past_days,
                                            forecast_days=forecast_days))


def drop_dark_days(df: pd.DataFrame) -> pd.DataFrame:
    """Full days with (almost) no sunlight are data errors: mark their sunlight as missing."""
    df = df.copy()
    day = df.index.floor("1D")
    hours = df["ghi_wm2"].notna().groupby(day).transform("sum")
    total = df["ghi_wm2"].groupby(day).transform("sum")
    df.loc[(hours >= 20) & (total < DARK_DAY_WH_M2), "ghi_wm2"] = float("nan")
    return df


def stitch(sources: list[pd.DataFrame | None], start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Hourly frame for [start, end]: each hour from the first source with a real value."""
    idx = pd.date_range(start, end, freq="1h")
    out = pd.DataFrame(index=idx, columns=["ghi_wm2", "temp_c"], dtype="float64")
    for src in sources:
        if src is None or src.empty:
            continue
        src = drop_dark_days(src[~src.index.duplicated(keep="first")])
        out = out.combine_first(src.reindex(idx))
    return out


def longest_gap_hours(s: pd.Series) -> int:
    missing = s.isna().to_numpy()
    longest = run = 0
    for m in missing:
        run = run + 1 if m else 0
        longest = max(longest, run)
    return longest


def hourly_weather(site: SiteConfig, start: pd.Timestamp, end: pd.Timestamp) -> tuple[pd.DataFrame, str]:
    """Hourly ghi_wm2 + temp_c (UTC index, left-labelled) covering [start, end)."""
    start, end = pd.Timestamp(start).tz_convert("UTC"), pd.Timestamp(end).tz_convert("UTC")
    pad_start, pad_end = (start - PAD).floor("1h"), (end + PAD).ceil("1h")
    now = pd.Timestamp.now(tz="UTC")
    p = weather_point(site.latitude, site.longitude)

    nasa = _nasa(NASA_DIR / f"lat{p.latitude}_lon{p.longitude}.parquet")
    nasa_end = nasa["ghi_wm2"].last_valid_index() if nasa is not None else None
    sources = [nasa.loc[pad_start:pad_end] if nasa is not None else None]

    covered_until = nasa_end if nasa_end is not None else pad_start - pd.Timedelta(hours=1)
    forecast_from = now.floor("1D") - pd.Timedelta(days=FORECAST_PAST_DAYS)
    a_from, a_to = max(pad_start, covered_until), min(pad_end, forecast_from)
    if a_from < a_to:                                    # older than the forecast service keeps
        sources.append(_archive(p, a_from.strftime("%Y-%m-%d"),
                                (a_to + pd.Timedelta(days=1)).strftime("%Y-%m-%d")))
    if pad_end > max(covered_until, forecast_from):      # recent days and the future
        past_days = min(92, max(1, (now - max(pad_start, forecast_from)).days + 2))
        forecast_days = max(1, min(16, (pad_end - now).days + 2))
        sources.append(_forecast(p, past_days, forecast_days, f"{now:%Y-%m-%d %H}"))

    df = stitch(sources, pad_start, pad_end)
    gap = longest_gap_hours(df["ghi_wm2"])
    if gap > MAX_GAP_HOURS:
        first_missing = df.index[df["ghi_wm2"].isna()][0]
        raise ValueError(f"Weather for {site.code} has a {gap}-hour hole (first missing hour "
                         f"{first_missing:%Y-%m-%d %H:%M} UTC). Check your NASA files / internet.")
    df = df.interpolate(limit=MAX_GAP_HOURS, limit_direction="both")
    return df, LABEL
