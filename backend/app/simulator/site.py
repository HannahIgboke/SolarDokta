"""A site's physical setup, loaded from the `sites` table."""

from dataclasses import dataclass

from app.db import get_client

PANEL_WATTS = 550        # assumed module size when we only know total kWp
PANEL_VMP = 41.5         # volts at max power for a typical 550 W module at 25 C


@dataclass(frozen=True)
class SiteConfig:
    id: str
    code: str
    latitude: float
    longitude: float
    timezone: str
    pv1_kwp: float
    pv2_kwp: float
    tilt_deg: float
    azimuth_deg: float
    inverter_kw: float
    battery_kwh: float
    battery_chemistry: str
    tariff_band: str
    city: str = "Lagos"
    load_profile: str = "home"
    inverter_mode: str = "SBU"

    @property
    def strings(self) -> dict[str, float]:
        """Panel strings with non-zero size, e.g. {"pv1": 3.6, "pv2": 1.4}."""
        return {k: v for k, v in (("pv1", self.pv1_kwp), ("pv2", self.pv2_kwp)) if v > 0}

    @staticmethod
    def panels_in(kwp: float) -> int:
        return max(1, round(kwp * 1000 / PANEL_WATTS))


def _from_row(r: dict) -> SiteConfig:
    return SiteConfig(
        id=r["id"], code=r["code"],
        latitude=float(r["latitude"]), longitude=float(r["longitude"]), timezone=r["timezone"],
        pv1_kwp=float(r["pv1_kwp"]), pv2_kwp=float(r["pv2_kwp"]),
        tilt_deg=float(r["tilt_deg"]), azimuth_deg=float(r["azimuth_deg"]),
        inverter_kw=float(r["inverter_kw"]), battery_kwh=float(r["battery_kwh"]),
        battery_chemistry=r["battery_chemistry"], tariff_band=r["tariff_band"],
        city=r["city"], load_profile=r.get("load_profile", "home"),
        inverter_mode=r.get("inverter_mode", "SBU"),
    )


def load_sites(client=None) -> list[SiteConfig]:
    client = client or get_client()
    rows = client.table("sites").select("*").eq("is_simulated", True).order("code").execute().data
    return [_from_row(r) for r in rows]


def load_site(code: str, client=None) -> SiteConfig:
    client = client or get_client()
    rows = client.table("sites").select("*").eq("code", code).execute().data
    if not rows:
        raise ValueError(f"No site with code {code!r}")
    return _from_row(rows[0])
