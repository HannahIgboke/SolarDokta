"""Score the rule/physics detectors against the injected faults in ml/data/sim/*.parquet.

Being honest about the data:
- Weather: the simulator made its sunshine from the same NASA/Open-Meteo data the detectors use.
  Real satellite weather is never that exact, so by default we add random error to the
  detectors' copy (about 12% per hour and 5% per day on sunlight, 1 C on temperature).
- Battery gauge: the simulator knows the true charge level. A real battery's gauge (BMS) drifts
  between full charges and is a little off in scale, so by default we add that error too.

Usage (from backend/):
    python -m scripts.evaluate_detectors
    python -m scripts.evaluate_detectors --sites lagos-002 --show-alarms
    python -m scripts.evaluate_detectors --no-weather-noise --no-bms-noise
Results are also saved in ml/reports/.
"""

import argparse

import numpy as np
import pandas as pd

from app.config import REPO_ROOT
from app.detect.evaluate import events_from_labels, score, summary
from app.detect.expected import expected_power
from app.detect.rules import run_all
from app.simulator.engine import TELEMETRY_COLUMNS
from app.simulator.site import load_site
from app.simulator.weather_source import hourly_weather
from scripts.generate_history import DEFAULT_SITES

SIM_DIR = REPO_ROOT / "ml" / "data" / "sim"
REPORT_DIR = REPO_ROOT / "ml" / "reports"


def add_weather_error(hourly: pd.DataFrame, seed: int, hourly_sd=0.12, daily_sd=0.05) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    out = hourly.copy()
    days = out.index.normalize()
    per_day = pd.Series(rng.normal(0, daily_sd, len(days.unique())), index=days.unique())
    out["ghi_wm2"] *= np.exp(rng.normal(0, hourly_sd, len(out)) + per_day.reindex(days).to_numpy())
    out["temp_c"] += rng.normal(0, 1.0, len(out))
    return out


def add_bms_error(tel: pd.DataFrame, seed: int, drift_per_day=0.015, gain_sd=0.02) -> pd.DataFrame:
    """Realistic battery-gauge error: drifts slowly, resets to exact whenever the battery is full,
    and is a little off in scale (a 10% drop may read as 9.8% or 10.2%)."""
    rng = np.random.default_rng(1000 + seed)
    soc = tel["batt_soc"].to_numpy()
    steps = rng.normal(0, drift_per_day / np.sqrt(288), len(soc))
    drift = np.empty(len(soc))
    x = 0.0
    for k in range(len(soc)):
        x = 0.0 if soc[k] >= 0.99 else x + steps[k]
        drift[k] = x
    out = tel.copy()
    out["batt_soc"] = np.clip(1 - (1 - soc) * rng.normal(1, gain_sd) + drift, 0, 1)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sites", nargs="+", default=DEFAULT_SITES)
    parser.add_argument("--no-weather-noise", action="store_true")
    parser.add_argument("--no-bms-noise", action="store_true")
    parser.add_argument("--show-alarms", action="store_true", help="list every false alarm and miss")
    args = parser.parse_args()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    all_ev, all_al, months = [], [], 0.0
    for i, code in enumerate(args.sites):
        df = pd.read_parquet(SIM_DIR / f"{code}.parquet")
        site = load_site(code)
        hourly, label = hourly_weather(site, df.index[0], df.index[-1] + pd.Timedelta(minutes=5))
        if not args.no_weather_noise:
            hourly = add_weather_error(hourly, seed=i)

        exp = expected_power(site, hourly, label, df.index)
        tel = df[TELEMETRY_COLUMNS]
        if not args.no_bms_noise:
            tel = add_bms_error(tel, seed=i)
        alarms = run_all(site, tel, exp)                        # detectors never see the labels
        ev, al = score(events_from_labels(df["fault_label"]), alarms, df.index[0])
        m = len(df) / 288 / 30.4
        months += m
        ev.insert(0, "site", code)
        al.insert(0, "site", code)
        all_ev.append(ev)
        all_al.append(al)

        print(f"\n== {code}  ({m:.0f} months, {len(alarms)} alarms)")
        print(summary(ev, al, m).round(2).to_string())
        if args.show_alarms:
            fa, miss = al[~al.true_alarm], ev[~ev.detected & ev.scored]
            if len(fa):
                print("  false alarms:\n" + fa[["kind", "start", "end", "target", "details"]].to_string())
            if len(miss):
                print("  missed:\n" + miss[["kind", "start", "end"]].to_string())

    ev, al = pd.concat(all_ev), pd.concat(all_al)
    total = summary(ev, al, months)
    print(f"\n== ALL SITES  ({months:.0f} site-months)")
    print(total.round(2).to_string())
    total.to_csv(REPORT_DIR / "detector_summary.csv")
    ev.to_csv(REPORT_DIR / "detector_events.csv", index=False)
    al.to_csv(REPORT_DIR / "detector_alarms.csv", index=False)
    print(f"\nSaved to {REPORT_DIR.relative_to(REPO_ROOT)}/")


if __name__ == "__main__":
    main()
