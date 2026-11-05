"""Phone alerts without WhatsApp: Web Push (free, no business approval).

A customer or technician taps "Turn on alerts" in the web app (installed on their home screen or
in the browser). The browser gives us a "subscription": an address at Google's, Apple's or
Mozilla's push service that only works with our key pair (VAPID). We save it, and from then on we
can pop up a notification on that phone even when SolarDokta is closed.

    GET  /api/push/key          our public key (the browser needs it to subscribe)
    POST /api/push/subscribe    save this browser's subscription for the person's site(s)
    POST /api/push/unsubscribe  forget it
    POST /api/push/test         send a sample alert to this browser now (3 an hour)

Jobs (Supabase Cron):
    alerts   hourly: new problems -> customers and technicians (shared with WhatsApp, see whatsapp.py)
    evening  daily 7 pm: "tonight and tomorrow" for each customer

Demo visitors can subscribe too: they get the demo home's alerts, so anyone can try it.
Subscriptions the push service says are gone (404/410) are deleted.
"""

import hashlib
import json
import logging
import time
from collections import defaultdict, deque
from typing import Annotated

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.config import get_settings
from app.dashboard import current_profile, visible_sites
from app.db import get_client
from app.simulator.faults import _iso

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/push")
Profile = Annotated[dict, Depends(current_profile)]


class Keys(BaseModel):
    p256dh: str = Field(max_length=200)
    auth: str = Field(max_length=100)


class Subscription(BaseModel):
    endpoint: str = Field(max_length=1000, pattern=r"^https://")
    keys: Keys
    lang: str = Field(default="en", pattern="^(en|pcm|ig)$")


class Endpoint(BaseModel):
    endpoint: str = Field(max_length=1000)


def _sub_id(endpoint: str) -> str:
    return hashlib.sha256(endpoint.encode()).hexdigest()[:24]


def configured() -> bool:
    s = get_settings()
    return bool(s.vapid_public_key and s.vapid_private_key)


class Gone(Exception):
    """The push service says this subscription no longer exists."""


def deliver(sub: dict, payload: dict) -> None:
    """Send one notification. Raises Gone if the subscription is dead."""
    from pywebpush import WebPushException, webpush

    s = get_settings()
    try:
        webpush(subscription_info={"endpoint": sub["endpoint"],
                                   "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]}},
                data=json.dumps(payload), vapid_private_key=s.vapid_private_key,
                vapid_claims={"sub": s.vapid_contact}, ttl=12 * 3600, timeout=10)
    except WebPushException as exc:
        code = getattr(exc.response, "status_code", None)
        if code in (404, 410):
            raise Gone() from exc
        raise


# ---------- endpoints ----------

@router.get("/key")
def public_key() -> dict:
    return {"key": get_settings().vapid_public_key or None}


@router.post("/subscribe")
def subscribe(body: Subscription, profile: Profile) -> dict:
    if not configured():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Alerts aren't set up on the server yet")
    sites = visible_sites(profile)
    if not sites:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No site on this account")
    if profile["role"] == "customer":
        sites = sites[:1]
    row = {
        "id": _sub_id(body.endpoint), "endpoint": body.endpoint, "p256dh": body.keys.p256dh,
        "auth": body.keys.auth, "lang": body.lang, "role": profile["role"],
        "profile_id": None if profile.get("demo") else profile["id"], "org_id": profile["org_id"],
        "site_id": sites[0]["id"] if profile["role"] == "customer" else None,
        "demo": bool(profile.get("demo")), "created_at": _iso(pd.Timestamp.now(tz="UTC")),
    }
    get_client().table("push_subscriptions").upsert([row], on_conflict="id").execute()
    return {"ok": True}


@router.post("/unsubscribe")
def unsubscribe(body: Endpoint, profile: Profile) -> dict:
    get_client().table("push_subscriptions").delete().eq("id", _sub_id(body.endpoint)).execute()
    return {"ok": True}


_tests: dict[str, deque] = defaultdict(deque)

TEST = {
    "customer": {
        "en": ("SolarDokta: Ikeja home",
               ("Dust on your panels is cutting your solar power. Have them washed early morning or "
                "evening. (This is a test alert.)")),
        "pcm": ("SolarDokta: Ikeja home",
                ("Dust don cover your panel, e dey reduce your solar. Make dem wash am early morning or "
                 "evening. (Na test alert be this.)")),
        "ig": ("SolarDokta: Ikeja home",
               "Ájá dị na panel gị na-ebelata ike anyanwụ gị. (Nke a bụ ule.)"),
    },
    "staff": {"en": ("SolarDokta [CRITICAL] Ikeja shop",
                     ("One set of panels has stopped producing (string 2). Bring a multimeter and MC4 "
                      "connectors. (Test alert.)"))},
}


@router.post("/test")
def test(body: Endpoint, profile: Profile) -> dict:
    sid = _sub_id(body.endpoint)
    rows = get_client().table("push_subscriptions").select("*").eq("id", sid).execute().data
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Turn on alerts first")
    times, now = _tests[sid], time.time()
    while times and now - times[0] > 3600:
        times.popleft()
    if len(times) >= 3:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "That's 3 test alerts this hour. Try later.")
    times.append(now)
    sub = rows[0]
    texts = TEST["staff" if sub["role"] == "staff" else "customer"]
    title, text = texts.get(sub.get("lang") or "en", texts["en"])
    try:
        deliver(sub, {"title": title, "body": text, "url": _home(sub), "tag": "test"})
    except Gone:
        get_client().table("push_subscriptions").delete().eq("id", sid).execute()
        raise HTTPException(status.HTTP_410_GONE, "This phone's alerts were switched off. Turn them on again.") from None
    except Exception as exc:
        log.exception("Test push failed")
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Couldn't reach the phone's push service. Try again.") from exc
    return {"ok": True}


