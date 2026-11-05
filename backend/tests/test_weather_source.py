import numpy as np
import pandas as pd
import pytest

from app.simulator import weather_source as ws
from tests.test_engine import HOME

UTC = "UTC"


def _hours(start, end, ghi=100.0, temp=27.0):
    """Sunny-ish fake weather: ghi at midday hours, 0 at night (left labelled)."""
    idx = pd.date_range(start, end, freq="1h", tz=UTC)
    sun = np.where((idx.hour >= 7) & (idx.hour <= 16), ghi, 0.0)
    return pd.DataFrame({"ghi_wm2": sun, "temp_c": temp}, index=idx)


def test_stitch_prefers_the_first_source_with_real_values():
    nasa = _hours("2026-08-29", "2026-09-03", ghi=500)
    nasa.loc["2026-09-01":, "ghi_wm2"] = np.nan                        # NASA stops
    archive = _hours("2026-08-30", "2026-09-10", ghi=400)
    df = ws.stitch([nasa, archive], pd.Timestamp("2026-08-30", tz=UTC), pd.Timestamp("2026-09-05", tz=UTC))
    assert df.index.is_unique and df.index.is_monotonic_increasing
    assert df.loc["2026-08-31 12:00", "ghi_wm2"] == 500                 # NASA where it has data
    assert df.loc["2026-09-02 12:00", "ghi_wm2"] == 400                 # archive after
    assert df["ghi_wm2"].notna().all()


def test_all_dark_days_count_as_missing():
    bad = _hours("2026-09-01", "2026-09-05", ghi=500)
    bad.loc["2026-09-02", "ghi_wm2"] = 0.0                               # a whole day of "no sun"
    clean = ws.drop_dark_days(bad)
    assert clean.loc["2026-09-02", "ghi_wm2"].isna().all()
    assert clean.loc["2026-09-03", "ghi_wm2"].notna().all()
    assert ws.longest_gap_hours(clean["ghi_wm2"]) == 24


def test_hourly_weather_fills_the_nasa_gap_from_the_archive(monkeypatch):
    now = pd.Timestamp("2026-11-02 12:00", tz=UTC)
    monkeypatch.setattr(ws.pd.Timestamp, "now", staticmethod(lambda tz=None: now))
    nasa = _hours("2026-08-01", "2026-09-30", ghi=500)
    nasa.loc["2026-09-01":, "ghi_wm2"] = np.nan
    calls = []
    monkeypatch.setattr(ws, "_nasa", lambda path: nasa)
    monkeypatch.setattr(ws, "_archive", lambda p, a, b: calls.append(("archive", a, b))
                        or _hours("2026-08-25", "2026-10-28", ghi=400))
    monkeypatch.setattr(ws, "_forecast", lambda p, past, fut, hour: calls.append(("forecast", past))
                        or _hours("2026-10-01", "2026-11-10", ghi=300))

    df, label = ws.hourly_weather(HOME, pd.Timestamp("2026-08-25", tz=UTC), pd.Timestamp("2026-11-03", tz=UTC))
    assert label == "left"
    assert [c[0] for c in calls] == ["archive", "forecast"]
    assert calls[0][1] == "2026-08-31"                                   # starts where NASA stops
    assert df.loc["2026-08-28 12:00", "ghi_wm2"] == 500
    assert df.loc["2026-09-15 12:00", "ghi_wm2"] == 400
    assert df.loc["2026-11-01 12:00", "ghi_wm2"] in (300, 400)
    assert df["ghi_wm2"].notna().all()


