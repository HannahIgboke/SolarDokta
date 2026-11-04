"""Physics-and-rules detectors: each one looks for one kind of problem in the telemetry.

They only use what a real inverter reports (TELEMETRY_COLUMNS), plus weather and the site's
setup. Each produces Alarms: when the problem seems to have started, when we would have told
someone (raised_at), and when it went away.

Ideas used:
- Comparing the two strings with each other cancels out the weather and curtailment (both
  strings are cut back by the same share), so a dead, weak or shaded string stands out clearly.
- Problems that hit BOTH strings (dust) need the physics model: actual vs expected power, but
  only at moments the inverter was not throwing solar away (battery not full, not at its limit).
- To avoid false alarms, evidence must persist (e.g. 3 days in a row) before an alarm is raised,
  and the "all clear" also needs a few good readings in a row.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from app.simulator.battery import CHEMISTRIES
from app.simulator.site import SiteConfig

FAULT, OK, UNKNOWN = 1, 0, -1


@dataclass
class Alarm:
    kind: str
    start: pd.Timestamp          # first evidence of the problem
    raised_at: pd.Timestamp      # when we would alert (after enough evidence)
    end: pd.Timestamp | None     # when it cleared (None = still going)
    target: str = "all"
    details: dict = field(default_factory=dict)


def episodes(evidence: pd.Series, start_after: int, end_after: int) -> list[tuple]:
    """Turn a series of FAULT/OK/UNKNOWN evidence into (start, raised_at, end) episodes.

    An episode is raised after `start_after` FAULT readings in a row (UNKNOWN readings in
    between are ignored) and ends after `end_after` OK readings in a row.
    """
    out, run_start, n_fault, n_ok, active = [], None, 0, 0, None
    for ts, e in evidence.items():
        if e == UNKNOWN:
            continue
        if active is None:
            if e == FAULT:
                run_start = run_start or ts
                n_fault += 1
                if n_fault >= start_after:
                    active = [run_start, ts, None]
            else:
                run_start, n_fault = None, 0
        else:
            n_ok = n_ok + 1 if e == OK else 0
            if n_ok >= end_after:
                active[2] = ts
                out.append(tuple(active))
                active, run_start, n_fault, n_ok = None, None, 0, 0
    if active is not None:
        out.append(tuple(active))
    return out


def _alarms(kind: str, eps: Iterable[tuple], target: str = "all", **details) -> list[Alarm]:
    return [Alarm(kind, s, r, e, target, dict(details)) for s, r, e in eps]


# ---------- 1. a dead string (5-minute data, fast) ----------

def dead_string(site: SiteConfig, tel: pd.DataFrame, exp: pd.DataFrame) -> list[Alarm]:
    alarms = []
    for s, o in (("pv1", "pv2"), ("pv2", "pv1")):
        kwp = getattr(site, f"{s}_kwp")
        if kwp <= 0 or getattr(site, f"{o}_kwp") <= 0:
            continue
        sunny = exp[f"{s}_exp_w"] > 0.15 * kwp * 1000            # this string should be working
        other_working = tel[f"{o}_w"] > 50
        dead = sunny & other_working & (tel[f"{s}_w"] < 5)
        fine = sunny & other_working & ~dead
        ev = pd.Series(np.select([dead, fine], [FAULT, OK], UNKNOWN), index=tel.index)
        alarms += _alarms("string_failure", episodes(ev, start_after=3, end_after=3), target=s)
    return alarms


# ---------- 2. a weak string (substandard panels) and 3. afternoon shading ----------

def _hourly_ratio(site: SiteConfig, tel: pd.DataFrame, exp: pd.DataFrame) -> pd.DataFrame:
    """Hourly pv2/pv1 ratio, per kWp, divided by what physics expects (1.0 = healthy)."""
    h = pd.DataFrame({"pv1": tel["pv1_w"], "pv2": tel["pv2_w"],
                      "e1": exp["pv1_exp_w"], "e2": exp["pv2_exp_w"]}).resample("1h").mean()
    # enough signal on one string, the other not dead (dead strings have their own detector)
    valid = (np.maximum(h.pv1, h.pv2) > 60) & (np.minimum(h.pv1, h.pv2) > 5) \
        & (h.e1 > 0.15 * site.pv1_kwp * 1000) & (h.e2 > 0.15 * site.pv2_kwp * 1000)
    q = (h.pv2 / h.pv1) / (h.e2 / h.e1)
    return pd.DataFrame({"q": q.where(valid), "hour": h.index.hour}, index=h.index)


def weak_string(site: SiteConfig, tel: pd.DataFrame, exp: pd.DataFrame) -> list[Alarm]:
    if site.pv1_kwp <= 0 or site.pv2_kwp <= 0:
        return []
    r = _hourly_ratio(site, tel, exp)
    mid = r[(r.hour >= 10) & (r.hour < 14)]["q"]
    daily = np.log(mid.resample("1D").median())               # log ratio: 0 = equal strings
    ev = pd.Series(np.select([daily.abs() > np.log(1 / 0.88), daily.abs() < np.log(1 / 0.95)],
                             [FAULT, OK], UNKNOWN), index=daily.index)
    ev[daily.isna()] = UNKNOWN
    eps = episodes(ev, start_after=3, end_after=3)
    alarms = []
    for s, raised, e in eps:
        window = daily.loc[s:raised]
        weaker = "pv2" if window.median() < 0 else "pv1"
        ratio = float(np.exp(-abs(window.median())))
        alarms += _alarms("underrated_panel", [(s, raised + pd.Timedelta(days=1), e)],
                          target=weaker, output_vs_rated=round(ratio, 2))
    return alarms


def shading(site: SiteConfig, tel: pd.DataFrame, exp: pd.DataFrame) -> list[Alarm]:
    """One string drops sharply against the other at the same hours (outside midday) each day."""
    if site.pv1_kwp <= 0 or site.pv2_kwp <= 0:
        return []
    r = _hourly_ratio(site, tel, exp)
    mid = r[(r.hour >= 10) & (r.hour < 14)]["q"].resample("1D").median()
    r["dev"] = np.log(r["q"] / mid.reindex(r.index.normalize()).to_numpy())   # vs today's midday
    edge = r[(r.hour < 10) | (r.hour >= 14)]
    shaded = (edge["dev"].abs() > np.log(1 / 0.6)).resample("1D").sum()
    seen = edge["dev"].notna().resample("1D").sum()
    ev = pd.Series(np.select([shaded >= 1, seen >= 2], [FAULT, OK], UNKNOWN), index=shaded.index)
    alarms = []
    for s, raised, e in episodes(ev, start_after=3, end_after=3):
        hit = edge.loc[s:raised + pd.Timedelta(days=1)]
        hit = hit[hit["dev"].abs() > np.log(1 / 0.6)]
        target = "pv2" if hit["dev"].median() < 0 else "pv1"
        hours = sorted({int(h) for h in hit["hour"]})
        alarms += _alarms("shading", [(s, raised + pd.Timedelta(days=1), e)], target=target,
                          hours=hours)
    return alarms


# ---------- 4. dust on the panels (both strings, physics model) ----------

def daily_performance(site: SiteConfig, tel: pd.DataFrame, exp: pd.DataFrame) -> pd.DataFrame:
    """Per day and string: performance ratio (actual / expected solar), measured only while no
    solar was being thrown away. Columns pr_pv1, pr_pv2, usable_steps. Saved daily in the
    database (health_daily), because the dust check needs months of these."""
    chem = CHEMISTRIES[site.battery_chemistry]
    batt_w = tel["batt_v"] * tel["batt_a"]
    # Moments when no solar was thrown away: the battery was taking power but below its limit
    # (so it could have taken more), or the battery was helping the house (solar all used).
    # Uses battery power, not the charge-level gauge, because gauges drift.
    limit = 0.8 * chem.c_rate * site.battery_kwh * 1000
    absorbing = (((batt_w > 50) & (batt_w < limit)) | (batt_w < -50)) & tel["fault_code"].isna()
    out = pd.DataFrame(index=tel["batt_v"].resample("1D").count().index)
    steps = []
    for s in ("pv1", "pv2"):
        kwp = getattr(site, f"{s}_kwp")
        if kwp <= 0:
            out[f"pr_{s}"] = np.nan
            continue
        ok = absorbing & (exp[f"{s}_exp_w"] > 0.10 * kwp * 1000)
        act = tel[f"{s}_w"].where(ok).resample("1D").sum()
        expd = exp[f"{s}_exp_w"].where(ok).resample("1D").sum()
        n = ok.resample("1D").sum()
        out[f"pr_{s}"] = (act / expd).where(n >= 24)           # at least 2 hours of usable data
        steps.append(n)
    out["usable_steps"] = pd.concat(steps, axis=1).min(axis=1) if steps else 0
    return out


def soiling_from_daily(daily: pd.DataFrame) -> list[Alarm]:
    """Dust alarm from the daily performance table (see daily_performance)."""
    strings = daily[["pr_pv1", "pr_pv2"]].dropna(axis=1, how="all")
    day_pr = strings.max(axis=1, skipna=False)                  # dust hits both; take the better one

    clean, evidence, ratios = [], {}, {}
    active = False
    for day, v in day_pr.items():
        if np.isnan(v):
            evidence[day] = UNKNOWN
            continue
        if len(clean) >= 14:
            recent = day_pr.loc[:day].dropna().tail(7).median()      # last week, smooths noise
            ratio = recent / np.median(clean[-60:])                   # vs the usual clean level
            ratios[day] = ratio
            evidence[day] = FAULT if ratio < 0.88 else OK if ratio > 0.94 else UNKNOWN
            active = evidence[day] == FAULT or (active and evidence[day] != OK)
        else:
            evidence[day] = UNKNOWN
        if not active:
            clean.append(v)                                     # only learn from clean days
    ev = pd.Series(evidence, dtype=float)
    alarms = []
    for s, raised, e in episodes(ev, start_after=3, end_after=3):
        loss = 1 - min(ratios[d] for d in ratios if s <= d <= raised)
        alarms += _alarms("soiling", [(s, raised + pd.Timedelta(days=1), e)], loss=round(loss, 2))
    return alarms


def soiling(site: SiteConfig, tel: pd.DataFrame, exp: pd.DataFrame) -> list[Alarm]:
    """Daily performance ratio (actual / expected) against the site's own recent clean level."""
    return soiling_from_daily(daily_performance(site, tel, exp))


