from dataclasses import replace

import numpy as np
import pandas as pd
import pvlib
import pytest

from app.simulator import battery as bat
from app.simulator.battery import BatteryState
from app.simulator.dispatch import energy_balance_error, route
from app.simulator.engine import SimState, simulate_day, summarise
from app.simulator.site import SiteConfig

HOME = SiteConfig(
    id="x", code="lagos-001", latitude=6.6018, longitude=3.3515, timezone="Africa/Lagos",
    pv1_kwp=4.4, pv2_kwp=4.4, tilt_deg=10, azimuth_deg=180, inverter_kw=6, battery_kwh=10,
    battery_chemistry="lifepo4", tariff_band="A", city="Lagos", load_profile="home",
    inverter_mode="SUB",
)
LFP = bat.CHEMISTRIES["lifepo4"]


def _weather(days=3, start="2026-02-01", scale=0.8, temp=30.0):
    """Hourly NASA-style (left-labelled) weather: a fraction of clear sky, fixed temperature."""
    idx = pd.date_range(f"{start} 00:00", periods=24 * (days + 1), freq="1h", tz="UTC") - pd.Timedelta(hours=6)
    fine = pd.date_range(idx[0], idx[-1] + pd.Timedelta(hours=1), freq="5min", tz="UTC")
    z = pvlib.solarposition.get_solarposition(fine, HOME.latitude, HOME.longitude)["apparent_zenith"]
    ghi = pvlib.clearsky.haurwitz(z)["ghi"].resample("1h", label="left", closed="left").mean() * scale
    return pd.DataFrame({"ghi_wm2": ghi, "temp_c": temp}).loc[idx[0]:idx[-1]]


def _run(site=HOME, days=3, state=None, **weather):
    hourly = _weather(days=days, **weather)
    outs = []
    for d in pd.date_range("2026-02-01", periods=days, freq="D", tz=site.timezone):
        out, state = simulate_day(site, d, hourly, "left", state)
        outs.append(out)
    return pd.concat(outs), state


def test_energy_always_balances():
    out, _ = _run()
    assert np.abs(energy_balance_error(out)).max() < 1.0


def test_soc_stays_in_range_and_shape():
    out, _ = _run()
    assert len(out) == 3 * 288
    assert out["batt_soc"].between(LFP.min_soc - 0.005, 1.0).all()
    assert {"pv1_w", "batt_soc", "grid_w", "fault_code"}.issubset(out.columns)


def test_sub_mode_saves_battery_while_nepa_is_on():
    out, _ = _run()
    grid_on = out["grid_v"] > 0
    assert (out.loc[grid_on, "batt_w"] >= -1).all()          # never discharges with NEPA on


def test_battery_carries_the_house_during_outages():
    out, _ = _run()
    night_outage = (out["grid_v"] == 0) & (out["pv1_w"] + out["pv2_w"] < 10) & (out["unserved_w"] == 0)
    assert night_outage.any()
    assert (out.loc[night_outage, "batt_w"] < 0).all()


def test_spare_solar_is_curtailed_when_battery_full():
    full = SimState(BatteryState(soc=1.0))
    out, _ = _run(state=full, days=1)
    assert out["curtailed_w"].sum() > 0
    # a big array with a small daytime load wastes a lot of potential solar
    s = summarise(out, HOME)
    assert s["solar_curtailed_kwh"] > 5


def test_sbu_mode_uses_battery_first():
    sbu = replace(HOME, code="t-sbu", inverter_mode="SBU")
    out, _ = _run(site=sbu, days=2)
    evening = out.between_time("20:00", "23:00")
    on_and_battery = evening[(evening["grid_v"] > 0) & (evening["batt_soc"] > 0.35)]
    assert (on_and_battery["batt_w"] < 0).mean() > 0.8     # battery first even with NEPA on


def test_overload_trips_inverter():
    st = BatteryState(soc=0.9)
    res = route(HOME, LFP, st, pv_w=0, load_w=8000, grid_on=False)
    assert res.fault == "OVERLOAD" and res.served_w == 0 and res.unserved_w == 8000
    res = route(HOME, LFP, st, pv_w=0, load_w=8000, grid_on=True)   # NEPA bypass covers it
    assert res.fault is None and res.served_w == 8000 and res.grid_w >= 8000   # plus battery top-up


def test_empty_battery_shuts_down_but_solar_recharges():
    st = BatteryState(soc=LFP.min_soc)
    res = route(HOME, LFP, st, pv_w=0, load_w=300, grid_on=False)
    assert res.fault == "LOW_BATTERY" and res.served_w == 0
    res = route(HOME, LFP, st, pv_w=2000, load_w=300, grid_on=False, locked=True)
    assert res.fault == "LOW_BATTERY" and res.batt_w > 0     # output off, battery still charging


def test_heat_and_lead_acid_wear_faster():
    def soh_after(chem, temp, days=60):
        c = bat.CHEMISTRIES[chem]
        st = BatteryState(soc=0.9, temp_c=temp)
        for _ in range(days):
            for w in [-1500] * 48 + [1500] * 48:              # one deep-ish daily cycle
                st, _, _ = bat.step(c, 10, st, w, temp)
        return st.soh

    assert soh_after("lifepo4", 40) < soh_after("lifepo4", 25)
    assert soh_after("lead_acid", 30) < soh_after("lifepo4", 30)


def test_heat_factor_doubles_every_10c():
    assert bat.heat_factor(35) == pytest.approx(2 * bat.heat_factor(25))


def test_state_round_trips_and_days_continue():
    _, st1 = _run(days=1)
    restored = SimState.from_dict(st1.to_dict())
    assert restored == st1
    out_both, _ = _run(days=2)
    hourly = _weather(days=2)
    day2, _ = simulate_day(HOME, pd.Timestamp("2026-02-02", tz="Africa/Lagos"), hourly, "left", restored)
    pd.testing.assert_frame_equal(day2, out_both.iloc[288:])
