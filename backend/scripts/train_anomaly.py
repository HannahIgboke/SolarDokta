"""Train and score the anomaly models (autoencoder + Isolation Forest) against the rules.

How the test is kept fair:
- Time-blocked cross-validation: the period is cut into --folds blocks. For each block, the
  models train only on CLEAN days from the other blocks, then score every day in that block.
  So every day gets a score from a model that never saw it.
- One model for all sites together (features are scaled by each site's size).
- Weather and battery-gauge error are added like in evaluate_detectors, and the models never
  see the labels.

At the end, a final autoencoder is trained on all clean days and saved in ml/models/ (this is
the one Phase 5 will host on Modal).

Usage (from backend/):
    python -m scripts.train_anomaly
    python -m scripts.train_anomaly --folds 4 --epochs 150
"""

import argparse
import time

import numpy as np
import pandas as pd

from app.config import REPO_ROOT
from app.detect.evaluate import (
    events_from_labels,
    score,
    score_anomaly,
    summary,
    summary_anomaly,
)
from app.detect.expected import expected_power
from app.detect.rules import run_all
from app.ml.features import daily_features, day_labels
from app.ml.models import AutoencoderDetector, ForestDetector, to_alarms
from app.simulator.engine import TELEMETRY_COLUMNS
from app.simulator.site import load_site
from app.simulator.weather_source import hourly_weather
from scripts.evaluate_detectors import SIM_DIR, add_bms_error, add_weather_error
from scripts.generate_history import DEFAULT_SITES

MODEL_DIR = REPO_ROOT / "ml" / "models"
REPORT_DIR = REPO_ROOT / "ml" / "reports"


def load(codes: list[str]) -> dict:
    data = {}
    for i, code in enumerate(codes):
        df = pd.read_parquet(SIM_DIR / f"{code}.parquet")
        site = load_site(code)
        hourly, label = hourly_weather(site, df.index[0], df.index[-1] + pd.Timedelta(minutes=5))
        exp = expected_power(site, add_weather_error(hourly, seed=i), label, df.index)
        tel = add_bms_error(df[TELEMETRY_COLUMNS], seed=i)
        x = daily_features(site, tel, exp)
        data[code] = {"site": site, "x": x, "labels": day_labels(df["fault_label"]).reindex(x.index),
                      "events": events_from_labels(df["fault_label"]),
                      "rules": run_all(site, tel, exp), "start": df.index[0]}
        print(f"  {code}: {len(x)} days, {(data[code]['labels'] == '').sum()} clean")
    return data


def cross_validate(data: dict, folds: int, epochs: int) -> dict:
    """Out-of-fold anomaly scores (score / threshold, so > 1 means flagged) for every day."""
    rows = [(code, day) for code, d in data.items() for day in d["x"].index]
    x = np.vstack([d["x"].to_numpy() for d in data.values()])
    clean = np.concatenate([(d["labels"] == "").to_numpy() for d in data.values()])
    days = pd.DatetimeIndex([r[1] for r in rows])
    edges = pd.date_range(days.min(), days.max() + pd.Timedelta(days=1), periods=folds + 1)

    ae_ratio, if_ratio, hints = np.zeros(len(x)), np.zeros(len(x)), [None] * len(x)
    for k in range(folds):
        test = (days >= edges[k]) & (days < edges[k + 1])
        buffer = (days >= edges[k] - pd.Timedelta(days=7)) & (days < edges[k + 1] + pd.Timedelta(days=7))
        train = clean & ~buffer                            # clean days, away from the test block
        t0 = time.time()
        ae = AutoencoderDetector.fit(x[train], epochs=epochs, seed=k)
        forest = ForestDetector.fit(x[train], seed=k)
        ae_ratio[test] = ae.score(x[test]) / ae.threshold
        if_ratio[test] = forest.score(x[test]) / forest.threshold
        for i, h in zip(np.flatnonzero(test), ae.worst_channel(x[test]), strict=True):
            hints[i] = h
        print(f"  fold {k + 1}/{folds}: trained on {train.sum()} clean days, "
              f"tested {test.sum()} days ({time.time() - t0:.0f}s)")

    out = {}
    for code in data:
        m = np.array([r[0] == code for r in rows])
        out[code] = {"days": days[m], "ae": ae_ratio[m], "if": if_ratio[m],
                     "hints": [h for h, keep in zip(hints, m, strict=True) if keep]}
    return out


