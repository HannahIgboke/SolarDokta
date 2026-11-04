"""House usage (load) model: which appliances are on, every 5 minutes, for one local day.

Each day is simulated from a seed made from the site code and the date, so the same day always
produces the same usage (needed later when the pipeline re-runs a 5-minute tick).
Hot days make fridges work harder and air conditioners and fans more likely to be used.
"""

import hashlib

import numpy as np
import pandas as pd

from app.simulator.appliances import PROFILES, Appliance
from app.simulator.site import SiteConfig

STEPS_PER_DAY = 288          # 24 h x 12 five-minute steps
STEPS_PER_HOUR = 12


def load_seed(site_code: str, day: pd.Timestamp) -> int:
    digest = hashlib.sha256(f"load:{site_code}:{day:%Y-%m-%d}".encode()).digest()
    return int.from_bytes(digest[:4], "little")


def _window_mask(windows, jitter_steps: np.ndarray | None = None) -> np.ndarray:
    """Boolean mask of the steps inside the windows. Windows like (21, 6) wrap past midnight."""
    mask = np.zeros(STEPS_PER_DAY, dtype=bool)
    for i, (h0, h1) in enumerate(windows):
        s0, s1 = h0 * STEPS_PER_HOUR, h1 * STEPS_PER_HOUR
        if jitter_steps is not None:
            s0, s1 = s0 + int(jitter_steps[2 * i]), s1 + int(jitter_steps[2 * i + 1])
        s0, s1 = s0 % STEPS_PER_DAY, s1 % STEPS_PER_DAY if s1 != STEPS_PER_DAY else STEPS_PER_DAY
        if s0 < s1:
            mask[s0:s1] = True
        elif s0 > s1:                                    # wraps past midnight
            mask[s0:] = True
            mask[:s1] = True
        elif h0 != h1:                                   # full day, e.g. (0, 24)
            mask[:] = True
    return mask


def _runs_today(app: Appliance, day: pd.Timestamp) -> bool:
    if app.days == "weekdays":
        return day.dayofweek < 5
    if app.days == "not_sunday":
        return day.dayofweek != 6
    return True


def _compressor(n_on: int, duty: float, rng: np.random.Generator) -> np.ndarray:
    """On/off pattern for a fridge or AC compressor: runs of about 15 minutes on."""
    duty = float(np.clip(duty, 0.05, 0.95))
    out = np.zeros(n_on, dtype=bool)
    i = int(rng.integers(0, 6))
    while i < n_on:
        on = int(rng.integers(2, 5))                     # 10 to 20 minutes on
        off = max(1, round(on * (1 - duty) / duty * rng.uniform(0.7, 1.3)))
        out[i:i + on] = True
        i += on + off
    return out


def simulate_load(site: SiteConfig, day: pd.Timestamp, temp_c: np.ndarray | None = None,
                  seed: int | None = None) -> pd.DataFrame:
    """Watts per appliance and in total, for each 5-minute step of one local day.

    day: local date (time part ignored). temp_c: 288 outdoor temperatures (C), or None for 28 C.
    Returns a DataFrame indexed by local time, with one column per appliance and `load_w`.
    """
    day = pd.Timestamp(day).normalize()
    if day.tzinfo is None:
        day = day.tz_localize(site.timezone)
    idx = pd.date_range(day, periods=STEPS_PER_DAY, freq="5min")
    temp = np.full(STEPS_PER_DAY, 28.0) if temp_c is None else np.asarray(temp_c, dtype=float)
    day_max = float(np.nanmax(temp))
    rng = np.random.default_rng(load_seed(site.code, day) if seed is None else seed)

    profile = PROFILES[site.load_profile]
    out = pd.DataFrame(index=idx)
    for app in profile.appliances:
        watts = np.zeros(STEPS_PER_DAY)
        if not _runs_today(app, day):
            out[app.name] = watts
            continue

        if app.kind == "always":
            on = _window_mask(app.windows)

        elif app.kind == "cycle":
            hot_extra = 0.01 * np.clip(temp - 25, 0, None).mean()    # +1% duty per degree over 25 C
            on = _compressor(STEPS_PER_DAY, app.duty + hot_extra, rng)

        elif app.kind == "window":
            used = rng.random() < app.prob
            jitter = rng.integers(-6, 7, size=2 * len(app.windows))   # +/- 30 minutes
            on = _window_mask(app.windows, jitter) if used else np.zeros(STEPS_PER_DAY, bool)

        elif app.kind == "cooling":
            p = np.clip(app.prob + 0.07 * (day_max - 31), 0.05, 0.95)  # hotter day, more AC
            used = rng.random() < p
            jitter = rng.integers(-6, 7, size=2 * len(app.windows))
            window = _window_mask(app.windows, jitter) if used else np.zeros(STEPS_PER_DAY, bool)
            on = window & _compressor(STEPS_PER_DAY, app.duty, rng)

        elif app.kind == "event":
            on = np.zeros(STEPS_PER_DAY, dtype=bool)
            allowed = np.flatnonzero(_window_mask(app.windows))
            for _ in range(rng.poisson(app.uses_per_day)):
                start = int(rng.choice(allowed))
                length = round(rng.uniform(*app.minutes) / 5) or 1
                on[start:start + length] = True
        else:
            raise ValueError(f"Unknown appliance kind {app.kind!r} for {app.name}")

        # Each unit of a multi-unit appliance (e.g. 3 fans) is on with slight variation.
        units = sum(on & (rng.random(STEPS_PER_DAY) < 0.97) for _ in range(app.qty)) if app.qty > 1 else on
        watts = np.asarray(units, dtype=float) * app.watts * rng.uniform(0.9, 1.1)
        out[app.name] = watts

    out["load_w"] = out.sum(axis=1)
    return out