# ---------- used by the jobs ----------

def _home(sub: dict) -> str:
    """Where tapping a notification opens. Demo visitors go back into the demo."""
    if sub.get("demo"):
        return "/demo/technician" if sub["role"] == "staff" else "/demo/customer"
    return "/staff" if sub["role"] == "staff" else "/my"


def subscriptions(client) -> list[dict]:
    return client.table("push_subscriptions").select("*").range(0, 4999).execute().data


def send_many(client, subs: list[dict], payload_for) -> tuple[int, int]:
    """payload_for(sub) -> dict or None. Returns (sent, failed); dead subscriptions are removed."""
    sent = failed = 0
    for sub in subs:
        payload = payload_for(sub)
        if not payload:
            continue
        try:
            deliver(sub, payload)
            sent += 1
        except Gone:
            client.table("push_subscriptions").delete().eq("id", sub["id"]).execute()
        except Exception:
            log.exception("Push to %s… failed", sub["id"][:6])
            failed += 1
    return sent, failed


def evening(client=None, sender=None) -> dict:
    """7 pm: tonight's battery and tomorrow's sun, for every customer with alerts on."""
    from app.agent import offline
    from app.agent.tools import ToolContext, run_tool
    from app.simulator.site import _from_row

    client = client or get_client()
    if not configured() and sender is None:
        return {"sent": 0, "note": "VAPID keys not set"}
    subs = [s for s in subscriptions(client) if s["role"] == "customer" and s.get("site_id")]
    sites = {r["id"]: r for r in client.table("sites").select("*").range(0, 4999).execute().data}
    texts: dict[tuple, str] = {}

    def payload_for(sub):
        site = sites.get(sub["site_id"])
        if not site:
            return None
        key = (site["id"], sub.get("lang") or "en")
        if key not in texts:
            ctx = ToolContext(_from_row(site), client=client)
            results = [{"name": n, "result": run_tool(ctx, n, {})} for n in ("battery_now", "tomorrow_plan")]
            texts[key] = offline.answer(results, key[1]).split("\n")[0]
        return {"title": f"SolarDokta: tonight at {site['name']}", "body": texts[key], "url": _home(sub), "tag": "evening"}

    if sender:                                                   # tests
        return {"sent": sum(1 for s in subs if sender(s, payload_for(s)))}
    sent, failed = send_many(client, subs, payload_for)
    return {"sent": sent, "failed": failed}
