"""Fault injection: problems we deliberately put into the virtual inverter.

Each fault is saved in the `injected_faults` table. That gives us an answer key: later we can
check whether SolarDokta's detectors (rules + ML) noticed each problem, and how fast.

Kinds of fault and what they do:
    soiling           dust builds up on the panels (both strings), loss grows day by day until cleaned
    shading           a new obstruction shades one string for a few hours each afternoon
    string_failure    one string produces nothing (blown fuse, loose connector)
    underrated_panel  one string was sold as bigger than it really is (substandard panels)
    battery_fade      a weak cell: battery health drops much faster than normal
    hot_battery_room  battery kept somewhere hot (no ventilation): higher temperature, faster wear
    overload          someone switches on heavy appliances together (e.g. iron + kettle + AC)
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from app.simulator.grid import _seed
from app.simulator.site import SiteConfig

KINDS = ("soiling", "shading", "string_failure", "underrated_panel", "battery_fade",
         "hot_battery_room", "overload")


@dataclass
class Fault:
    kind: str
    start: pd.Timestamp                  # timezone-aware
    end: pd.Timestamp | None = None      # None = still going on
    target: str = "all"                  # "pv1", "pv2" or "all"
    params: dict = field(default_factory=dict)
    id: int | None = None                # row id once saved in the database

    def active_mask(self, idx: pd.DatetimeIndex) -> np.ndarray:
        mask = idx >= self.start
        if self.end is not None:
            mask &= idx < self.end
        return np.asarray(mask)

    def overlaps(self, start: pd.Timestamp, end: pd.Timestamp) -> bool:
        return self.start < end and (self.end is None or self.end > start)

    def to_row(self, site_id: str) -> dict:
        return {
            "site_id": site_id, "kind": self.kind,
            "params": {"target": self.target, **self.params},
            "start_ts": _iso(self.start), "end_ts": _iso(self.end) if self.end is not None else None,
        }

    @staticmethod
    def from_row(r: dict) -> "Fault":
        params = dict(r.get("params") or {})
        target = params.pop("target", "all")
        end = pd.Timestamp(r["end_ts"]) if r.get("end_ts") else None
        return Fault(r["kind"], pd.Timestamp(r["start_ts"]), end, target, params, r.get("id"))


def _iso(ts: pd.Timestamp) -> str:
    return ts.tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Effects:
    """What the active faults do to one stretch of 5-minute steps."""
    pv1_factor: np.ndarray
    pv2_factor: np.ndarray
    extra_load_w: np.ndarray
    room_temp_add: np.ndarray
    fade_per_step: np.ndarray            # extra battery health lost each step
    labels: list[str | None]             # active fault kinds per step, e.g. "soiling,overload"


def effects(faults: list[Fault], idx: pd.DatetimeIndex) -> Effects:
    n = len(idx)
    f = {"pv1": np.ones(n), "pv2": np.ones(n)}
    extra, room, fade = np.zeros(n), np.zeros(n), np.zeros(n)
    labels = [[] for _ in range(n)]

    for flt in faults:
        mask = flt.active_mask(idx)
        if not mask.any():
            continue
        strings = ("pv1", "pv2") if flt.target == "all" else (flt.target,)
        p = flt.params

        if flt.kind == "soiling":
            # loss grows linearly from 0 to max_loss over ramp_days, then stays there
            days_in = (idx - flt.start) / pd.Timedelta(days=1)
            loss = p["max_loss"] * np.clip(np.asarray(days_in) / p["ramp_days"], 0, 1)
            for s in strings:
                f[s] = np.where(mask, f[s] * (1 - loss), f[s])
        elif flt.kind == "shading":
            hour = idx.hour + idx.minute / 60
            mask &= np.asarray((hour >= p["from_hour"]) & (hour < p["from_hour"] + p["hours"]))
            for s in strings:
                f[s] = np.where(mask, f[s] * (1 - p["loss"]), f[s])
        elif flt.kind == "string_failure":
            for s in strings:
                f[s] = np.where(mask, 0.0, f[s])
        elif flt.kind == "underrated_panel":
            for s in strings:
                f[s] = np.where(mask, f[s] * p["factor"], f[s])
        elif flt.kind == "battery_fade":
            fade += np.where(mask, p["soh_per_day"] / 288, 0.0)
        elif flt.kind == "hot_battery_room":
            room += np.where(mask, p["extra_c"], 0.0)
        elif flt.kind == "overload":
            extra += np.where(mask, p["extra_w"], 0.0)
        else:
            raise ValueError(f"Unknown fault kind {flt.kind!r}")

        for i in np.flatnonzero(mask):
            labels[i].append(flt.kind)

    return Effects(f["pv1"], f["pv2"], extra, room, fade,
                   [",".join(sorted(set(x))) if x else None for x in labels])


# ---------- Planning faults for a history run ----------

# Expected number of episodes per site per year, and how long each lasts (days).
RATES = {
    "string_failure": (1.5, (1, 10)),
    "shading": (0.5, (14, 90)),
    "hot_battery_room": (0.5, (14, 60)),
    "overload": (6.0, None),             # single evening events of 10-40 minutes
}

# Problems built into particular sites from the start, so every kind shows up somewhere.
SCENARIOS = {
    "lagos-002": [("underrated_panel", "pv2", {"factor": 0.78})],          # substandard panels
    "lagos-003": [("battery_fade", "all", {"soh_per_day": 0.0004})],       # weak battery cell
}


def plan_faults(site: SiteConfig, start: pd.Timestamp, end: pd.Timestamp, seed: int = 0) -> list[Fault]:
    """A repeatable random set of faults for one site between start and end (local times)."""
    rng = np.random.default_rng(_seed("faults", site.code, seed))
    tz = site.timezone
    start, end = start.tz_convert(tz), end.tz_convert(tz)
    years = (end - start) / pd.Timedelta(days=365)
    strings = list(site.strings)
    faults: list[Fault] = []

    def random_day() -> pd.Timestamp:
        return start.normalize() + pd.Timedelta(days=int(rng.integers(0, max(1, (end - start).days))))

    # Harmattan dust every dry season: starts early December, builds over 4-8 weeks,
    # cleaned some time in February.
    for year in range(start.year - 1, end.year + 1):
        s = pd.Timestamp(f"{year}-12-01", tz=tz) + pd.Timedelta(days=int(rng.integers(0, 15)))
        e = pd.Timestamp(f"{year + 1}-02-01", tz=tz) + pd.Timedelta(days=int(rng.integers(0, 28)))
        if s < end and e > start:
            faults.append(Fault("soiling", s, e, "all",
                                {"max_loss": round(float(rng.uniform(0.12, 0.30)), 3),
                                 "ramp_days": int(rng.integers(28, 56))}))

    for kind, (per_year, dur) in RATES.items():
        for _ in range(rng.poisson(per_year * years)):
            day = random_day()
            if kind == "overload":
                s = day + pd.Timedelta(minutes=int(rng.integers(18 * 12, 22 * 12)) * 5)
                e = s + pd.Timedelta(minutes=5 * int(rng.integers(2, 9)))
                params = {"extra_w": round(site.inverter_kw * 1000 * float(rng.uniform(0.9, 1.3)))}
                faults.append(Fault(kind, s, e, "all", params))
                continue
            s = day + pd.Timedelta(hours=float(rng.uniform(7, 17)))
            e = s + pd.Timedelta(days=float(rng.uniform(*dur)))
            if kind == "string_failure":
                faults.append(Fault(kind, s, e, str(rng.choice(strings))))
            elif kind == "shading":
                faults.append(Fault(kind, s, e, str(rng.choice(strings)),
                                    {"from_hour": round(float(rng.uniform(14, 16)), 2),
                                     "hours": round(float(rng.uniform(1.5, 3)), 2),
                                     "loss": round(float(rng.uniform(0.5, 0.8)), 2)}))
            elif kind == "hot_battery_room":
                faults.append(Fault(kind, s, e, "all", {"extra_c": round(float(rng.uniform(6, 12)), 1)}))

    for kind, target, params in SCENARIOS.get(site.code, []):
        if target in strings or target == "all":
            begins = start if kind == "underrated_panel" else start + (end - start) * 0.3
            faults.append(Fault(kind, begins, None, target, params))

    faults = [f for f in faults if f.overlaps(start, end)]
    return sorted(faults, key=lambda f: f.start)
