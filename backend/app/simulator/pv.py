"""Solar panel model: hourly weather in, 5-minute power per panel string out.

Steps for every 5-minute step:
1. Sun position for the site (pvlib).
2. Sunlight on flat ground (GHI): the hourly weather value is spread across the hour using a
   clear-sky curve, then passing-cloud flicker is added (seeded, so results are repeatable).
3. Sunlight on the tilted panels (plane-of-array irradiance).
4. Panel temperature from sunlight and air temperature (hot panels produce less).
5. DC power from the PVWatts model, minus system losses.

The inverter may later "throw away" some of this power if the battery is full and the house
needs little; that happens in the dispatch step (Phase 2 Part C), not here.
"""

import hashlib

import numpy as np
import pandas as pd
import pvlib

from app.simulator.site import PANEL_VMP, SiteConfig

STEP = "5min"
GAMMA_PDC = -0.0035       # power drops 0.35% per degree C above 25 C (typical mono panels)
SYSTEM_LOSSES = 0.14      # wiring, mismatch, inverter MPPT etc. (PVWatts default is ~14%)
VOLTAGE_TEMP_COEFF = -0.0029   # Vmp drops ~0.29% per degree C


def _clear_sky_index_noise(n: int, kt: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Multiplicative cloud flicker. Strongest on partly cloudy hours, weak on clear or overcast."""
    strength = 0.25 * np.clip(4 * kt * (1 - kt), 0, 1)       # peaks at kt = 0.5
    noise = np.empty(n)
    x = 0.0
    for i in range(n):                                         # AR(1): clouds drift, not jump
        x = 0.7 * x + rng.normal(0, 1)
        noise[i] = x
    noise /= noise.std() or 1.0
    return np.clip(1 + strength * noise, 0.05, 1.3)


def spread_hourly_ghi(
    hourly: pd.DataFrame,
    site: SiteConfig,
    start: pd.Timestamp,
    end: pd.Timestamp,
    label: str = "left",
    seed: int | None = None,
    flicker: bool = True,
) -> pd.DataFrame:
    """Turn hourly weather into 5-minute weather between start (inclusive) and end (exclusive).

    hourly: DataFrame with UTC index, columns ghi_wm2 and temp_c.
    label: "left" if each hourly value describes the hour AFTER its timestamp (NASA POWER),
           "right" if it describes the hour BEFORE (Open-Meteo).
    """
    times = pd.date_range(start, end, freq=STEP, inclusive="left", tz="UTC")
    solpos = pvlib.solarposition.get_solarposition(times, site.latitude, site.longitude)
    clear = pvlib.clearsky.haurwitz(solpos["apparent_zenith"])["ghi"]

    # Mean clear-sky GHI for each hourly bucket, matched to the weather's labelling.
    closed = "left" if label == "left" else "right"
    clear_hourly = clear.resample("1h", label=label, closed=closed).mean()
    hourly = hourly.reindex(clear_hourly.index.union(hourly.index)).sort_index()
    kt_hourly = (hourly["ghi_wm2"] / clear_hourly).replace([np.inf, -np.inf], np.nan)
    kt_hourly = kt_hourly.where(clear_hourly > 20).clip(0, 1.2)

    # Each 5-minute step takes the clear-sky index of the hour it belongs to.
    bucket = times.floor("1h") if label == "left" else (times - pd.Timedelta(minutes=5)).floor("1h") + pd.Timedelta(hours=1)
    kt = kt_hourly.reindex(bucket).to_numpy()
    kt = pd.Series(kt, index=times).interpolate(limit_direction="both").fillna(0).to_numpy()

    ghi = clear.to_numpy() * kt
    if flicker:                      # off when we want the smooth "expected" curve (detectors)
        ghi = ghi * _clear_sky_index_noise(len(times), kt, np.random.default_rng(seed))

    temp = hourly["temp_c"].interpolate(limit_direction="both")
    temp = temp.reindex(temp.index.union(times)).interpolate("time").reindex(times)

    return pd.DataFrame({"ghi_wm2": ghi, "temp_c": temp.to_numpy(),
                         "zenith": solpos["zenith"].to_numpy(),
                         "azimuth": solpos["azimuth"].to_numpy()}, index=times)


def pv_power(weather_5min: pd.DataFrame, site: SiteConfig, soiling: dict[str, float] | None = None) -> pd.DataFrame:
    """DC power (W), panel temperature and string voltage for each panel string.

    soiling: optional loss factor per string, e.g. {"pv2": 0.15} = PV2 loses 15% to dust.
    """
    soiling = soiling or {}
    w = weather_5min
    erbs = pvlib.irradiance.erbs(w["ghi_wm2"], w["zenith"], w.index)
    poa = pvlib.irradiance.get_total_irradiance(
        surface_tilt=site.tilt_deg, surface_azimuth=site.azimuth_deg,
        solar_zenith=w["zenith"], solar_azimuth=w["azimuth"],
        dni=erbs["dni"], ghi=w["ghi_wm2"], dhi=erbs["dhi"], albedo=0.2,
    )["poa_global"].fillna(0).clip(lower=0)
    t_cell = pvlib.temperature.faiman(poa, w["temp_c"], wind_speed=1.0)

    out = pd.DataFrame(index=w.index)
    out["poa_wm2"] = poa
    out["t_cell_c"] = t_cell
    for name, kwp in site.strings.items():
        dc = pvlib.pvsystem.pvwatts_dc(poa, t_cell, pdc0=kwp * 1000, gamma_pdc=GAMMA_PDC)
        dc = dc * (1 - SYSTEM_LOSSES) * (1 - soiling.get(name, 0.0))
        out[f"{name}_w"] = dc.clip(lower=0).fillna(0)
        vmp = site.panels_in(kwp) * PANEL_VMP * (1 + VOLTAGE_TEMP_COEFF * (t_cell - 25))
        out[f"{name}_v"] = vmp.where(poa > 5, 0).fillna(0)
    for name in ("pv1", "pv2"):            # always present, even for single-string sites
        out[f"{name}_w"] = out.get(f"{name}_w", 0.0)
        out[f"{name}_v"] = out.get(f"{name}_v", 0.0)
    return out


def day_seed(site_code: str, day: pd.Timestamp) -> int:
    """Stable seed per site and day, so re-running a day gives identical clouds."""
    digest = hashlib.sha256(f"{site_code}:{day:%Y-%m-%d}".encode()).digest()
    return int.from_bytes(digest[:4], "little")
