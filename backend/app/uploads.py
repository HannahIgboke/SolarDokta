"""What customers (and technicians) add about a system: receipts, fuel prices, voice notes,
photos, and the list of appliances they own.

    GET  /api/sites/{code}/uploads       everything added so far (photos/audio get a 1-hour link)
    POST /api/sites/{code}/uploads       add a file (form fields: kind, component, file)
    POST /api/sites/{code}/fuel          "I bought 20 litres of diesel for N28,000"
    GET  /api/sites/{code}/appliances    the appliance list (theirs, or the usual one for the site)
    PUT  /api/sites/{code}/appliances    replace their appliance list

What happens to a file:
1. It is saved privately in Supabase Storage (bucket "uploads"; only this backend can open it).
2. Gemini reads it (app/agent/reader.py) and we keep the fields it found.
3. The useful part is applied: a token receipt sets the site's real NEPA price per kWh, a fuel
   receipt its fuel price, a voice note that reports a problem opens a finding for the
   technician, a photo's nameplate is compared with the system's recorded size.
"""

import logging
import uuid
from typing import Annotated, Literal

import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from app.agent import reader
from app.agent.llm import LLMError
from app.dashboard import current_profile, no_demo, site_for
from app.dashboard_views import site_appliances
from app.db import get_client
from app.simulator.appliances import PROFILES
from app.simulator.faults import _iso
from app.simulator.site import SiteConfig

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api")
Profile = Annotated[dict, Depends(current_profile)]

BUCKET = "uploads"
MAX_BYTES = 10 * 1024 * 1024
ALLOWED = {
    "token_receipt": ("image/", "application/pdf"),
    "fuel_receipt": ("image/", "application/pdf"),
    "voice_note": ("audio/",),
    "photo": ("image/",),
}
COMPONENTS = {"inverter", "battery", "panels", "distribution_board", "appliance", "other"}
GRID_PRICE_RANGE = (20, 1000)        # N per kWh: anything outside is a misread
FUEL_PRICE_RANGE = (300, 5000)       # N per litre


def _signed_url(path: str) -> str | None:
    try:
        r = get_client().storage.from_(BUCKET).create_signed_url(path, 3600)
        return r.get("signedURL") or r.get("signedUrl")
    except Exception:  # noqa: BLE001 - a missing file shouldn't break the whole list
        return None


def save_price(site: SiteConfig, item: str, price: float, day: str | None, source: str,
               upload_id: str | None = None) -> None:
    get_client().table("site_prices").insert({
        "site_id": site.id, "item": item, "price_ngn": round(price, 2),
        "effective_from": day or pd.Timestamp.now(tz=site.timezone).strftime("%Y-%m-%d"),
        "source": source, "upload_id": upload_id}).execute()


def _date(value) -> str | None:
    try:
        return pd.Timestamp(value).strftime("%Y-%m-%d") if value else None
    except (ValueError, TypeError):
        return None


def apply(site: SiteConfig, row: dict, found: dict, profile: dict) -> dict:
    """Use what Gemini read. Returns a short note about what changed (shown to the customer)."""
    kind, notes = row["kind"], {}
    if kind == "token_receipt":
        amount, units = found.get("amount_ngn"), found.get("units_kwh")
        if amount and units:
            price = float(amount) / float(units)
            if GRID_PRICE_RANGE[0] <= price <= GRID_PRICE_RANGE[1]:
                save_price(site, "grid", price, _date(found.get("date")), "token receipt", row["id"])
                notes["applied"] = f"NEPA price set to N{price:,.0f} per kWh"
            else:
                notes["warning"] = f"N{price:,.0f} per kWh looks wrong, so it wasn't used"
    elif kind == "fuel_receipt":
        price = found.get("price_per_litre")
        if not price and found.get("amount_ngn") and found.get("litres"):
            price = float(found["amount_ngn"]) / float(found["litres"])
        fuel = found.get("fuel") if found.get("fuel") in ("petrol", "diesel") else None
        if price and fuel and FUEL_PRICE_RANGE[0] <= float(price) <= FUEL_PRICE_RANGE[1]:
            save_price(site, fuel, float(price), _date(found.get("date")), "fuel receipt", row["id"])
            notes["applied"] = f"{fuel.title()} price set to N{float(price):,.0f} per litre"
    elif kind == "voice_note" and found.get("reports_problem"):
        get_client().table("findings").insert({
            "site_id": site.id, "kind": "customer_report", "severity": "warning",
            "dedupe_key": f"customer_report:{row['id']}", "ts_start": _iso(pd.Timestamp.now(tz="UTC")),
            "details": {"summary": found.get("summary"), "problem": found.get("problem"),
                        "transcript": found.get("transcript"), "upload_id": row["id"],
                        "from": profile.get("full_name")}}).execute()
        notes["applied"] = "Sent to your technician as a problem report"
    elif kind == "photo":
        cap, kw = found.get("capacity_kwh"), found.get("power_kw")
        if cap and site.battery_kwh and abs(float(cap) - site.battery_kwh) / site.battery_kwh > 0.2:
            notes["warning"] = (f"Label says {cap} kWh but this system is recorded as "
                                f"{site.battery_kwh:g} kWh: worth checking")
        if kw and abs(float(kw) - site.inverter_kw) / site.inverter_kw > 0.25 and "inverter" in str(found.get("shows", "")).lower():
            notes["warning"] = (f"Label says {kw} kW but the inverter is recorded as "
                                f"{site.inverter_kw:g} kW: worth checking")
    return notes


