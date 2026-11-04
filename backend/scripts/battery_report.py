"""Battery report card for each site, and how close the health estimate is to the truth.

The simulator knows each battery's true health (the `soh` column); the estimator only sees the
telemetry, with realistic battery-gauge error added. Comparing the two shows how trustworthy
the report card would be on a real system.

Usage (from backend/):
    python -m scripts.battery_report
    python -m scripts.battery_report --sites lagos-003
Saves ml/reports/battery_cards.csv and ml/reports/battery_estimates.csv (for charts).
"""

import argparse

import pandas as pd

from app.config import REPO_ROOT
from app.detect.battery import capacity_estimates, report_card
from app.simulator.engine import TELEMETRY_COLUMNS
from app.simulator.site import load_site
from scripts.evaluate_detectors import SIM_DIR, add_bms_error
from scripts.generate_history import DEFAULT_SITES

REPORT_DIR = REPO_ROOT / "ml" / "reports"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sites", nargs="+", default=DEFAULT_SITES)
    args = parser.parse_args()

    cards, estimates = [], []
    for i, code in enumerate(args.sites):
        df = pd.read_parquet(SIM_DIR / f"{code}.parquet")
        site = load_site(code)
        tel = add_bms_error(df[TELEMETRY_COLUMNS], seed=i)
        est = capacity_estimates(site, tel)
        truth = df["soh"].reindex(est.index)
        card = report_card(site, tel)
        card["true_soh_now"] = round(float(df["soh"].iloc[-1]), 3)
        card["estimate_error_typical"] = round(float((est - truth).abs().median()), 3)
        cards.append(card)
        estimates.append(pd.DataFrame({"site": code, "estimate": est, "true_soh": truth}))

    table = pd.DataFrame(cards).set_index("site")
    print("\nBattery report cards (estimated from telemetry; true values from the simulator):\n")
    print(table.T.to_string())
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    table.to_csv(REPORT_DIR / "battery_cards.csv")
    pd.concat(estimates).rename_axis("ts").to_csv(REPORT_DIR / "battery_estimates.csv")
    print(f"\nSaved to {REPORT_DIR.relative_to(REPO_ROOT)}/")


if __name__ == "__main__":
    main()
