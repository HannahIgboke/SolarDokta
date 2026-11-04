"""Map site coordinates onto a 0.5-degree weather grid.

NASA POWER's weather data is coarser than 0.5 degrees, so sites in the same city share one
weather point. This keeps the weather tables small (important on Supabase's free tier).
"""

from dataclasses import dataclass

from app.db import get_client


@dataclass(frozen=True)
class WeatherPoint:
    latitude: float
    longitude: float


def weather_point(latitude: float, longitude: float) -> WeatherPoint:
    def snap(x: float) -> float:
        return round(round(float(x) * 2) / 2, 1)

    return WeatherPoint(snap(latitude), snap(longitude))


def site_weather_points(client=None) -> list[WeatherPoint]:
    """Distinct weather points covering every site in the database."""
    client = client or get_client()
    rows = client.table("sites").select("latitude,longitude").execute().data
    return sorted({weather_point(r["latitude"], r["longitude"]) for r in rows},
                  key=lambda p: (p.latitude, p.longitude))
