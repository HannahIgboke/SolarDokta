from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from app.detect.evaluate import events_from_labels, score_anomaly, summary_anomaly
from app.detect.expected import expected_power
from app.ml.features import CHANNELS, FEATURES, daily_features, day_labels
from app.ml.models import AutoencoderDetector, ForestDetector, to_alarms
from app.simulator.battery import BatteryState
from app.simulator.engine import STEP, TELEMETRY_COLUMNS, SimState, simulate_window
from app.simulator.faults import Fault
from tests.test_engine import HOME as _HOME
from tests.test_engine import _weather

pytest.importorskip("torch")              # these tests need PyTorch (requirements-ml.txt)

HOME = replace(_HOME, inverter_mode="SBU")
DAY = pd.Timestamp("2026-02-01", tz="Africa/Lagos")


def _sim(days=4, faults=None):
    hourly = _weather(days=days)
    out, _ = simulate_window(HOME, DAY - STEP, DAY + pd.Timedelta(days=days) - STEP, hourly, "left",
                             SimState(BatteryState(soc=0.5)), faults)
    exp = expected_power(HOME, hourly, "left", out.index)
    return out, daily_features(HOME, out[TELEMETRY_COLUMNS], exp)


def test_features_one_row_per_day_scaled_by_size():
    out, x = _sim()
    assert x.shape == (4, len(CHANNELS) * 24) and list(x.columns) == FEATURES
    assert x.filter(like="pv1_").to_numpy().max() < 1.2          # per kWp, so roughly 0-1
    assert x.filter(like="soc_").to_numpy().min() >= 0
    assert (day_labels(out["fault_label"]) == "").all()


def test_partial_days_are_skipped():
    out, _ = _sim(days=2)
    exp = pd.DataFrame({"pv1_exp_w": 0.0, "pv2_exp_w": 0.0, "outdoor_temp_c": 28.0}, index=out.index)
    x = daily_features(HOME, out[TELEMETRY_COLUMNS].iloc[:-10], exp.iloc[:-10])
    assert len(x) == 1


def _toy_days(n=120, seed=0):
    """Fake 'normal' days: a smooth daily shape plus noise, in feature layout."""
    rng = np.random.default_rng(seed)
    base = np.sin(np.linspace(0, np.pi, 24)).clip(0)
    day = np.tile(base, len(CHANNELS))
    return (day + rng.normal(0, 0.05, (n, len(FEATURES)))).astype(np.float32)


def test_autoencoder_flags_an_unusual_day_and_round_trips(tmp_path):
    normal = _toy_days()
    det = AutoencoderDetector.fit(normal, epochs=40)
    odd = _toy_days(5, seed=1)
    odd[:, FEATURES.index("pv2_12") - 6: FEATURES.index("pv2_12") + 6] = 0     # pv2 dead at midday
    assert det.score(odd).min() > det.threshold
    assert (det.score(_toy_days(50, seed=2)) > det.threshold).mean() < 0.2
    assert set(det.worst_channel(odd)) == {"pv2"}
    det.save(tmp_path)
    again = AutoencoderDetector.load(tmp_path)
    np.testing.assert_allclose(again.score(odd), det.score(odd), rtol=1e-5)


def test_forest_fallback_scores_odd_days_higher():
    det = ForestDetector.fit(_toy_days())
    odd = _toy_days(5, seed=1) + 1.0
    assert det.score(odd).min() > det.score(_toy_days(5, seed=2)).max()


def test_daily_flags_become_alarms_and_get_scored():
    f = Fault("string_failure", DAY + pd.Timedelta(days=1, hours=10), DAY + pd.Timedelta(days=2), "pv2")
    out, x = _sim(days=4, faults=[f])
    days = x.index
    ratio = np.array([0.5, 3.0, 0.4, 0.5])                    # day 2 looks unusual
    alarms = to_alarms(days, ratio, 1.0, ["soc", "pv2", "soc", "soc"])
    assert len(alarms) == 1 and alarms[0].details["hint"] == "pv2"
    ev, al = score_anomaly(events_from_labels(out["fault_label"]), alarms, out.index[0])
    s = summary_anomaly(ev, al, months=4 / 30.4)
    assert s.loc["string_failure", "recall"] == 1.0 and s.attrs["false_alarms"] == 0
