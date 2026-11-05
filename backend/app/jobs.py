"""Background jobs the scheduler triggers, apart from the 5-minute tick.

    forecast  every 3 hours: save the next 3 days of Open-Meteo weather for each weather point
              (used by "tomorrow's plan"), and drop forecast rows older than a week
    purge     every night: delete raw 5-minute telemetry older than 30 days (the hourly and
              daily summaries stay forever), keeping us inside Supabase's free 500 MB
    anomaly   every night: score yesterday with the autoencoder on Modal (Isolation Forest
              fallback) and record unusual days as findings
    detect    every hour: run the rule detectors and keep each site's findings up to date
    alerts    every hour, just after detect: new problems to customers and technicians, as phone
              notifications (and WhatsApp when switched on)
    evening   every day at 7 pm: "tonight and tomorrow" notification for each customer
"""

import logging

import pandas as pd

from app.db import get_client
from app.simulator.faults import _iso
from app.simulator.site import SiteConfig, load_sites
from app.weather import open_meteo
from app.weather.points import weather_point
from app.weather.store import save_forecast

log = logging.getLogger(__name__)

CITIES = ("Lagos", "Port Harcourt")      # SolarDokta's launch cities
RAW_KEEP_DAYS = 30
FORECAST_KEEP_DAYS = 7


def active_sites(client=None) -> list[SiteConfig]:
    """Simulated sites in the launch cities (other seed sites are ignored)."""
    return [s for s in load_sites(client) if s.city in CITIES]


def refresh_forecast(client=None) -> dict:
    client = client or get_client()
    points = sorted({weather_point(s.latitude, s.longitude) for s in active_sites(client)},
                    key=lambda p: (p.latitude, p.longitude))
    saved, failed = 0, []
    for p in points:
        # 7 days ahead: if Open-Meteo refuses us for a while, the readings and plans keep
        # running on this saved copy
        try:
            df = open_meteo.fetch_forecast(p.latitude, p.longitude, days=7)
        except Exception:
            log.exception("Forecast download failed for %s; keeping the saved copy", p)
            failed.append(f"{p.latitude},{p.longitude}")
            continue
        saved += save_forecast(p, df, client=client)
    cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=FORECAST_KEEP_DAYS)
    client.table("weather_forecast").delete().lt("ts", _iso(cutoff)).execute()
    return {"points": len(points), "hours_saved": saved, "failed": failed}


def purge(client=None) -> dict:
    client = client or get_client()
    from app.whatsapp import purge_conversations

    deleted = client.rpc("purge_old_telemetry", {"p_keep_days": RAW_KEEP_DAYS}).execute().data
    return {"raw_rows_deleted": deleted, "old_chats_deleted": purge_conversations(client)}


def anomaly(client=None) -> dict:
    from app.ml import daily  # imported here: only this job needs the ML code

    return daily.run(active_sites(client), client=client)


def detect(client=None) -> list[dict]:
    from app.detect import live

    return live.run(active_sites(client), client=client)


def alerts(client=None) -> dict:
    from app.whatsapp import send_alerts

    return send_alerts(client)


def evening(client=None) -> dict:
    from app.push import evening as run

    return run(client)


JOBS = {"forecast": refresh_forecast, "purge": purge, "anomaly": anomaly, "detect": detect,
        "alerts": alerts, "evening": evening}
