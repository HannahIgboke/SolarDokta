"""The virtual inverter: from weather to telemetry, for any stretch of time.

    solar (pv.py) + house usage (load.py) + NEPA (grid.py) + faults (faults.py)
    -> inverter logic (dispatch.py) -> battery (battery.py) -> telemetry rows

One function, `simulate_window`, does the work. It is used two ways:
- history: simulate a year or two in one go (generate_history script)
- ticks: every 5 minutes, simulate just the steps since the last reading (tick.py)

Both give exactly the same numbers, because each day's solar, usage and NEPA pattern is fixed
by seeds (site + date), and the battery/inverter state is carried from step to step. SimState
holds everything needed to carry on later: battery, inverter, and the NEPA state at the start
of the current day.
"""

from dataclasses import dataclass, field

import pandas as pd

from app.simulator import dispatch
from app.simulator.battery import BatteryState
from app.simulator.dispatch import InverterState
from app.simulator.faults import Fault, effects
from app.simulator.grid import GridState, simulate_grid
from app.simulator.load import simulate_load
from app.simulator.pv import day_seed, pv_power, spread_hourly_ghi
from app.simulator.site import SiteConfig

ROOM_OFFSET_C = 2.0     # battery rooms/enclosures run a little warmer than outside air
STEP = pd.Timedelta(minutes=5)

TELEMETRY_COLUMNS = ["pv1_w", "pv2_w", "pv_v", "batt_soc", "batt_v", "batt_a", "batt_temp_c",
                     "load_w", "grid_v", "grid_w", "inv_temp_c", "fault_code"]


@dataclass
class SimState:
    battery: BatteryState = field(default_factory=BatteryState)
    inverter: InverterState = field(default_factory=InverterState)
    day: str | None = None               # local date (YYYY-MM-DD) that day_grid belongs to
    day_grid: GridState | None = None    # NEPA state at the start of that day

    def to_dict(self) -> dict:
        return {"battery": self.battery.to_dict(),
                "inverter": {"trip_left": self.inverter.trip_left, "locked": self.inverter.locked},
                "day": self.day,
                "day_grid": self.day_grid.to_dict() if self.day_grid else None}

    @staticmethod
    def from_dict(d: dict | None) -> "SimState":
        if not d:
            return SimState()
        return SimState(BatteryState.from_dict(d.get("battery")),
                        InverterState(**d["inverter"]) if d.get("inverter") else InverterState(),
                        d.get("day"),
                        GridState.from_dict(d["day_grid"]) if d.get("day_grid") else None)


def _local_day(site: SiteConfig, day) -> pd.Timestamp:
    day = pd.Timestamp(day)
    day = day.tz_localize(site.timezone) if day.tzinfo is None else day.tz_convert(site.timezone)
    return day.normalize()


def day_inputs(site: SiteConfig, day: pd.Timestamp, hourly: pd.DataFrame, label: str,
               grid_start: GridState | None, faults: list[Fault] | None = None
               ) -> tuple[pd.DataFrame, GridState]:
    """Everything outside the inverter for one local day (288 steps), with faults applied.

    Returns (inputs frame incl. fault labels and extra battery wear, NEPA state at day end).
    """
    day = _local_day(site, day)
    start, end = day.tz_convert("UTC"), (day + pd.Timedelta(days=1)).tz_convert("UTC")

    w5 = spread_hourly_ghi(hourly, site, start, end, label=label, seed=day_seed(site.code, day))
    pv = pv_power(w5, site).tz_convert(site.timezone)
    temp = w5["temp_c"].tz_convert(site.timezone)
    load = simulate_load(site, day, temp.to_numpy())
    grid, grid_end = simulate_grid(site, day, grid_start)

    fx = effects(faults or [], pv.index)
    frame = pd.DataFrame({
        "pv1_w": pv["pv1_w"] * fx.pv1_factor, "pv2_w": pv["pv2_w"] * fx.pv2_factor,
        "pv1_v": pv["pv1_v"].where(fx.pv1_factor > 0, 0.0),
        "pv2_v": pv["pv2_v"].where(fx.pv2_factor > 0, 0.0),
        "load_w": load["load_w"] + fx.extra_load_w,
        "grid_on": grid["grid_on"], "grid_v": grid["grid_v"],
        "room_temp_c": temp + ROOM_OFFSET_C + fx.room_temp_add,
        "outdoor_temp_c": temp,
        "fault_label": fx.labels,
        "extra_fade": fx.fade_per_step,
    })
    return frame, grid_end


