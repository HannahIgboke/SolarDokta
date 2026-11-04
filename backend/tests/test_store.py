import json

import numpy as np
import pandas as pd

from app import db
from app.weather.points import WeatherPoint
from app.weather.store import forecast_rows, history_rows, save_history


class FakeTable:
    def __init__(self, log, name):
        self.log, self.name = log, name

    def upsert(self, rows, on_conflict, returning):
        self.log.append((self.name, list(rows), on_conflict))
        return self

    def execute(self):
        return self


class FakeClient:
    def __init__(self):
        self.calls = []

    def table(self, name):
        return FakeTable(self.calls, name)


def _df(n):
    idx = pd.date_range("2026-01-01", periods=n, freq="h", tz="UTC")
    return pd.DataFrame({"ghi_wm2": np.linspace(0, 900, n), "temp_c": 27.0}, index=idx)


def test_history_rows_are_json_ready():
    df = _df(3)
    df.iloc[1, 0] = np.nan
    rows = list(history_rows(WeatherPoint(6.5, 3.5), df))
    json.dumps(rows)                           # must not raise (no NaN, no numpy types)
    assert rows[0]["ts"] == "2026-01-01T00:00:00+00:00"
    assert rows[1]["ghi_wm2"] is None
    assert rows[2]["ghi_wm2"] == 900.0


def test_forecast_rows_include_cloud_cover():
    df = _df(2).assign(cloud_cover_pct=[80, 75])
    rows = list(forecast_rows(WeatherPoint(4.5, 7.0), df))
    assert rows[1]["cloud_cover_pct"] == 75.0 and rows[0]["source"] == "open_meteo"


def test_upsert_is_batched(monkeypatch):
    monkeypatch.setattr(db, "BATCH_SIZE", 1000)
    client = FakeClient()
    n = save_history(WeatherPoint(6.5, 3.5), _df(2500), client=client)
    assert n == 2500
    assert [len(c[1]) for c in client.calls] == [1000, 1000, 500]
    assert all(c[0] == "weather_history" and c[2] == "latitude,longitude,ts" for c in client.calls)
