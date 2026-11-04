from itertools import pairwise

import pandas as pd
import pytest

from app.simulator.battery import BatteryState
from app.simulator.engine import STEP, SimState, simulate_day, simulate_window
from app.simulator.faults import KINDS, Fault, effects, plan_faults
from app.simulator.store import daily_summary, hourly_summary
from tests.test_engine import HOME, _weather

TZ = "Africa/Lagos"
DAY = pd.Timestamp("2026-02-01", tz=TZ)


def ts(s: str) -> pd.Timestamp:
    return pd.Timestamp(s, tz=TZ)


def _day(faults=None, state=None, days=1):
    hourly = _weather(days=days)
    out, st = simulate_window(HOME, DAY - STEP, DAY + pd.Timedelta(days=days) - STEP, hourly, "left",
                              state, faults)
    return out, st


# ---------- faults ----------

def test_string_failure_kills_one_string_only_while_active():
    f = Fault("string_failure", ts("2026-02-01 11:00"), ts("2026-02-01 13:00"), "pv2")
    base, _ = _day()
    out, _ = _day([f])
    hit = (out.index >= f.start) & (out.index < f.end)
    assert (out.loc[hit, "pv_available_w"] < base.loc[hit, "pv_available_w"] * 0.6).all()
    assert (out.loc[hit, "fault_label"] == "string_failure").all()
    assert out.loc[~hit, "fault_label"].isna().all()
    fx = effects([f], out.index)
    assert (fx.pv2_factor[hit] == 0).all() and (fx.pv1_factor == 1).all()


def test_soiling_grows_day_by_day():
    f = Fault("soiling", DAY, None, "all", {"max_loss": 0.3, "ramp_days": 30})
    idx = pd.date_range(DAY, periods=288 * 40, freq="5min")
    fx = effects([f], idx)
    daily = pd.Series(fx.pv1_factor, index=idx).resample("1D").mean()
    assert daily.iloc[0] > daily.iloc[10] > daily.iloc[20] > daily.iloc[35] - 1e-9
    assert daily.iloc[35] == pytest.approx(0.7, abs=0.01)


def test_shading_only_in_its_hours():
    f = Fault("shading", DAY, None, "pv1", {"from_hour": 15, "hours": 2, "loss": 0.6})
    idx = pd.date_range(DAY, periods=288, freq="5min")
    fx = effects([f], idx)
    shaded = (idx.hour >= 15) & (idx.hour < 17)
    assert (fx.pv1_factor[shaded] == pytest.approx(0.4)) and (fx.pv1_factor[~shaded] == 1).all()


def test_overload_during_outage_trips_the_inverter():
    base, _ = _day()
    outage = base.index[(base["grid_v"] == 0) & (base.index.hour >= 18)]
    assert len(outage), "test day needs an evening outage"
    f = Fault("overload", outage[0], outage[0] + 2 * STEP, "all", {"extra_w": 7000})
    out, _ = _day([f])
    assert "OVERLOAD" in set(out["fault_code"].dropna())


def test_hot_room_and_weak_battery_wear_faster():
    _, normal = _day(days=3)
    hot = Fault("hot_battery_room", DAY, None, "all", {"extra_c": 10})
    out_hot, st_hot = _day([hot], days=3)
    fade = Fault("battery_fade", DAY, None, "all", {"soh_per_day": 0.001})
    _, st_fade = _day([fade], days=3)
    assert out_hot["batt_temp_c"].max() > 37
    assert st_hot.battery.soh < normal.battery.soh
    assert normal.battery.soh - st_fade.battery.soh == pytest.approx(0.003, abs=0.0003)


def test_fault_rows_round_trip():
    f = Fault("shading", ts("2026-03-01 15:00"), None, "pv1", {"from_hour": 15, "hours": 2, "loss": 0.6})
    row = f.to_row("site-1")
    assert row["start_ts"] == "2026-03-01T14:00:00Z" and row["params"]["target"] == "pv1"
    back = Fault.from_row(row)
    assert (back.kind, back.target, back.params, back.end) == (f.kind, f.target, f.params, None)
    assert back.start == f.start


def test_plan_is_repeatable_and_realistic():
    start, end = ts("2025-01-01"), ts("2026-11-01")
    a = plan_faults(HOME, start, end, seed=1)
    b = plan_faults(HOME, start, end, seed=1)
    assert [x.to_row("s") for x in a] == [x.to_row("s") for x in b]
    kinds = {x.kind for x in a}
    assert {"soiling", "overload"} <= kinds <= set(KINDS)
    assert all(x.overlaps(start, end) for x in a)
    assert sum(x.kind == "overload" for x in a) >= 3


# ---------- ticks give the same answer as one long run ----------

def test_ticks_match_one_long_run():
    faults = [Fault("string_failure", ts("2026-02-01 12:00"), ts("2026-02-02 09:00"), "pv1")]
    hourly = _weather(days=2)
    whole, st_whole = simulate_window(HOME, DAY - STEP, DAY + pd.Timedelta(days=2) - STEP,
                                      hourly, "left", None, faults)

    # the same two days in uneven chunks, saving and reloading the state like the database does
    cuts = [DAY - STEP, ts("2026-02-01 00:20"), ts("2026-02-01 13:05"), ts("2026-02-01 23:55"),
            ts("2026-02-02 00:00"), ts("2026-02-02 17:40"), DAY + pd.Timedelta(days=2) - STEP]
    parts, st = [], None
    for a, b in pairwise(cuts):
        out, st = simulate_window(HOME, a, b, hourly, "left", st, faults)
        parts.append(out)
        st = SimState.from_dict(st.to_dict())
    ticked = pd.concat(parts)
    pd.testing.assert_frame_equal(ticked, whole)
    assert st == st_whole


def test_catch_up_after_a_gap_matches_day_by_day():
    hourly = _weather(days=3)
    st, outs = None, []
    for d in pd.date_range(DAY, periods=3, freq="D"):
        out, st = simulate_day(HOME, d, hourly, "left", st)
        outs.append(out)
    _, st_jump = simulate_window(HOME, DAY - STEP, DAY + pd.Timedelta(days=3) - STEP, hourly, "left")
    assert st_jump == st
    assert len(pd.concat(outs)) == 3 * 288


# ---------- summaries ----------

def test_summaries_add_up():
    out, _ = _day(days=2)
    hourly = hourly_summary(out)
    daily = daily_summary(hourly, TZ)
    assert len(hourly) == 48 and len(daily) == 2
    assert (hourly["samples"] == 12).all()
    pv_total = (out["pv1_w"] + out["pv2_w"]).sum() * 5 / 60 / 1000
    assert daily["pv_kwh"].sum() == pytest.approx(pv_total)
    assert daily["grid_on_minutes"].sum() == (out["grid_v"] > 150).sum() * 5


def test_fresh_state_defaults():
    st = SimState.from_dict(None)
    assert st.battery == BatteryState() and st.day is None