# ---------- 5. battery kept somewhere too hot ----------

def daily_batt_heat(tel: pd.DataFrame, exp: pd.DataFrame) -> pd.Series:
    """Battery temperature minus outdoor temperature, daily mean (C)."""
    return (tel["batt_temp_c"] - exp["outdoor_temp_c"]).resample("1D").mean()


def hot_battery(site: SiteConfig, tel: pd.DataFrame, exp: pd.DataFrame) -> list[Alarm]:
    excess = daily_batt_heat(tel, exp)
    ev = pd.Series(np.select([excess > 6.5, excess < 4.5], [FAULT, OK], UNKNOWN), index=excess.index)
    ev[excess.isna()] = UNKNOWN
    return [Alarm("hot_battery_room", s, r + pd.Timedelta(days=1), e,
                  details={"above_outdoor_c": round(float(excess.loc[s:r].mean()), 1)})
            for s, r, e in episodes(ev, start_after=2, end_after=2)]


# ---------- 6. overload: too much switched on at once ----------

def overload(site: SiteConfig, tel: pd.DataFrame, exp: pd.DataFrame) -> list[Alarm]:
    limit = site.inverter_kw * 1000
    hit = (tel["fault_code"] == "OVERLOAD") | (tel["load_w"] > 0.95 * limit)
    ev = pd.Series(np.where(hit, FAULT, OK), index=tel.index)
    return [Alarm("overload", s, r, e, details={"inverter_w": limit})
            for s, r, e in episodes(ev, start_after=1, end_after=6)]


# ---------- 7. the battery ran empty (the inverter reports it) ----------

def battery_ran_out(site: SiteConfig, tel: pd.DataFrame, exp: pd.DataFrame) -> list[Alarm]:
    """Not a fault in the equipment, but something the customer wants to hear about (and a hint
    that usage is too high for the system). Live only: not part of the injected-fault scoring."""
    hit = tel["fault_code"] == "LOW_BATTERY"
    ev = pd.Series(np.where(hit, FAULT, OK), index=tel.index)
    return [Alarm("battery_ran_out", s, r, e,
                  details={"blackout_minutes": int(hit.loc[s:e if e is not None else None].sum() * 5)})
            for s, r, e in episodes(ev, start_after=1, end_after=12)]


DETECTORS = [dead_string, weak_string, shading, soiling, hot_battery, overload]


def run_all(site: SiteConfig, tel: pd.DataFrame, exp: pd.DataFrame) -> list[Alarm]:
    from app.detect.battery import (
        battery_fade,  # imported here to avoid a circular import
    )

    alarms = []
    for det in [*DETECTORS, battery_fade]:
        alarms += det(site, tel, exp)
    return sorted(alarms, key=lambda a: a.raised_at)
