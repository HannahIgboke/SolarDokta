"""Battery model: charge level, voltage, temperature and wear, one 5-minute step at a time.

Wear (state of health) has two parts, both faster when the battery is hot:
- calendar ageing: slow wear just from time passing (worse at high charge and high heat)
- cycle ageing: wear from energy flowing out, worse when the battery is drained deep

"Hot" uses the Arrhenius rule of thumb: chemical wear roughly doubles for every 10 C rise.
All numbers are typical published figures and can be tuned as real battery data comes in.
"""

from dataclasses import asdict, dataclass

STEP_H = 5 / 60


@dataclass(frozen=True)
class Chemistry:
    name: str
    min_soc: float              # inverter's low-battery cut-off
    eff_charge: float           # share of charging energy that ends up stored
    eff_discharge: float        # share of stored energy that comes out
    c_rate: float               # max charge/discharge power = c_rate x capacity (kW per kWh)
    cycle_fade: float           # SOH lost per full-capacity discharge at 25 C, moderate depth
    calendar_fade_per_year: float
    deep_stress: float          # how much harder deep discharge hits (low-SOC wear multiplier)
    v_empty: float              # resting voltage at 0% and 100% (48 V-class system)
    v_full: float
    r_internal: float           # ohms; voltage sag/rise under current


CHEMISTRIES = {
    # LiFePO4: ~6,000 cycles to 80% health at 25 C
    "lifepo4": Chemistry("lifepo4", min_soc=0.10, eff_charge=0.96, eff_discharge=0.96, c_rate=0.5,
                         cycle_fade=0.20 / 6000, calendar_fade_per_year=0.02, deep_stress=1.5,
                         v_empty=46.0, v_full=54.4, r_internal=0.02),
    # Tubular lead-acid: ~1,200 cycles to 80% at 50% depth; hates deep discharge
    "lead_acid": Chemistry("lead_acid", min_soc=0.30, eff_charge=0.90, eff_discharge=0.90, c_rate=0.2,
                           cycle_fade=0.20 / 600, calendar_fade_per_year=0.04, deep_stress=4.0,
                           v_empty=46.0, v_full=51.5, r_internal=0.05),
}


@dataclass
class BatteryState:
    soc: float = 0.8            # state of charge, 0-1
    soh: float = 1.0            # state of health: usable capacity / new capacity
    temp_c: float = 28.0        # battery temperature
    throughput_kwh: float = 0.0  # total energy discharged since new (for cycle counting)

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict | None) -> "BatteryState":
        return BatteryState(**d) if d else BatteryState()


def heat_factor(temp_c: float) -> float:
    """Arrhenius rule of thumb: wear doubles every 10 C above 25 C (halves below)."""
    return 2 ** ((temp_c - 25.0) / 10.0)


def resting_voltage(chem: Chemistry, soc: float) -> float:
    return chem.v_empty + (chem.v_full - chem.v_empty) * soc


def limits(chem: Chemistry, capacity_kwh: float, st: BatteryState) -> tuple[float, float]:
    """(max charge W, max discharge W) available this step at the battery terminals."""
    usable = capacity_kwh * st.soh
    rate_w = chem.c_rate * usable * 1000
    room_w = max(0.0, (1.0 - st.soc) * usable * 1000 / STEP_H / chem.eff_charge)
    avail_w = max(0.0, (st.soc - chem.min_soc) * usable * 1000 / STEP_H * chem.eff_discharge)
    return min(rate_w, room_w), min(rate_w, avail_w)


def step(chem: Chemistry, capacity_kwh: float, st: BatteryState, batt_w: float,
         room_temp_c: float) -> tuple[BatteryState, float, float]:
    """Apply one 5-minute step. batt_w > 0 charging, < 0 discharging (at the terminals).

    Returns (new state, terminal voltage, current in amps; + charging).
    """
    usable_wh = capacity_kwh * st.soh * 1000
    stored_wh = batt_w * STEP_H * (chem.eff_charge if batt_w > 0 else 1 / chem.eff_discharge)
    soc = min(1.0, max(0.0, st.soc + stored_wh / usable_wh))

    v_rest = resting_voltage(chem, (st.soc + soc) / 2)
    amps = batt_w / v_rest
    volts = v_rest + amps * chem.r_internal

    # Temperature: drifts towards room temperature (~3 h time constant), warmed by heavy current.
    self_heat = 4.0 * abs(batt_w) / (chem.c_rate * capacity_kwh * 1000)   # up to ~4 C at max rate
    target = room_temp_c + self_heat
    temp = st.temp_c + (target - st.temp_c) * (STEP_H / 3.0)

    # Wear
    hf = heat_factor(temp)
    calendar = chem.calendar_fade_per_year * STEP_H / 8760 * hf * (0.6 + 0.6 * soc)
    discharged_kwh = max(0.0, -batt_w) * STEP_H / 1000
    depth_stress = 1.0 + chem.deep_stress * max(0.0, 0.5 - soc) * 2      # grows below 50% SOC
    cycle = chem.cycle_fade * (discharged_kwh / capacity_kwh) * depth_stress * hf
    soh = max(0.0, st.soh - calendar - cycle)

    new = BatteryState(soc=soc, soh=soh, temp_c=temp,
                       throughput_kwh=st.throughput_kwh + discharged_kwh)
    return new, volts, amps
