from dataclasses import replace

import pandas as pd

from app.detect import live
from app.simulator import store
from app.simulator.battery import BatteryState
from app.simulator.engine import STEP, SimState, simulate_window
from app.simulator.faults import Fault
from tests.fakedb import FakeDB
from tests.test_engine import HOME as _HOME
from tests.test_engine import _weather

HOME = replace(_HOME, id="site-1", inverter_mode="SBU")
TZ = "Africa/Lagos"
START = pd.Timestamp("2026-02-01", tz=TZ)
DAYS = 16
HOURLY = _weather(days=DAYS + 1)


def _load(db, faults, until):
    """Simulate from START to `until` and save it as telemetry in the fake database."""
    out, _ = simulate_window(HOME, START - STEP, until, HOURLY, "left",
                             SimState(BatteryState(soc=0.5)), faults)
    store.save_telemetry(HOME, out, db)
    return out


def test_live_check_opens_records_and_resolves(monkeypatch):
    monkeypatch.setattr(live, "hourly_weather", lambda site, a, b: (HOURLY, "left"))
    db = FakeDB()
    dead = Fault("string_failure", START + pd.Timedelta(days=13, hours=10), None, "pv2")
    surge = Fault("overload", START + pd.Timedelta(days=12, hours=20),
                  START + pd.Timedelta(days=12, hours=20, minutes=20), "all", {"extra_w": 7000})
    now = START + pd.Timedelta(days=14, hours=14)
    _load(db, [dead, surge], now)

    res = live.check_site(HOME, now, db)
    assert "string_failure:pv2" in res["new"]
    assert any(k.startswith("overload:all:") for k in res["new"])
    findings = db.tables["findings"]
    dead_row = next(f for f in findings if f["kind"] == "string_failure")
    assert dead_row["status"] == "open" and dead_row["severity"] == "critical"
    assert next(f for f in findings if f["kind"] == "overload")["status"] == "resolved"
    assert len(db.tables["health_daily"]) >= 13                  # finished days saved

    again = live.check_site(HOME, now, db)                       # running twice saves nothing new
    assert again["new"] == [] and len(db.tables["findings"]) == len(findings)

    # the technician fixes the string the next morning; the next check resolves the finding
    dead.end = START + pd.Timedelta(days=15, hours=8)
    later = START + pd.Timedelta(days=15, hours=15)
    _load(db, [dead, surge], later)
    res = live.check_site(HOME, later, db)
    assert "string_failure:pv2" in res["resolved"]
    assert dead_row["status"] == "resolved"


def test_health_round_trip():
    db = FakeDB()
    daily = pd.DataFrame({"pr_pv1": [0.95, None], "pr_pv2": [0.93, 0.9], "usable_steps": [40, 30],
                          "batt_heat_c": [2.5, 2.7]},
                         index=pd.date_range("2026-02-01", periods=2, freq="D", tz=TZ))
    store.save_health(HOME, daily, db)
    store.save_health(HOME, daily, db)                           # upsert, not duplicate
    back = store.load_health(HOME, pd.Timestamp("2026-01-01", tz=TZ), db)
    assert len(back) == 2 and back["pr_pv2"].tolist() == [0.93, 0.9] and pd.isna(back["pr_pv1"].iloc[1])
    est = pd.Series([0.97, 0.96], index=pd.date_range("2026-02-01 23:00", periods=2, freq="D", tz=TZ))
    store.save_battery_estimates(HOME, est, db)
    loaded = store.load_battery_estimates(HOME, pd.Timestamp("2026-01-01", tz=TZ), db)
    assert loaded.tolist() == [0.97, 0.96] and loaded.index[0] == est.index[0]


def test_too_little_data_is_skipped(monkeypatch):
    assert live.check_site(HOME, START, FakeDB())["skipped"]
