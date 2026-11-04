import numpy as np
import pandas as pd
import pvlib

from app.simulator.pv import day_seed, pv_power, spread_hourly_ghi
from app.simulator.site import SiteConfig

SITE = SiteConfig(
    id="x", code="lagos-001", latitude=6.6018, longitude=3.3515, timezone="Africa/Lagos",
    pv1_kwp=3.6, pv2_kwp=1.4, tilt_deg=10, azimuth_deg=180, inverter_kw=6, battery_kwh=10,
    battery_chemistry="lifepo4", tariff_band="A",
)


def _clear_day_hourly(day: str, scale: float = 0.8, label: str = "left") -> pd.DataFrame:
    """Hourly weather = a fraction of clear sky, labelled like NASA (left) or Open-Meteo (right)."""
    idx = pd.date_range(f"{day} 00:00", periods=48, freq="1h", tz="UTC")
    fine = pd.date_range(idx[0], idx[-1] + pd.Timedelta(hours=1), freq="5min", tz="UTC")
    z = pvlib.solarposition.get_solarposition(fine, SITE.latitude, SITE.longitude)["apparent_zenith"]
    clear = pvlib.clearsky.haurwitz(z)["ghi"]
    closed = "left" if label == "left" else "right"
    ghi = clear.resample("1h", label=label, closed=closed).mean() * scale
    return pd.DataFrame({"ghi_wm2": ghi, "temp_c": 30.0}).loc[idx[0]:idx[-1]]


def _simulate(day="2026-01-15", scale=0.8, label="left", seed=1, soiling=None):
    hourly = _clear_day_hourly(day, scale, label)
    start = pd.Timestamp(f"{day} 00:00", tz="Africa/Lagos").tz_convert("UTC")
    w5 = spread_hourly_ghi(hourly, SITE, start, start + pd.Timedelta(days=1), label=label, seed=seed)
    return w5, pv_power(w5, SITE, soiling)


def test_shape_and_night():
    _, pv = _simulate()
    assert len(pv) == 288                                   # 24 h x 12 steps
    local = pv.tz_convert("Africa/Lagos")
    assert local.between_time("00:00", "05:00")[["pv1_w", "pv2_w"]].max().max() == 0
    assert local.between_time("12:00", "14:00")["pv1_w"].mean() > 1500


def test_hourly_energy_is_preserved():
    """Spreading hourly sunlight into 5-minute steps must keep (roughly) the same energy."""
    hourly = _clear_day_hourly("2026-01-15", 0.8)
    w5, _ = _simulate(seed=None)
    day = slice("2026-01-15 06:00", "2026-01-15 17:59")
    ratio = w5["ghi_wm2"].loc[day].mean() / hourly["ghi_wm2"].loc[day].mean()
    assert 0.85 < ratio < 1.15


def test_label_conventions_agree():
    _, left = _simulate(label="left", seed=3)
    _, right = _simulate(label="right", seed=3)
    e_left, e_right = left["pv1_w"].sum(), right["pv1_w"].sum()
    assert abs(e_left - e_right) / e_left < 0.05


def test_daily_energy_is_realistic():
    _, pv = _simulate(scale=0.8)
    kwh_per_kwp = pv["pv1_w"].sum() * (5 / 60) / 1000 / SITE.pv1_kwp
    assert 3.0 < kwh_per_kwp < 5.5                          # typical for southern Nigeria


def test_soiling_and_voltage():
    _, clean = _simulate(seed=5)
    _, dirty = _simulate(seed=5, soiling={"pv2": 0.5})
    assert np.isclose(dirty["pv2_w"].sum(), clean["pv2_w"].sum() * 0.5)
    noon = clean.tz_convert("Africa/Lagos").between_time("12:30", "13:30")
    assert 250 < noon["pv1_v"].mean() < 320                  # 7 x ~41 V panels, hot


def test_same_seed_same_clouds():
    _, a = _simulate(seed=day_seed("lagos-001", pd.Timestamp("2026-01-15")))
    _, b = _simulate(seed=day_seed("lagos-001", pd.Timestamp("2026-01-15")))
    pd.testing.assert_frame_equal(a, b)
    assert day_seed("lagos-001", pd.Timestamp("2026-01-15")) != day_seed("lagos-001", pd.Timestamp("2026-01-16"))