def chance_recall(data: dict, oof: dict, repeats: int = 20) -> pd.Series:
    """Recall a "model" would get by luck: the same alarms, slid to random other dates.

    Long alarms near frequent faults can overlap them by coincidence; this tells us how much.
    """
    rng = np.random.default_rng(0)
    runs = []
    for _ in range(repeats):
        evs = []
        for code, d in data.items():
            o = oof[code]
            shifted = np.roll(o["ae"], int(rng.integers(30, len(o["ae"]) - 30)))
            ev, _ = score_anomaly(d["events"], to_alarms(o["days"], shifted, 1.0), d["start"])
            evs.append(ev)
        ev = pd.concat(evs)
        runs.append(ev[ev.scored].groupby("kind")["detected"].mean())
    return pd.concat(runs, axis=1).mean(axis=1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sites", nargs="+", default=DEFAULT_SITES)
    parser.add_argument("--folds", type=int, default=4)
    parser.add_argument("--epochs", type=int, default=150)
    args = parser.parse_args()

    print("Building daily features ...")
    data = load(args.sites)
    print("Cross-validating ...")
    oof = cross_validate(data, args.folds, args.epochs)

    results, months = {"rules": [], "autoencoder": [], "forest": []}, 0.0
    alarms_kept = []
    for code, d in data.items():
        o = oof[code]
        months += len(d["x"]) / 30.4
        ev_r, al_r = score(d["events"], d["rules"], d["start"])
        ae_alarms = to_alarms(o["days"], o["ae"], 1.0, o["hints"])
        if_alarms = to_alarms(o["days"], o["if"], 1.0)
        ev_a, al_a = score_anomaly(d["events"], ae_alarms, d["start"])
        ev_f, al_f = score_anomaly(d["events"], if_alarms, d["start"])
        results["rules"].append((ev_r, al_r))
        results["autoencoder"].append((ev_a, al_a))
        results["forest"].append((ev_f, al_f))
        al_a.insert(0, "site", code)
        alarms_kept.append(al_a)

    ev_r = pd.concat(r[0] for r in results["rules"])
    al_r = pd.concat(r[1] for r in results["rules"])
    ev_a = pd.concat(r[0] for r in results["autoencoder"])
    al_a = pd.concat(r[1] for r in results["autoencoder"])
    ev_f = pd.concat(r[0] for r in results["forest"])
    al_f = pd.concat(r[1] for r in results["forest"])

    s_r = summary(ev_r, al_r, months)
    s_a, s_f = summary_anomaly(ev_a, al_a, months), summary_anomaly(ev_f, al_f, months)
    # rules OR autoencoder: an event counts if either caught it
    key = ["kind", "start"]
    both = ev_a.merge(ev_r[[*key, "detected"]], on=key, suffixes=("_ae", "_rules"))
    both["detected"] = both.detected_ae | both.detected_rules
    s_b = both[both.scored].groupby("kind")["detected"].mean()

    table = pd.DataFrame({
        "injected": s_a["injected"],
        "rules": s_r["recall"].reindex(s_a.index),
        "autoencoder": s_a["recall"], "forest": s_f["recall"], "rules+AE": s_b,
        "AE_by_luck": chance_recall(data, oof),
        "AE_delay_h": s_a["median_delay_h"],
    })
    print(f"\n== Recall by fault ({months:.0f} site-months, short-lived faults only)")
    print("   (AE_by_luck = what the same number of alarms would catch at random dates)")
    print(table.round(2).to_string())
    rules_false = int((~al_r.true_alarm).sum())
    print("\nFalse alarms per site-month:  "
          f"rules {rules_false / months:.3f}   "
          f"autoencoder {s_a.attrs['false_per_month']:.3f}   "
          f"forest {s_f.attrs['false_per_month']:.3f}")
    print(f"Autoencoder alarms during long-running problems (weak panels, weak battery): "
          f"{s_a.attrs['background_alarms']}")
    top = al_a[al_a.verdict == "true"]["details"].map(lambda d: d.get("hint")).value_counts()
    print("What the autoencoder pointed at, on real faults: "
          + ", ".join(f"{k} x{v}" for k, v in top.items()))

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    table.to_csv(REPORT_DIR / "anomaly_comparison.csv")
    pd.concat(alarms_kept).to_csv(REPORT_DIR / "autoencoder_alarms.csv", index=False)

    print("\nTraining the final autoencoder on all clean days ...")
    x_all = np.vstack([d["x"][d["labels"] == ""].to_numpy() for d in data.values()])
    final = AutoencoderDetector.fit(x_all, epochs=args.epochs, verbose=True)
    final.save(MODEL_DIR)
    ForestDetector.fit(x_all).save(MODEL_DIR)          # the backup scorer if Modal is unreachable
    print(f"Saved autoencoder + forest to {MODEL_DIR.relative_to(REPO_ROOT)}/ "
          f"(autoencoder threshold {final.threshold:.3f})")


if __name__ == "__main__":
    main()