def test_a_real_hole_stops_with_a_clear_error(monkeypatch):
    now = pd.Timestamp("2026-11-02 12:00", tz=UTC)
    monkeypatch.setattr(ws.pd.Timestamp, "now", staticmethod(lambda tz=None: now))
    nasa = _hours("2026-08-01", "2026-09-30", ghi=500)
    nasa.loc["2026-09-01":, "ghi_wm2"] = np.nan
    archive = _hours("2026-08-25", "2026-10-28", ghi=400)
    archive.loc["2026-09-01":"2026-09-08", "ghi_wm2"] = 0.0              # the September bug
    monkeypatch.setattr(ws, "_nasa", lambda path: nasa)
    monkeypatch.setattr(ws, "_archive", lambda p, a, b: archive)
    monkeypatch.setattr(ws, "_forecast", lambda *a: _hours("2026-10-01", "2026-11-10", ghi=300))
    with pytest.raises(ValueError, match="hole"):
        ws.hourly_weather(HOME, pd.Timestamp("2026-08-25", tz=UTC), pd.Timestamp("2026-11-03", tz=UTC))


def test_tick_only_needs_the_forecast(monkeypatch):
    now = pd.Timestamp("2026-11-02 12:00", tz=UTC)
    monkeypatch.setattr(ws.pd.Timestamp, "now", staticmethod(lambda tz=None: now))
    nasa = _hours("2026-08-01", "2026-08-31", ghi=500)
    calls = []
    monkeypatch.setattr(ws, "_nasa", lambda path: nasa)
    monkeypatch.setattr(ws, "_archive", lambda *a: calls.append("archive"))
    monkeypatch.setattr(ws, "_forecast", lambda *a: calls.append("forecast")
                        or _hours("2026-10-25", "2026-11-10", ghi=300))
    ws.hourly_weather(HOME, pd.Timestamp("2026-11-02", tz=UTC), pd.Timestamp("2026-11-03", tz=UTC))
    assert calls == ["forecast"]


def test_readings_continue_when_open_meteo_refuses(monkeypatch):
    """Open-Meteo rate-limits shared cloud servers (429): fall back to the saved forecast."""
    from tests.fakedb import FakeDB

    now = pd.Timestamp("2026-11-05 13:00", tz=UTC)
    monkeypatch.setattr(ws.pd.Timestamp, "now", staticmethod(lambda tz=None: now))
    monkeypatch.setattr(ws, "_nasa", lambda path: None)
    ws._last_good.clear()

    def refused(*a):
        raise RuntimeError("429 Too Many Requests")

    monkeypatch.setattr(ws, "_forecast", refused)
    p = ws.weather_point(HOME.latitude, HOME.longitude)
    saved = _hours("2026-11-01", "2026-11-08", ghi=350)
    db = FakeDB()
    db.tables["weather_forecast"] = [
        {"latitude": p.latitude, "longitude": p.longitude, "ts": ts.isoformat(),
         "ghi_wm2": float(r.ghi_wm2), "temp_c": float(r.temp_c)} for ts, r in saved.iterrows()]
    import app.db
    monkeypatch.setattr(app.db, "get_client", lambda: db)
    df, label = ws.hourly_weather(HOME, pd.Timestamp("2026-11-05", tz=UTC), pd.Timestamp("2026-11-06", tz=UTC))
    assert label == "left" and df["ghi_wm2"].max() == 350 and df["ghi_wm2"].notna().all()


def test_the_last_good_download_is_reused(monkeypatch):
    now = pd.Timestamp("2026-11-05 13:00", tz=UTC)
    monkeypatch.setattr(ws.pd.Timestamp, "now", staticmethod(lambda tz=None: now))
    monkeypatch.setattr(ws, "_nasa", lambda path: None)
    monkeypatch.setattr(ws, "_saved", lambda point: None)
    ws._last_good.clear()
    good = _hours("2026-11-01", "2026-11-08", ghi=420)
    monkeypatch.setattr(ws, "_forecast", lambda *a: good)
    ws.hourly_weather(HOME, pd.Timestamp("2026-11-05", tz=UTC), pd.Timestamp("2026-11-06", tz=UTC))

    def refused(*a):
        raise RuntimeError("429")

    monkeypatch.setattr(ws, "_forecast", refused)
    df, _ = ws.hourly_weather(HOME, pd.Timestamp("2026-11-05", tz=UTC), pd.Timestamp("2026-11-06", tz=UTC))
    assert df["ghi_wm2"].max() == 420
