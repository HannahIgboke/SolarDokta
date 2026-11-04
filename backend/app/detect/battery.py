"""Battery health from telemetry: how much the battery can really hold, and how fast that falls.

How it works (the way a battery tester does it, but using everyday use instead of a test):
- Find deep discharges, e.g. a night on battery where charge falls from 90% to 50%.
- Energy that came out (volts x amps over time) / drop in charge level = usable capacity.
  Divided by the nameplate kWh (and the battery's efficiency) that gives state of health (SOH).
- Track the estimates over weeks. Normal lithium batteries lose roughly 2-4% a year in Nigerian
  heat. Losing much faster than that points to a weak cell (or abuse: heat, deep cycling).

The "report card" sums it up for the customer/technician, and for warranty or resale.
"""

import numpy as np
import pandas as pd

from app.detect.rules import FAULT, OK, UNKNOWN, Alarm, episodes
from app.simulator.battery import CHEMISTRIES
from app.simulator.site import SiteConfig

STEP_H = 5 / 60
MIN_DROP = 0.30              # only discharges that use at least 30% of the battery
FADE_WINDOW = pd.Timedelta(days=120)  # judge the trend over the last 4 months
MIN_ESTIMATES = 20                     # ...and only with enough deep discharges in them
FADE_ALARM = 0.12            # losing more than 12% health per year = alarm (normal: 2-5%)
FADE_CLEAR = 0.07
HOT_C = 35.0


def capacity_estimates(site: SiteConfig, tel: pd.DataFrame) -> pd.Series:
    """One SOH estimate per deep discharge, indexed by the time the discharge ended."""
    chem = CHEMISTRIES[site.battery_chemistry]
    batt_w = tel["batt_v"] * tel["batt_a"]
    discharging = batt_w < -20
    run = (discharging != discharging.shift()).cumsum()
    soc_before = tel["batt_soc"].shift(1)
    out = {}
    for _, seg in tel[discharging].groupby(run[discharging]):
        if len(seg) < 12:                                    # at least an hour
            continue
        drop = soc_before.loc[seg.index[0]] - seg["batt_soc"].iloc[-1]
        if not drop >= MIN_DROP:
            continue
        energy_kwh = -(batt_w.loc[seg.index].sum()) * STEP_H / 1000
        out[seg.index[-1]] = energy_kwh / (drop * site.battery_kwh * chem.eff_discharge)
    if not out:                      # no deep discharge: still return a time-indexed (empty) series
        return pd.Series(dtype=float, index=pd.DatetimeIndex([], tz=tel.index.tz))
    return pd.Series(out, dtype=float).sort_index()


def _weekly(est: pd.Series) -> pd.Series:
    return est.resample("7D").median().dropna()


def fade_per_year(est: pd.Series) -> float:
    """Health lost per year (positive = getting worse).

    Theil-Sen slope through weekly medians: the median of the slopes between every pair of
    weeks, so a few bad estimates can't drag the line around (unlike ordinary least squares).
    """
    wk = _weekly(est)
    if len(wk) < 4:
        return float("nan")
    t = np.asarray((wk.index - wk.index[0]) / pd.Timedelta(days=365), dtype=float)
    v = wk.to_numpy()
    i, j = np.triu_indices(len(v), k=1)
    return float(-np.median((v[j] - v[i]) / (t[j] - t[i])))


def battery_fade(site: SiteConfig, tel: pd.DataFrame, exp: pd.DataFrame) -> list[Alarm]:
    """Alarm when health falls much faster than normal ageing over the last four months.

    Health is lost slowly (a weak cell costs about 1% a month), and each estimate is a couple of
    percent off, so this needs months of evidence: expect an alarm 3-4 months after the problem
    starts, which is still long before the battery fails or the warranty runs out.
    """
    return battery_fade_from_estimates(capacity_estimates(site, tel), tel.index[-1])


def battery_fade_from_estimates(est: pd.Series, until: pd.Timestamp) -> list[Alarm]:
    """The fade alarm from stored health estimates (the database keeps these for months)."""
    if est.empty:
        return []
    days = pd.date_range(est.index[0].normalize(), until.normalize(), freq="1D")
    evidence, rates = {}, {}
    for d in days:
        window = est.loc[d - FADE_WINDOW:d]
        if len(window) < MIN_ESTIMATES or window.index.min() > d - FADE_WINDOW * 0.8:
            evidence[d] = UNKNOWN
            continue
        rate = fade_per_year(window)
        rates[d] = rate
        evidence[d] = FAULT if rate > FADE_ALARM else OK if rate < FADE_CLEAR else UNKNOWN
    alarms = []
    for s, r, e in episodes(pd.Series(evidence, dtype=float), start_after=14, end_after=7):
        recent = est.loc[r - pd.Timedelta(days=30):r]
        alarms.append(Alarm("battery_fade", s, r + pd.Timedelta(days=1), e, details={
            "fade_per_year": round(rates[r], 3), "soh_now": round(float(recent.median()), 3)}))
    return alarms


def report_card(site: SiteConfig, tel: pd.DataFrame) -> dict:
    """Battery summary for the dashboard, warranty claims and resale."""
    est = capacity_estimates(site, tel)
    batt_w = tel["batt_v"] * tel["batt_a"]
    discharged = float((-batt_w).clip(lower=0).sum() * STEP_H / 1000)
    soh = float(est.loc[est.index[-1] - pd.Timedelta(days=30):].median()) if len(est) else float("nan")
    recent = est.loc[est.index[-1] - FADE_WINDOW:] if len(est) else est
    rate = fade_per_year(recent) if len(est) else float("nan")
    if soh <= 0.80:
        years_to_80 = 0.0                                    # already at/below the warranty line
    elif rate and rate > 0:
        years_to_80 = (soh - 0.80) / rate
    else:
        years_to_80 = float("nan")                           # not measurably fading

    return {
        "site": site.code,
        "chemistry": site.battery_chemistry,
        "nameplate_kwh": site.battery_kwh,
        "soh_estimate": round(soh, 3),
        "usable_kwh_now": round(soh * site.battery_kwh, 1),
        "fade_per_year": round(rate, 3),
        "trend_confidence": "good" if len(recent) >= MIN_ESTIMATES else "low (few deep discharges)",
        "years_to_80pct": round(years_to_80, 1),
        "equivalent_full_cycles": round(discharged / site.battery_kwh),
        "share_of_time_above_35C": round(float((tel["batt_temp_c"] > HOT_C).mean()), 3),
        "deep_discharges_measured": len(est),
    }