@router.post("/sites/{code}/uploads")
def upload(code: str, profile: Profile, kind: Annotated[str, Form()],
                 file: Annotated[UploadFile, File()],
                 component: Annotated[str | None, Form()] = None) -> dict:
    no_demo(profile)
    site = site_for(code, profile)
    if kind not in ALLOWED:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown kind {kind!r}")
    mime = (file.content_type or "").split(";")[0].strip().lower()
    if not mime.startswith(ALLOWED[kind]):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"A {kind.replace('_', ' ')} can't be a {mime or 'file of this type'}")
    data = file.file.read(MAX_BYTES + 1)            # plain (not async) so Gemini runs off the event loop
    if len(data) > MAX_BYTES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Files must be under 10 MB")
    client = get_client()
    ext = (file.filename or "").rsplit(".", 1)[-1][:5] if "." in (file.filename or "") else "bin"
    path = f"{site.code}/{kind}/{uuid.uuid4().hex}.{ext}"
    client.storage.from_(BUCKET).upload(path, data, {"content-type": mime})
    row = client.table("uploads").insert({
        "site_id": site.id, "uploaded_by": profile["id"], "kind": kind,
        "component": component if component in COMPONENTS else None,
        "storage_path": path, "mime_type": mime}).execute().data[0]
    try:
        found = reader.read_file(kind, data, mime)
        notes = apply(site, row, found, profile)
        update = {"status": "read", "extracted": {**found, **notes}}
    except LLMError as exc:
        update = {"status": "failed", "error": str(exc)[:300]}
    client.table("uploads").update(update).eq("id", row["id"]).execute()
    return {**row, **update, "url": _signed_url(path)}


@router.get("/sites/{code}/uploads")
def list_uploads(code: str, profile: Profile) -> dict:
    site = site_for(code, profile)
    rows = (get_client().table("uploads").select("*").eq("site_id", site.id)
            .order("created_at", desc=True).range(0, 99).execute().data)
    for r in rows:
        if r["kind"] in ("photo", "voice_note"):
            r["url"] = _signed_url(r["storage_path"])
    return {"uploads": rows}


class FuelPurchase(BaseModel):
    fuel: Literal["petrol", "diesel"]
    litres: float = Field(gt=0, le=1000)
    amount_ngn: float = Field(gt=0, le=10_000_000)


@router.post("/sites/{code}/fuel")
def fuel(code: str, body: FuelPurchase, profile: Profile) -> dict:
    no_demo(profile)
    site = site_for(code, profile)
    price = body.amount_ngn / body.litres
    if not FUEL_PRICE_RANGE[0] <= price <= FUEL_PRICE_RANGE[1]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"N{price:,.0f} per litre doesn't look right")
    save_price(site, body.fuel, price, None, f"entered by {profile.get('full_name') or 'customer'}")
    return {"fuel": body.fuel, "price_per_litre": round(price)}


class ApplianceItem(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    watts: float = Field(gt=0, le=10_000)
    qty: int = Field(default=1, ge=1, le=50)


@router.get("/sites/{code}/appliances")
def get_appliances(code: str, profile: Profile) -> dict:
    site = site_for(code, profile)
    mine = site_appliances(site, get_client())
    if mine:
        return {"appliances": mine, "source": "yours"}
    usual = [{"name": a.name.replace("_", " "), "watts": a.watts, "qty": a.qty}
             for a in PROFILES[site.load_profile].appliances]
    return {"appliances": usual, "source": "usual"}


@router.put("/sites/{code}/appliances")
def put_appliances(code: str, items: list[ApplianceItem], profile: Profile) -> dict:
    no_demo(profile)
    site = site_for(code, profile)
    if len(items) > 40:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "At most 40 appliances")
    client = get_client()
    client.table("site_appliances").delete().eq("site_id", site.id).execute()
    seen = {}
    for i in items:
        seen[i.name.strip().lower()] = i
    if seen:
        client.table("site_appliances").insert(
            [{"site_id": site.id, "name": k, "watts": v.watts, "qty": v.qty} for k, v in seen.items()]).execute()
    return {"saved": len(seen)}
