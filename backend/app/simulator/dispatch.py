"""Inverter logic: route every watt, every 5 minutes.

For each step the inverter decides:
1. How much solar goes straight to the house.
2. Who covers the rest of the house: NEPA or the battery (depends on the mode, SUB or SBU).
3. Where spare solar goes: into the battery; anything left is curtailed (thrown away).
4. Whether NEPA should top up the battery.
5. If nothing can cover the house: an overload or low-battery shutdown (a fault).

Sign conventions match the telemetry table: batt_w > 0 charging, grid_w > 0 importing.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.simulator import battery as bat
from app.simulator.battery import BatteryState
from app.simulator.site import SiteConfig

SBU_BACK_TO_GRID_SOC = 0.30     # SBU: use NEPA for the house once the battery falls below this
GRID_CHARGE_TARGET = 0.95       # NEPA tops the battery up to this level
GRID_CHARGE_C = 0.2             # NEPA charging power, as a fraction of capacity per hour
TRIP_STEPS = 1                  # an overload shuts the inverter down for 5 minutes


@dataclass
class StepResult:
    pv_used_w: float
    curtailed_w: float
    batt_w: float
    grid_w: float
    served_w: float
    unserved_w: float
    fault: str | None


def _output_off(pv_w: float, load_w: float, max_charge: float, fault: str) -> StepResult:
    """House output is off (trip or empty battery); solar can still charge the battery."""
    pv_to_batt = min(pv_w, max_charge)
    return StepResult(pv_used_w=pv_to_batt, curtailed_w=pv_w - pv_to_batt, batt_w=pv_to_batt,
                      grid_w=0.0, served_w=0.0, unserved_w=load_w, fault=fault)


def route(site: SiteConfig, chem: bat.Chemistry, st: BatteryState, pv_w: float, load_w: float,
          grid_on: bool, tripped: bool = False, locked: bool = False) -> StepResult:
    """Decide where power flows for one step (no state changes).

    tripped: inverter is recovering from an overload. locked: battery hit its cut-off and has
    not yet recharged enough to restart. Both only matter when NEPA is off.
    """
    inv_w = site.inverter_kw * 1000
    max_charge, max_discharge = bat.limits(chem, site.battery_kwh, st)

    if not grid_on and tripped:
        return _output_off(pv_w, load_w, max_charge, "INVERTER_TRIP")
    if not grid_on and locked:
        return _output_off(pv_w, load_w, max_charge, "LOW_BATTERY")

    pv_to_load = min(pv_w, load_w, inv_w)
    need = load_w - pv_to_load
    batt_out = grid_to_load = 0.0

    use_battery_first = site.inverter_mode == "SBU" and st.soc > SBU_BACK_TO_GRID_SOC
    if grid_on and not use_battery_first:
        grid_to_load, need = need, 0.0
    else:
        batt_out = min(need, max_discharge, max(0.0, inv_w - pv_to_load))
        need -= batt_out
        if grid_on:                                    # SBU: NEPA covers what the battery can't
            grid_to_load, need = need, 0.0

    if need > 1.0:                                     # nobody can cover the house
        if load_w > inv_w:
            fault = "OVERLOAD"
        elif st.soc <= chem.min_soc + 0.01:
            fault = "LOW_BATTERY"
        else:
            fault = "BATTERY_LIMIT"
        return _output_off(pv_w, load_w, max_charge, fault)

    # Spare solar charges the battery; the rest is curtailed.
    spare = pv_w - pv_to_load
    pv_to_batt = 0.0 if batt_out > 0 else min(spare, max_charge)
    curtailed = spare - pv_to_batt

    # NEPA tops up the battery when it's on. SUB fills the battery (saved for outages);
    # SBU only lifts it back above its back-to-grid level, so it doesn't buy NEPA to discharge it.
    target = GRID_CHARGE_TARGET if site.inverter_mode == "SUB" else SBU_BACK_TO_GRID_SOC + 0.15
    grid_to_batt = 0.0
    if grid_on and batt_out == 0 and st.soc < target:
        grid_to_batt = min(max_charge - pv_to_batt, GRID_CHARGE_C * site.battery_kwh * 1000)
        grid_to_batt = max(0.0, grid_to_batt)

    batt_w = pv_to_batt + grid_to_batt - batt_out
    return StepResult(pv_used_w=pv_to_load + pv_to_batt, curtailed_w=curtailed, batt_w=batt_w,
                      grid_w=grid_to_load + grid_to_batt, served_w=load_w, unserved_w=0.0,
                      fault=None)


@dataclass
class InverterState:
    """What the inverter remembers between steps: recovering from a trip, or locked after empty."""
    trip_left: int = 0
    locked: bool = False


def run(site: SiteConfig, frame: pd.DataFrame, st: BatteryState,
        inv: InverterState | None = None,
        extra_fade: np.ndarray | None = None) -> tuple[pd.DataFrame, BatteryState, InverterState]:
    """Run the inverter over a frame of 5-minute inputs.

    frame columns: pv1_w, pv2_w (available solar), pv1_v, pv2_v, load_w, grid_on, grid_v,
                   room_temp_c. extra_fade: optional extra battery wear per step (a fault).
    Returns telemetry columns plus diagnostics, and the end battery and inverter states.
    """
    chem = bat.CHEMISTRIES[site.battery_chemistry]
    inv = InverterState(inv.trip_left, inv.locked) if inv else InverterState()
    cols = {c: frame[c].to_numpy() for c in
            ("pv1_w", "pv2_w", "pv1_v", "pv2_v", "load_w", "grid_on", "grid_v", "room_temp_c")}
    rows = []
    for i, ts in enumerate(frame.index):
        pv1, pv2 = float(cols["pv1_w"][i]), float(cols["pv2_w"][i])
        pv_w = pv1 + pv2
        room = float(cols["room_temp_c"][i])
        res = route(site, chem, st, pv_w, float(cols["load_w"][i]), bool(cols["grid_on"][i]),
                    inv.trip_left > 0, inv.locked)
        inv.trip_left = max(0, inv.trip_left - 1)
        if res.fault == "OVERLOAD":
            inv.trip_left = TRIP_STEPS

        st, volts, amps = bat.step(chem, site.battery_kwh, st, res.batt_w, room)
        if extra_fade is not None and extra_fade[i] > 0:
            st.soh = max(0.0, st.soh - float(extra_fade[i]))

        # After an empty-battery shutdown, the inverter waits for 10% more charge before restarting.
        if res.fault == "LOW_BATTERY":
            inv.locked = True
        elif inv.locked and st.soc >= chem.min_soc + 0.10:
            inv.locked = False

        share = res.pv_used_w / pv_w if pv_w > 0 else 0.0      # curtailment reduces both strings
        through = res.served_w + max(0.0, res.batt_w)
        rows.append({
            "ts": ts,
            "pv1_w": pv1 * share, "pv2_w": pv2 * share,
            "pv_v": max(float(cols["pv1_v"][i]), float(cols["pv2_v"][i])),
            "batt_soc": round(st.soc, 4), "batt_v": round(volts, 2), "batt_a": round(amps, 2),
            "batt_temp_c": round(st.temp_c, 2),
            "load_w": res.served_w, "grid_v": float(cols["grid_v"][i]), "grid_w": res.grid_w,
            "inv_temp_c": round(room + 5 + 15 * through / (site.inverter_kw * 1000), 1),
            "fault_code": res.fault,
            # Diagnostics (not stored in telemetry, used by tests, previews and ML labels)
            "pv_available_w": pv_w, "curtailed_w": res.curtailed_w,
            "demand_w": float(cols["load_w"][i]), "unserved_w": res.unserved_w,
            "batt_w": res.batt_w, "soh": st.soh,
        })
    out = pd.DataFrame(rows)
    if len(out):
        out = out.set_index("ts")
        out.index.name = None
        out["fault_code"] = out["fault_code"].astype(object).where(out["fault_code"].notna(), None)
    return out, st, inv


def energy_balance_error(df: pd.DataFrame) -> np.ndarray:
    """Per-step mismatch (W): solar used + grid - battery charging = house served."""
    pv_used = df["pv1_w"] + df["pv2_w"]
    return (pv_used + df["grid_w"] - df["batt_w"] - df["load_w"]).to_numpy()
