"""Score detectors against the answer key (the injected faults).

For each kind of fault:
    recall       share of injected faults that got an alarm of the right kind
    delay        how long from the fault starting to the alarm (median, hours)
    false alarms alarms of that kind that match no injected fault
"""

import numpy as np
import pandas as pd

from app.detect.rules import Alarm

# Gaps shorter than this inside one kind's labels are treated as the same fault
# (e.g. shading is only labelled during its afternoon hours, but it is one problem).
MERGE_GAP = {"overload": pd.Timedelta(minutes=30)}
DEFAULT_GAP = pd.Timedelta(days=2)
GRACE = pd.Timedelta(days=2)            # an alarm this soon after a fault ended still counts

# Detectors that learn the site's normal level first can't judge faults that were already
# there when monitoring started. Such faults are listed but not scored.
NEEDS_BASELINE = {"soiling": pd.Timedelta(days=30)}

# Problems present for months on end. A "something is unusual" alarm during them can't be
# credited to them (it may be about something else), so they are scored by Part A/C only.
PERSISTENT = {"underrated_panel", "battery_fade"}


def events_from_labels(fault_label: pd.Series) -> pd.DataFrame:
    """Injected fault episodes (kind, start, end) from the per-step labels in the parquet."""
    rows = []
    labels = fault_label.dropna()
    kinds = sorted({k for lab in labels for k in lab.split(",")})
    for kind in kinds:
        ts = labels.index[labels.str.contains(kind, regex=False)]
        gap = MERGE_GAP.get(kind, DEFAULT_GAP)
        start = prev = ts[0]
        for t in ts[1:]:
            if t - prev > gap:
                rows.append((kind, start, prev))
                start = t
            prev = t
        rows.append((kind, start, prev))
    return pd.DataFrame(rows, columns=["kind", "start", "end"])


def score(events: pd.DataFrame, alarms: list[Alarm],
          data_start: pd.Timestamp) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (per-event results, per-alarm results)."""
    al = pd.DataFrame([{"kind": a.kind, "start": a.start, "raised_at": a.raised_at, "end": a.end,
                        "target": a.target, "details": a.details} for a in alarms],
                      columns=["kind", "start", "raised_at", "end", "target", "details"])
    al["true_alarm"] = False
    ev = events.copy()
    ev["detected"], ev["delay_h"] = False, np.nan
    ev["scored"] = [not (k in NEEDS_BASELINE and st < data_start + NEEDS_BASELINE[k])
                    for k, st in zip(ev.kind, ev.start, strict=True)]
    for i, e in ev.iterrows():
        cand = al[(al.kind == e.kind) & (al.raised_at >= e.start - pd.Timedelta(hours=1))
                  & (al.start <= e.end + GRACE)]
        if len(cand):
            ev.loc[i, "detected"] = True
            ev.loc[i, "delay_h"] = max(0.0, (cand.raised_at.min() - e.start) / pd.Timedelta(hours=1))
            al.loc[cand.index, "true_alarm"] = True
    return ev, al


def summary(ev: pd.DataFrame, al: pd.DataFrame, months: float) -> pd.DataFrame:
    kinds = sorted(set(ev.kind) | set(al.kind))
    rows = []
    for k in kinds:
        e, a = ev[(ev.kind == k) & ev.scored], al[al.kind == k]
        rows.append({
            "fault": k, "injected": len(e), "caught": int(e.detected.sum()),
            "not_scored": int(((ev.kind == k) & ~ev.scored).sum()),
            "recall": e.detected.mean() if len(e) else np.nan,
            "median_delay_h": e.delay_h.median() if e.detected.any() else np.nan,
            "false_alarms": int((~a.true_alarm).sum()),
            "false_per_month": (~a.true_alarm).sum() / months,
        })
    return pd.DataFrame(rows).set_index("fault")


def score_anomaly(events: pd.DataFrame, alarms: list[Alarm],
                  data_start: pd.Timestamp) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Score kind-free alarms ("this day is unusual"): any overlapping acute fault is a hit.

    Alarms are labelled 'true' (overlap an acute fault), 'background' (overlap only a long
    persistent condition such as weak panels) or 'false'.
    """
    al = pd.DataFrame([{"start": a.start, "raised_at": a.raised_at, "end": a.end,
                        "details": a.details} for a in alarms],
                      columns=["start", "raised_at", "end", "details"])
    al["verdict"] = "false"
    ev = events[~events.kind.isin(PERSISTENT)].copy()
    ev["detected"], ev["delay_h"] = False, np.nan
    ev["scored"] = [not (k in NEEDS_BASELINE and st < data_start + NEEDS_BASELINE[k])
                    for k, st in zip(ev.kind, ev.start, strict=True)]
    for i, e in ev.iterrows():
        cand = al[(al.raised_at >= e.start - pd.Timedelta(hours=1)) & (al.start <= e.end + GRACE)]
        if len(cand):
            ev.loc[i, "detected"] = True
            ev.loc[i, "delay_h"] = max(0.0, (cand.raised_at.min() - e.start) / pd.Timedelta(hours=1))
            al.loc[cand.index, "verdict"] = "true"
    for _, e in events[events.kind.isin(PERSISTENT)].iterrows():
        hit = (al.verdict == "false") & (al.raised_at >= e.start) & (al.start <= e.end + GRACE)
        al.loc[hit, "verdict"] = "background"
    return ev, al


def summary_anomaly(ev: pd.DataFrame, al: pd.DataFrame, months: float) -> pd.DataFrame:
    rows = []
    for k in sorted(set(ev.kind)):
        e = ev[(ev.kind == k) & ev.scored]
        rows.append({"fault": k, "injected": len(e), "caught": int(e.detected.sum()),
                     "recall": e.detected.mean() if len(e) else np.nan,
                     "median_delay_h": e.delay_h.median() if e.detected.any() else np.nan})
    out = pd.DataFrame(rows).set_index("fault")
    out.attrs["false_alarms"] = int((al.verdict == "false").sum())
    out.attrs["background_alarms"] = int((al.verdict == "background").sum())
    out.attrs["false_per_month"] = (al.verdict == "false").sum() / months
    return out
