"""Turn a site's 5-minute telemetry into one feature row per day, for the anomaly models.

Each day becomes 24 hours x 9 channels = 216 numbers. Everything is scaled by the site's own
size (panel kWp, inverter kW, battery kWh), so one model can learn from all sites together and
can also judge a brand-new site that has no history yet.

Only what a real inverter reports is used, plus the physics "expected solar" as context.
"""

from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

# SiteConfig is only needed for type hints. Importing it for real would pull in the database
# libraries, and this file must stay light enough to run on Modal.
if TYPE_CHECKING:
    from app.simulator.site import SiteConfig

CHANNELS = [
    "pv1",          # string 1 power / its kWp
    "pv2",          # string 2 power / its kWp
    "pv_expected",  # what physics expected from both strings / total kWp (weather context)
    "load",         # house power / inverter rating
    "soc",          # battery charge level 0-1
    "batt_power",   # battery power / battery kWh (+ charging)
    "batt_heat",    # battery temperature minus outdoor temperature, / 10 C
    "grid_on",      # share of the hour NEPA was on
    "grid_power",   # NEPA power / inverter rating
]
HOURS = 24
FEATURES = [f"{c}_{h:02d}" for c in CHANNELS for h in range(HOURS)]


def daily_features(site: "SiteConfig", tel: pd.DataFrame, exp: pd.DataFrame) -> pd.DataFrame:
    """One row per complete local day (index = day), columns = FEATURES."""
    kwp1 = max(site.pv1_kwp, 1e-6) * 1000
    kwp2 = max(site.pv2_kwp, 1e-6) * 1000
    inv = site.inverter_kw * 1000
    ch = pd.DataFrame({
        "pv1": tel["pv1_w"] / kwp1,
        "pv2": tel["pv2_w"] / kwp2 if site.pv2_kwp > 0 else 0.0,
        "pv_expected": (exp["pv1_exp_w"] + exp["pv2_exp_w"]) / (kwp1 + kwp2),
        "load": tel["load_w"] / inv,
        "soc": tel["batt_soc"],
        "batt_power": tel["batt_v"] * tel["batt_a"] / (site.battery_kwh * 1000),
        "batt_heat": (tel["batt_temp_c"] - exp["outdoor_temp_c"]) / 10,
        "grid_on": (tel["grid_v"] > 150).astype(float),
        "grid_power": tel["grid_w"] / inv,
    }, index=tel.index)[CHANNELS]

    hourly = ch.resample("1h").mean()
    counts = ch["soc"].resample("1D").count()
    full_days = counts.index[counts == 288]                  # skip partial days
    hourly = hourly[hourly.index.normalize().isin(full_days)]

    day = hourly.index.normalize()
    hour = hourly.index.hour
    rows = {}
    for c in CHANNELS:
        wide = pd.DataFrame({"day": day, "hour": hour, "v": hourly[c].to_numpy()}) \
            .pivot(index="day", columns="hour", values="v")
        wide.columns = [f"{c}_{h:02d}" for h in wide.columns]
        rows[c] = wide
    out = pd.concat(rows.values(), axis=1).reindex(columns=FEATURES)
    return out.dropna().astype(np.float32)


def day_labels(fault_label: pd.Series) -> pd.Series:
    """Which injected faults touched each day ('' = a clean day). Used only for training
    selection and scoring, never as a model input."""
    lab = fault_label.fillna("")
    return lab.groupby(lab.index.normalize()).agg(
        lambda s: ",".join(sorted({k for x in s if x for k in x.split(",")})))
