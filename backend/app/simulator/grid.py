"""NEPA (grid) model: when grid power is on or off, every 5 minutes.

Grid supply alternates between "on" and "off" spells of random length. The average hours of
supply per day depend on the tariff band. On rare days the whole city loses power for many hours
(a grid collapse), and every site in that city is hit at the same time.

The state at the end of a run (on/off and how long the current spell still lasts) is returned,
so the next run continues seamlessly (needed for the 5-minute ticks in Part D).

Grid conditions: the band figures describe a normal period. When supply gets worse for a whole
city (e.g. Lagos since mid-October 2026, when national generation crashed), a "grid condition"
overrides them for a date range: hours of light per day and typical outage length. Conditions
live in the grid_conditions table (editable with scripts/set_grid.py); DEFAULT_CONDITIONS is used
until that table exists or when working offline.
"""

import hashlib
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from datetime import date

import numpy as np
import pandas as pd

from app.simulator.site import SiteConfig

STEP_MIN = 5

# Assumptions (adjust as real data comes in). Hours of supply actually delivered per day are
# below the band's promise; mean outage length grows for lower bands.
BAND_HOURS = {"A": 18.0, "B": 13.0, "C": 9.0, "D": 6.0, "E": 3.0}
BAND_MEAN_OUTAGE_H = {"A": 1.2, "B": 2.0, "C": 3.0, "D": 4.0, "E": 6.0}
COLLAPSE_PROB_PER_DAY = 0.01          # about 3-4 city-wide collapses a year
COLLAPSE_HOURS = (4, 16)
NOMINAL_V = 230.0


@dataclass(frozen=True)
class GridCondition:
    city: str
    starts: date
    ends: date | None                 # None = still going on
    hours_per_day: float              # hours of light a site gets per day, on average
    mean_outage_h: float              # typical length of one outage
    note: str = ""

    def covers(self, city: str, day: date) -> bool:
        return self.city == city and self.starts <= day and (self.ends is None or day <= self.ends)


# Assumptions from news reports (Oct 2026); replace with what customers actually experience.
DEFAULT_CONDITIONS = [
    GridCondition("Lagos", date(2026, 10, 10), None, 6.0, 6.0,
                  "Grid allocation shortfall: gas shortages, plants offline, line trips"),
    GridCondition("Lagos", date(2026, 10, 18), date(2026, 10, 21), 1.5, 14.0,
                  "Generation crashed to under 500 MW (19 Oct)"),
    GridCondition("Port Harcourt", date(2026, 10, 12), None, 8.0, 4.0,
                  "Poor supply; Alaoji-Afam line outage"),
    GridCondition("Port Harcourt", date(2026, 10, 19), date(2026, 10, 20), 2.0, 12.0,
                  "National generation crash"),
]
_conditions: list[GridCondition] = list(DEFAULT_CONDITIONS)


def set_conditions(conditions: list[GridCondition] | None) -> None:
    """Use these conditions from now on (None or empty = the defaults above)."""
    global _conditions
    _conditions = list(conditions) if conditions else list(DEFAULT_CONDITIONS)


# A what-if test can pretend NEPA gives N hours a day, for its own run only (other requests and
# the 5-minute tick don't see it, because a ContextVar is private to the code that set it).
what_if_hours: ContextVar[GridCondition | None] = ContextVar("what_if_hours", default=None)


def supply(site: SiteConfig, day: pd.Timestamp) -> tuple[float, float, GridCondition | None]:
    """(hours of light per day, mean outage hours, the condition used) for this site and day.
    When conditions overlap, the one that started last wins (e.g. a crash inside a bad month)."""
    if (forced := what_if_hours.get()) is not None:
        return forced.hours_per_day, forced.mean_outage_h, forced
    d = pd.Timestamp(day).date()
    matching = [c for c in _conditions if c.covers(site.city, d)]
    if matching:
        c = max(matching, key=lambda c: c.starts)
        return c.hours_per_day, c.mean_outage_h, c
    return BAND_HOURS[site.tariff_band], BAND_MEAN_OUTAGE_H[site.tariff_band], None


@dataclass
class GridState:
    on: bool = True
    steps_left: int = 0               # steps remaining in the current on/off spell

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict | None) -> "GridState":
        return GridState(**d) if d else GridState()


def _seed(*parts) -> int:
    digest = hashlib.sha256(":".join(str(p) for p in parts).encode()).digest()
    return int.from_bytes(digest[:4], "little")


def _spell_steps(rng: np.random.Generator, mean_hours: float) -> int:
    """Random spell length (exponential, at least 10 minutes)."""
    return max(2, round(rng.exponential(mean_hours) * 60 / STEP_MIN))


def _collapse_mask(site: SiteConfig, day: pd.Timestamp) -> np.ndarray:
    """Steps of a city-wide collapse on this local day (same for all sites in the city)."""
    rng = np.random.default_rng(_seed("collapse", site.city, f"{day:%Y-%m-%d}"))
    mask = np.zeros(288, dtype=bool)
    if rng.random() < COLLAPSE_PROB_PER_DAY:
        start = int(rng.integers(0, 288))
        mask[start:start + int(rng.uniform(*COLLAPSE_HOURS) * 12)] = True
    return mask


def simulate_grid(site: SiteConfig, day: pd.Timestamp,
                  state: GridState | None = None) -> tuple[pd.DataFrame, GridState]:
    """Grid on/off and voltage for each 5-minute step of one local day.

    Returns (DataFrame indexed by local time with grid_on and grid_v, end-of-day state).
    """
    day = pd.Timestamp(day).normalize()
    if day.tzinfo is None:
        day = day.tz_localize(site.timezone)
    idx = pd.date_range(day, periods=288, freq=f"{STEP_MIN}min")
    rng = np.random.default_rng(_seed("grid", site.code, f"{day:%Y-%m-%d}"))

    hours_on, mean_off, _ = supply(site, day)
    hours_on = min(max(hours_on, 0.1), 23.9)
    mean_on = mean_off * hours_on / (24 - hours_on)      # keeps the long-run share of hours

    if state is None:                                    # very first day: random starting point
        first_on = bool(rng.random() < hours_on / 24)
        st = GridState(on=first_on, steps_left=_spell_steps(rng, mean_on if first_on else mean_off))
    else:
        st = GridState(**asdict(state))

    on = np.zeros(288, dtype=bool)
    for i in range(288):
        if st.steps_left <= 0:                           # current spell is over: switch
            st.on = not st.on
            st.steps_left = _spell_steps(rng, mean_on if st.on else mean_off)
        on[i] = st.on
        st.steps_left -= 1

    on &= ~_collapse_mask(site, day)
    # Nigerian grid voltage wanders; low-voltage spells are common.
    volts = np.where(on, NOMINAL_V + rng.normal(-8, 10, 288).clip(-50, 15), 0.0)
    return pd.DataFrame({"grid_on": on, "grid_v": volts.round(1)}, index=idx), st