def simulate_window(site: SiteConfig, after: pd.Timestamp, until: pd.Timestamp,
                    hourly: pd.DataFrame, label: str, state: SimState | None = None,
                    faults: list[Fault] | None = None) -> tuple[pd.DataFrame, SimState]:
    """Simulate every 5-minute step with after < ts <= until.

    `after` is the last step already simulated (for a fresh start, use midnight minus 5 min).
    `state` must be the state at `after`. Returns (frame indexed by local time, state at `until`).
    """
    tz = site.timezone
    after, until = pd.Timestamp(after).tz_convert(tz), pd.Timestamp(until).tz_convert(tz)
    state = state or SimState()
    battery, inverter = state.battery, state.inverter
    day_key, day_grid = state.day, state.day_grid

    outs = []
    day = (after + STEP).normalize()
    while day <= until:
        key = f"{day:%Y-%m-%d}"
        # Move the NEPA state forward to the start of this day (also skips over any gap).
        while day_key is not None and day_key < key:
            prev = _local_day(site, day_key)
            _, day_grid = simulate_grid(site, prev, day_grid)
            day_key = f"{prev + pd.Timedelta(days=1):%Y-%m-%d}"
        day_key = key

        frame, _ = day_inputs(site, day, hourly, label, day_grid, faults)
        part = frame[(frame.index > after) & (frame.index <= until)]
        if len(part):
            out, battery, inverter = dispatch.run(site, part, battery, inverter,
                                                  part["extra_fade"].to_numpy())
            out["outdoor_temp_c"] = part["outdoor_temp_c"]
            out["fault_label"] = part["fault_label"]
            outs.append(out)
        day += pd.Timedelta(days=1)

    out = pd.concat(outs) if outs else pd.DataFrame()
    return out, SimState(battery, inverter, day_key, day_grid)


def simulate_day(site: SiteConfig, day, hourly: pd.DataFrame, label: str,
                 state: SimState | None = None,
                 faults: list[Fault] | None = None) -> tuple[pd.DataFrame, SimState]:
    """Simulate one whole local day (288 steps), continuing from `state`."""
    day = _local_day(site, day)
    return simulate_window(site, day - STEP, day + pd.Timedelta(days=1) - STEP, hourly, label,
                           state, faults)


def summarise(out: pd.DataFrame, site: SiteConfig) -> dict:
    """Daily totals in kWh plus a few health numbers."""
    def kwh(col: str) -> float:
        return float(out[col].clip(lower=0).sum() * (5 / 60) / 1000)

    return {
        "solar_available_kwh": kwh("pv_available_w"),
        "solar_used_kwh": float((out["pv1_w"] + out["pv2_w"]).sum() * (5 / 60) / 1000),
        "solar_curtailed_kwh": kwh("curtailed_w"),
        "house_kwh": kwh("load_w"),
        "grid_import_kwh": kwh("grid_w"),
        "battery_charged_kwh": kwh("batt_w"),
        "battery_discharged_kwh": float((-out["batt_w"]).clip(lower=0).sum() * (5 / 60) / 1000),
        "unserved_kwh": kwh("unserved_w"),
        "blackout_minutes": int((out["unserved_w"] > 0).sum() * 5),
        "soc_min": float(out["batt_soc"].min()),
        "soc_max": float(out["batt_soc"].max()),
        "batt_temp_max": float(out["batt_temp_c"].max()),
        "faults": sorted({f for f in out["fault_code"] if f}),
        "soh_end": float(out["soh"].iloc[-1]),
    }
