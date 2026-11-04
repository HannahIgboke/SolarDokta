from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from app.simulator.appliances import PROFILES
from app.simulator.grid import BAND_HOURS, _collapse_mask, simulate_grid
from app.simulator.load import simulate_load
from app.simulator.site import SiteConfig

HOME = SiteConfig(
    id="x", code="lagos-001", latitude=6.6, longitude=3.35, timezone="Africa/Lagos",
    pv1_kwp=4.4, pv2_kwp=4.4, tilt_deg=10, azimuth_deg=180, inverter_kw=6, battery_kwh=10,
    battery_chemistry="lifepo4", tariff_band="A", city="Lagos", load_profile="home",
)
DAYS = pd.date_range("2026-03-02", periods=28, freq="D", tz="Africa/Lagos")   # starts on a Monday


def _daily_kwh(site, day, temp=None):
    return simulate_load(site, day, temp)["load_w"].sum() * (5 / 60) / 1000


@pytest.mark.parametrize("profile, low, high", [
    ("home", 4, 16), ("home_large", 12, 40), ("clinic", 12, 40), ("school", 3, 30), ("shop", 5, 20),
])
def test_daily_energy_is_realistic(profile, low, high):
    site = replace(HOME, code=f"t-{profile}", load_profile=profile)
    avg = np.mean([_daily_kwh(site, d) for d in DAYS])
    assert low < avg < high, f"{profile}: {avg:.1f} kWh/day"


def test_shape_and_columns():
    df = simulate_load(HOME, DAYS[0])
    assert len(df) == 288 and df.index[0].hour == 0
    assert {a.name for a in PROFILES["home"].appliances} | {"load_w"} == set(df.columns)
    assert (df["load_w"] >= 13).all()                     # router (15 W +/- 10%) is always on
    evening = df.between_time("19:30", "22:00")["load_w"].mean()
    midday = df.between_time("11:00", "13:00")["load_w"].mean()
    assert evening > midday                                # homes peak in the evening


def test_same_day_same_usage():
    pd.testing.assert_frame_equal(simulate_load(HOME, DAYS[3]), simulate_load(HOME, DAYS[3]))


def test_hot_days_use_more_energy():
    cool = np.mean([_daily_kwh(HOME, d, np.full(288, 26.0)) for d in DAYS])
    hot = np.mean([_daily_kwh(HOME, d, np.full(288, 36.0)) for d in DAYS])
    assert hot > cool * 1.1


def test_school_is_quiet_at_weekends():
    school = replace(HOME, code="t-school", load_profile="school")
    weekday = np.mean([_daily_kwh(school, d) for d in DAYS if d.dayofweek < 5])
    weekend = np.mean([_daily_kwh(school, d) for d in DAYS if d.dayofweek >= 5])
    assert weekend < weekday * 0.4


@pytest.mark.parametrize("band", ["A", "C", "E"])
def test_grid_hours_match_band(band):
    site = replace(HOME, code=f"t-grid-{band}", tariff_band=band)
    state, hours = None, []
    for day in pd.date_range("2026-01-01", periods=120, freq="D", tz="Africa/Lagos"):
        df, state = simulate_grid(site, day, state)
        hours.append(df["grid_on"].sum() / 12)
    assert abs(np.mean(hours) - BAND_HOURS[band]) < 2.5, f"band {band}: {np.mean(hours):.1f} h"


def test_grid_continues_across_days():
    """An outage running at midnight must continue into the next day, not reset."""
    state = None
    for day in DAYS[:10]:
        df, new_state = simulate_grid(HOME, day, state)
        if state is not None and state.steps_left > 1:
            assert df["grid_on"].iloc[0] == state.on        # first step continues the old spell
        state = new_state


def test_grid_voltage():
    df, _ = simulate_grid(HOME, DAYS[0])
    assert (df.loc[~df["grid_on"], "grid_v"] == 0).all()
    assert df.loc[df["grid_on"], "grid_v"].between(170, 250).all()


def test_collapse_hits_all_sites_in_a_city():
    other = replace(HOME, code="lagos-002")
    for day in pd.date_range("2026-01-01", periods=400, freq="D", tz="Africa/Lagos"):
        a, _ = simulate_grid(HOME, day, None)
        b, _ = simulate_grid(other, day, None)
        mask = _collapse_mask(HOME, day)
        if mask.any():
            assert not a["grid_on"].to_numpy()[mask].any()
            assert not b["grid_on"].to_numpy()[mask].any()
            return
    pytest.fail("no collapse in 400 days; probability too low?")
