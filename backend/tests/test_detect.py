from dataclasses import replace

import pandas as pd
import pytest

from app.detect.evaluate import events_from_labels, score, summary
from app.detect.expected import expected_power
from app.detect.rules import (
    FAULT,
    OK,
    UNKNOWN,
    dead_string,
    episodes,
    hot_battery,
    run_all,
    weak_string,
)
from app.simulator.battery import BatteryState
from app.simulator.engine import STEP, TELEMETRY_COLUMNS, SimState, simulate_window
from app.simulator.faults import Fault
from tests.test_engine import HOME as _HOME
from tests.test_engine import _weather

HOME = replace(_HOME, inverter_mode="SBU")       # SBU: battery not always full, more to see
TZ = "Africa/Lagos"
DAY = pd.Timestamp("2026-02-01", tz=TZ)


def _run(faults, days=6):
    hourly = _weather(days=days)
    start = SimState(BatteryState(soc=0.3))
    out, _ = simulate_window(HOME, DAY - STEP, DAY + pd.Timedelta(days=days) - STEP, hourly, "left",
                             start, faults)
    exp = expected_power(HOME, hourly, "left", out.index)
    return out, out[TELEMETRY_COLUMNS], exp


def test_episodes_need_persistence():
    idx = pd.date_range(DAY, periods=12, freq="1D")
    ev = pd.Series([OK, FAULT, OK, FAULT, UNKNOWN, FAULT, FAULT, OK, OK, UNKNOWN, OK, OK], index=idx)
    eps = episodes(ev, start_after=3, end_after=3)
    assert eps == [(idx[3], idx[6], idx[10])]          # unknowns skipped; single blips ignored


def test_dead_string_found_within_minutes():
    f = Fault("string_failure", DAY + pd.Timedelta(days=1, hours=10), None, "pv2")
    _, tel, exp = _run([f], days=3)
    alarms = dead_string(HOME, tel, exp)
    assert len(alarms) == 1 and alarms[0].target == "pv2"
    assert alarms[0].raised_at - f.start <= pd.Timedelta(minutes=20)


def test_weak_string_found_and_named():
    f = Fault("underrated_panel", DAY, None, "pv1", {"factor": 0.75})
    _, tel, exp = _run([f])
    alarms = weak_string(HOME, tel, exp)
    assert len(alarms) == 1 and alarms[0].target == "pv1"
    assert alarms[0].details["output_vs_rated"] == pytest.approx(0.75, abs=0.03)


def test_hot_battery_room():
    f = Fault("hot_battery_room", DAY, None, "all", {"extra_c": 10})
    _, tel, exp = _run([f], days=4)
    assert [a.kind for a in hot_battery(HOME, tel, exp)] == ["hot_battery_room"]


def test_healthy_site_raises_nothing():
    _, tel, exp = _run([])
    assert run_all(HOME, tel, exp) == []


def test_scoring_against_the_answer_key():
    f = Fault("string_failure", DAY + pd.Timedelta(days=1, hours=10), DAY + pd.Timedelta(days=2), "pv2")
    out, tel, exp = _run([f], days=4)
    events = events_from_labels(out["fault_label"])
    assert list(events.kind) == ["string_failure"]
    ev, al = score(events, run_all(HOME, tel, exp), out.index[0])
    s = summary(ev, al, months=4 / 30.4)
    assert s.loc["string_failure", "recall"] == 1.0
    assert s.loc["string_failure", "false_alarms"] == 0
