import numpy as np
import pandas as pd
import pytest

from app.detect.battery import battery_fade, capacity_estimates, fade_per_year, report_card
from scripts.evaluate_detectors import add_bms_error
from tests.test_engine import HOME

TZ = "Africa/Lagos"


def _nights(days: int, soh_start: float = 1.0, fade_per_day: float = 0.0) -> pd.DataFrame:
    """Simple telemetry: each night 20:00-02:00 the battery gives 1 kW; it is recharged by day."""
    idx = pd.date_range("2026-01-01", periods=days * 288, freq="5min", tz=TZ)
    soh = soh_start - fade_per_day * np.arange(len(idx)) / 288
    hour = idx.hour
    night = (hour >= 20) | (hour < 2)
    batt_w = np.where(night, -1000.0, 0.0)
    usable_wh = HOME.battery_kwh * 1000 * soh
    soc = np.empty(len(idx))
    level = 1.0
    for k in range(len(idx)):
        if hour[k] == 10 and idx[k].minute == 0:
            level = 1.0                                    # solar refills it every morning
        level += batt_w[k] * (5 / 60) / 0.96 / usable_wh[k]
        soc[k] = level
    volts = np.full(len(idx), 51.0)
    return pd.DataFrame({"batt_soc": soc, "batt_v": volts, "batt_a": batt_w / volts,
                         "batt_temp_c": 30.0}, index=idx)


def test_capacity_estimate_matches_true_health():
    est = capacity_estimates(HOME, _nights(10, soh_start=0.9))
    assert len(est) >= 9
    assert est.median() == pytest.approx(0.9, abs=0.01)


def test_fade_rate_is_robust_to_a_bad_estimate():
    idx = pd.date_range("2026-01-01", periods=20, freq="7D", tz=TZ)
    est = pd.Series(1.0 - 0.10 * np.arange(20) * 7 / 365, index=idx)    # losing 10% a year
    est.iloc[5] = 0.5                                                     # one silly reading
    assert fade_per_year(est) == pytest.approx(0.10, abs=0.01)


def test_weak_battery_raises_an_alarm_normal_one_does_not():
    healthy = add_bms_error(_nights(240, fade_per_day=0.04 / 365), seed=1)     # 4% a year
    weak = add_bms_error(_nights(240, fade_per_day=0.20 / 365), seed=1)        # 20% a year
    assert battery_fade(HOME, healthy, None) == []
    alarms = battery_fade(HOME, weak, None)
    assert alarms and alarms[0].details["fade_per_year"] > 0.12


def test_report_card():
    card = report_card(HOME, _nights(150, soh_start=0.95, fade_per_day=0.10 / 365))
    assert card["soh_estimate"] == pytest.approx(0.95 - 0.10 * 135 / 365, abs=0.02)
    assert card["fade_per_year"] == pytest.approx(0.10, abs=0.02)
    assert 0 < card["years_to_80pct"] < 2
    assert card["equivalent_full_cycles"] == round(150 * 6 / HOME.battery_kwh)


def test_no_deep_discharge_gives_an_empty_time_series():
    tel = _nights(3)
    tel["batt_a"] = 0.0                                                 # battery never used
    est = capacity_estimates(HOME, tel)
    assert est.empty and isinstance(est.index, pd.DatetimeIndex)
    assert est[est.index < tel.index[-1]].empty                         # filtering by time works
