"""Save what SolarDokta finds (the `findings` table).

A finding stays 'open' until someone resolves or dismisses it. The dedupe_key stops the same
problem being saved twice (e.g. 'unusual_day:2026-11-01'), so jobs can safely run again.

Two shapes:
- conditions (a dead string, dust): one open finding while the problem lasts, resolved when the
  detector says it has cleared               -> open_finding / resolve_finding
- events (an overload, the battery running empty): one finding per occurrence, with its own
  start time in the key                      -> record_event
"""

import pandas as pd

from app.db import get_client
from app.simulator.faults import _iso
from app.simulator.site import SiteConfig


def open_finding(site: SiteConfig, kind: str, severity: str, dedupe_key: str,
                 ts_start: pd.Timestamp, ts_end: pd.Timestamp | None = None,
                 details: dict | None = None, score: float | None = None, client=None) -> bool:
    """Create an open finding unless one with the same dedupe_key is already open.

    Returns True if a new finding was created.
    """
    client = client or get_client()
    existing = (client.table("findings").select("id").eq("site_id", site.id)
                .eq("dedupe_key", dedupe_key).eq("status", "open").execute().data)
    if existing:
        return False
    client.table("findings").insert({
        "site_id": site.id, "kind": kind, "severity": severity, "dedupe_key": dedupe_key,
        "ts_start": _iso(ts_start), "ts_end": _iso(ts_end) if ts_end is not None else None,
        "details": details or {}, "score": score,
    }, returning="minimal").execute()
    return True


def record_event(site: SiteConfig, kind: str, severity: str, dedupe_key: str,
                 ts_start: pd.Timestamp, ts_end: pd.Timestamp | None, details: dict | None = None,
                 client=None) -> bool:
    """Save a one-off event. Returns True if it is new. If it was saved while still going on,
    it is closed off once it has ended."""
    client = client or get_client()
    existing = (client.table("findings").select("id,status").eq("site_id", site.id)
                .eq("dedupe_key", dedupe_key).execute().data)
    if existing:
        if ts_end is not None and existing[0]["status"] == "open":
            resolve_finding(existing[0]["id"], ts_end, client)
        return False
    client.table("findings").insert({
        "site_id": site.id, "kind": kind, "severity": severity, "dedupe_key": dedupe_key,
        "ts_start": _iso(ts_start), "ts_end": _iso(ts_end) if ts_end is not None else None,
        "status": "resolved" if ts_end is not None else "open", "details": details or {},
    }, returning="minimal").execute()
    return True


def open_findings(site: SiteConfig, kinds: set[str], client=None) -> list[dict]:
    client = client or get_client()
    rows = (client.table("findings").select("id,kind,dedupe_key").eq("site_id", site.id)
            .eq("status", "open").execute().data)
    return [r for r in rows if r["kind"] in kinds]


def resolve_finding(finding_id: str, ts_end: pd.Timestamp, client=None) -> None:
    client = client or get_client()
    client.table("findings").update({"status": "resolved", "ts_end": _iso(ts_end)}) \
        .eq("id", finding_id).execute()
