"""API for the technician (staff) side of the dashboard.

    GET  /api/fleet                         every site at a glance (map + table)
    GET  /api/findings?status=open&site=..  the problems inbox
    POST /api/findings/{id}                 resolve / dismiss / reopen a finding, with a note
    GET  /api/sites/{code}/history          long-term charts: string performance, battery
                                            health estimates, 30 days of energy (customers too)
    GET  /api/sites/{code}/customer         who owns the site (name, WhatsApp, language)
    POST /api/sites/{code}/demo/fault       break a simulated site on purpose (for demos)
    POST /api/sites/{code}/demo/fix         end the demo faults on that site now
    POST /api/sites/{code}/demo/check       run the 5-minute tick and the detectors right now
    POST /api/sites/{code}/whatif           "how would this site cope if...?" (simulation only)
    POST /api/fleet/chat                    Ask Dokta about all your sites at once

Only staff can call these (except history), and only for their own organisation's sites.
"""

from typing import Annotated, Literal

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from app import whatif
from app.agent.tools import PLAIN, ToolContext, battery_health_now, latest_reading
from app.dashboard import current_profile, no_demo, site_for, visible_sites
from app.db import get_client
from app.detect.battery import fade_per_year
from app.simulator import store
from app.simulator.faults import Fault, _iso
from app.simulator.site import _from_row

router = APIRouter(prefix="/api")


def staff_profile(profile: Annotated[dict, Depends(current_profile)]) -> dict:
    if profile["role"] != "staff":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Technicians only")
    return profile


Staff = Annotated[dict, Depends(staff_profile)]
URGENCY = {"critical": 0, "warning": 1, "info": 2}


@router.get("/fleet")
def fleet(profile: Staff) -> dict:
    client = get_client()
    rows = visible_sites(profile)
    findings = (client.table("findings").select("site_id,kind,severity").eq("status", "open")
                .range(0, 2999).execute().data)
    sites, now = [], pd.Timestamp.now(tz="UTC")
    for row in rows:
        site = _from_row(row)
        ctx = ToolContext(site, client=client, role="staff")
        r = latest_reading(ctx)
        mine = [f for f in findings if f["site_id"] == site.id]
        worst = min((f["severity"] for f in mine), key=lambda s: URGENCY.get(s, 3), default=None)
        soh, measured = battery_health_now(ctx)
        extra = _site_month(site, client, now)
        item = {"code": site.code, "name": row["name"], "city": site.city,
                "latitude": site.latitude, "longitude": site.longitude,
                "simulated": row.get("is_simulated", True),
                "open": {s: sum(f["severity"] == s for f in mine) for s in URGENCY},
                "worst": worst, "problems": sorted({f["kind"] for f in mine}),
                "battery_health": round(soh * 100) if measured else None, **extra}
        if r is not None:
            age = (now - r["ts"].tz_convert("UTC")) / pd.Timedelta(minutes=1)
            item.update({"battery": round(float(r["batt_soc"]) * 100),
                         "solar_w": round(float(r["pv1_w"]) + float(r["pv2_w"])),
                         "house_w": round(float(r["load_w"])), "nepa_on": float(r["grid_v"]) > 100,
                         "minutes_since_reading": round(age), "online": age <= 20,
                         "fault_code": r.get("fault_code")})
        else:
            item.update({"online": False, "minutes_since_reading": None})
        sites.append(item)
    totals = {"sites": len(sites), "online": sum(s["online"] for s in sites),
              "need_visit": sum(1 for s in sites if not s["online"] or s["worst"] == "critical"),
              "blackout_hours_7d": round(sum(s["blackouts_7d"]["hours"] for s in sites), 1),
              "heat_risk_sites": sum(1 for s in sites if s["heat"]["risk"] == "high"),
              "light_hours_avg": round(float(np.mean([s["light_hours_7d"] for s in sites
                                                      if s["light_hours_7d"] is not None] or [0])), 1),
              "critical": sum(s["open"]["critical"] for s in sites),
              "warning": sum(s["open"]["warning"] for s in sites),
              "solar_now_kw": round(sum(s.get("solar_w", 0) for s in sites) / 1000, 1)}
    return {"totals": totals, "sites": sites}


def _site_month(site, client, now: pd.Timestamp) -> dict:
    """Heat, NEPA hours and blackouts for one site over the last weeks (for the fleet view)."""
    since30 = (now - pd.Timedelta(days=30)).tz_convert(site.timezone).strftime("%Y-%m-%d")
    since7 = now - pd.Timedelta(days=7)
    daily = (client.table("telemetry_daily").select("day,batt_temp_max,grid_on_minutes")
             .eq("site_id", site.id).gte("day", since30).order("day").range(0, 99).execute().data)
    temps = [float(r["batt_temp_max"]) for r in daily if r.get("batt_temp_max") is not None]
    week = [r for r in daily if pd.Timestamp(r["day"]).tz_localize(site.timezone) >= since7.tz_convert(site.timezone).normalize()]
    outs = (client.table("findings").select("kind,details,ts_start").eq("site_id", site.id)
            .gte("ts_start", _iso(since7)).range(0, 499).execute().data)
    ran_out = [f for f in outs if f["kind"] == "battery_ran_out"]
    avg = float(np.mean(temps)) if temps else None
    speed = 2 ** ((avg - 25) / 10) if avg is not None else None
    hot_days = sum(t > 35 for t in temps)
    risk = ("high" if (speed or 0) >= 2 or hot_days >= 10 else
            "medium" if (speed or 0) >= 1.5 or hot_days >= 3 else "low")
    return {
        "heat": {"battery_avg_c": round(avg, 1) if avg is not None else None, "hot_days": hot_days,
                 "ageing_speed": round(speed, 2) if speed else None, "risk": risk},
        "light_hours_7d": round(float(np.mean([r["grid_on_minutes"] for r in week])) / 60, 1) if week else None,
        "blackouts_7d": {"count": len(ran_out), "hours": round(sum(
            int((f.get("details") or {}).get("blackout_minutes", 0)) for f in ran_out) / 60, 1)},
    }


@router.get("/findings")
def findings(profile: Staff, state: Annotated[str, Query(alias="status")] = "open",
             site: str | None = None) -> dict:
    client = get_client()
    sites = {r["id"]: r for r in visible_sites(profile)}
    if site:
        sites = {k: v for k, v in sites.items() if v["code"] == site}
    q = client.table("findings").select("*").order("ts_start", desc=True)
    if state != "all":
        q = q.eq("status", state)
    rows = [f for f in q.range(0, 999).execute().data if f["site_id"] in sites]
    out = []
    for f in rows:
        what, todo = PLAIN.get(f["kind"], (f["kind"].replace("_", " "), "check the site"))
        out.append({"id": f["id"], "site": sites[f["site_id"]]["code"],
                    "site_name": sites[f["site_id"]]["name"], "kind": f["kind"],
                    "severity": f["severity"], "status": f["status"], "problem": what,
                    "what_to_do": todo, "ts_start": f["ts_start"], "ts_end": f.get("ts_end"),
                    "details": f.get("details") or {}, "score": f.get("score"), "note": f.get("note")})
    out.sort(key=lambda f: (f["status"] != "open", URGENCY.get(f["severity"], 3)))
    return {"findings": out}


class FindingUpdate(BaseModel):
    status: Literal["open", "resolved", "dismissed"]
    note: str = Field(default="", max_length=500)


@router.post("/findings/{finding_id}")
def update_finding(finding_id: str, body: FindingUpdate, profile: Staff) -> dict:
    no_demo(profile)
    client = get_client()
    rows = client.table("findings").select("id,site_id").eq("id", finding_id).execute().data
    if not rows or rows[0]["site_id"] not in {r["id"] for r in visible_sites(profile)}:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such finding")
    closed = body.status != "open"
    client.table("findings").update({
        "status": body.status, "note": body.note or None,
        "resolved_by": profile["id"] if closed else None,
        "ts_end": _iso(pd.Timestamp.now(tz="UTC")) if closed else None,
    }).eq("id", finding_id).execute()
    return {"id": finding_id, "status": body.status}


def _trend(est: pd.Series) -> dict | None:
    """Straight fade line through the health estimates (for drawing), from the Theil-Sen rate."""
    rate = fade_per_year(est)
    if np.isnan(rate):
        return None
    t_mid = est.index[0] + (est.index[-1] - est.index[0]) / 2
    mid = float(est.median())
    def at(t):
        return mid - rate * ((t - t_mid) / pd.Timedelta(days=365))
    return {"from": {"ts": _iso(est.index[0]), "soh": round(at(est.index[0]), 4)},
            "to": {"ts": _iso(est.index[-1]), "soh": round(at(est.index[-1]), 4)},
            "fade_per_year": round(rate, 4)}


@router.get("/sites/{code}/history")
def history(code: str, profile: Annotated[dict, Depends(current_profile)]) -> dict:
    """Customers may see their own site's history too (used by the battery report)."""
    client = get_client()
    site = site_for(code, profile)
    now = pd.Timestamp.now(tz=site.timezone)
    health = store.load_health(site, now - pd.Timedelta(days=90), client)
    est = store.load_battery_estimates(site, now - pd.Timedelta(days=365), client)
    daily = (client.table("telemetry_daily")
             .select("day,pv_kwh,load_kwh,grid_import_kwh,grid_on_minutes,soc_min,batt_temp_max")
             .eq("site_id", site.id).gte("day", (now - pd.Timedelta(days=30)).strftime("%Y-%m-%d"))
             .order("day").range(0, 99).execute().data)

    def num(v, nd=3):
        return None if v is None or (isinstance(v, float) and np.isnan(v)) else round(float(v), nd)

    return {
        "strings": [{"day": d.strftime("%d %b"), "pv1": num(r["pr_pv1"]), "pv2": num(r["pr_pv2"]),
                     "battery_heat_c": num(r["batt_heat_c"], 1)} for d, r in health.iterrows()],
        "battery": [{"ts": _iso(t), "day": t.strftime("%d %b %Y"), "soh": round(float(v), 4)}
                    for t, v in est.items()],
        "battery_trend": _trend(est) if len(est) >= 8 else None,
        "energy": [{"day": pd.Timestamp(r["day"]).strftime("%d %b"), "solar_kwh": num(r["pv_kwh"], 1),
                    "use_kwh": num(r["load_kwh"], 1), "nepa_kwh": num(r["grid_import_kwh"], 1),
                    "light_hours": num(float(r["grid_on_minutes"]) / 60, 1),
                    "battery_low": num(r["soc_min"] * 100 if r.get("soc_min") is not None else None, 0),
                    "battery_temp_max": num(r.get("batt_temp_max"), 1)} for r in daily],
    }


@router.get("/sites/{code}/customer")
def customer(code: str, profile: Staff) -> dict:
    client = get_client()
    site = site_for(code, profile)
    row = client.table("sites").select("customer_id,install_date").eq("id", site.id).execute().data[0]
    person = None
    if row.get("customer_id"):
        p = (client.table("profiles").select("full_name,whatsapp_number,preferred_language")
             .eq("id", row["customer_id"]).execute().data)
        person = p[0] if p else None
    if person and profile.get("demo"):                 # don't show a real phone number publicly
        person = {**person, "whatsapp_number": "+234 ••• ••• ••••"}
    return {"customer": person, "install_date": row.get("install_date"),
            "system": {"pv1_kwp": site.pv1_kwp, "pv2_kwp": site.pv2_kwp, "inverter_kw": site.inverter_kw,
                       "battery_kwh": site.battery_kwh, "battery": site.battery_chemistry,
                       "mode": site.inverter_mode, "tariff_band": site.tariff_band,
                       "tilt": site.tilt_deg, "azimuth": site.azimuth_deg}}


# ---------- demo controls (simulated sites only) ----------

DEMO_FAULTS = {   # what each demo button does to the virtual inverter
    "string_failure": ("pv2", {}),
    "soiling": ("all", {"max_loss": 0.35, "ramp_days": 0.1}),
    "overload": ("all", {"extra_w": 7000}),
    "hot_battery_room": ("all", {"extra_c": 12.0}),
    "shading": ("pv1", {"from_hour": 0.0, "hours": 24.0, "loss": 0.6}),
}


class DemoFault(BaseModel):
    kind: Literal["string_failure", "soiling", "overload", "hot_battery_room", "shading"]


def _simulated(code: str, profile: dict):
    site = site_for(code, profile)
    row = get_client().table("sites").select("is_simulated").eq("id", site.id).execute().data
    if not row or not row[0].get("is_simulated", True):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Demo controls only work on simulated sites")
    return site


@router.post("/sites/{code}/demo/fault")
def demo_fault(code: str, body: DemoFault, profile: Staff) -> dict:
    no_demo(profile)
    site = _simulated(code, profile)
    now = pd.Timestamp.now(tz=site.timezone).floor("5min")
    target, params = DEMO_FAULTS[body.kind]
    end = now + pd.Timedelta(minutes=30) if body.kind == "overload" else None
    f = Fault(body.kind, now + pd.Timedelta(minutes=5), end, target, {**params, "demo": True})
    row = get_client().table("injected_faults").insert(f.to_row(site.id)).execute().data[0]
    return {"id": row["id"], "kind": body.kind, "target": target, "starts": _iso(f.start),
            "message": "Added. The next readings will show it; SolarDokta usually spots it within "
                       "10-20 minutes (dust takes longer: it needs a few days of evidence)."}


@router.post("/sites/{code}/demo/fix")
def demo_fix(code: str, profile: Staff) -> dict:
    no_demo(profile)
    site = _simulated(code, profile)
    client = get_client()
    now = pd.Timestamp.now(tz=site.timezone).floor("5min")
    rows = (client.table("injected_faults").select("id,end_ts,params").eq("site_id", site.id)
            .or_(f"end_ts.is.null,end_ts.gt.{_iso(now)}").execute().data)
    rows = [r for r in rows if (r.get("params") or {}).get("demo")]   # leave the planned faults alone
    for r in rows:
        client.table("injected_faults").update({"end_ts": _iso(now)}).eq("id", r["id"]).execute()
    return {"ended": len(rows)}


@router.post("/sites/{code}/demo/check")
def demo_check(code: str, profile: Staff) -> dict:
    no_demo(profile)
    from app.detect import live
    from app.simulator.tick import run_tick

    site = _simulated(code, profile)
    ticked = run_tick([site])
    result = live.check_site(site)
    return {"new_readings": sum(t.rows for t in ticked), **result}


# ---------- what-if tests ----------

@router.post("/sites/{code}/whatif")
def what_if(code: str, body: whatif.Scenario, profile: Staff) -> dict:
    """Simulation only: nothing is saved and the customer never sees it (allowed on the demo)."""
    site = site_for(code, profile)
    try:
        return whatif.run(site, body, get_client())
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Couldn't run the test (the weather forecast may be unreachable). Try again.") from exc


# ---------- Ask Dokta about the whole fleet ----------

FLEET_SYSTEM = """You are SolarDokta's assistant for a solar installer's technicians. You answer \
questions about ALL the sites they look after, using only the FLEET DATA below (live readings, \
open problems, battery health, battery heat in this El Niño season, hours of NEPA and blackouts \
in the last 7 days). Be concrete and technical: name sites, numbers and what to do or bring. \
Rank by urgency when asked what to do first. Keep it under 8 short lines. If the data doesn't \
answer the question, say so. Today is {today}.

FLEET DATA
{data}
"""


class FleetChat(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    history: list[dict] = Field(default_factory=list, max_length=20)


@router.post("/fleet/chat")
def fleet_chat(body: FleetChat, profile: Staff, request: Request) -> dict:
    import json

    from app import dashboard
    from app.agent.llm import LLMError
    from app.agent.providers import make_llm

    if profile.get("demo"):
        dashboard.demo_chat_allowed(request)
    data = fleet(profile)
    for s in data["sites"]:
        s.pop("latitude", None)
        s.pop("longitude", None)
    system = FLEET_SYSTEM.format(today=pd.Timestamp.now(tz="Africa/Lagos").strftime("%A %d %B %Y, %H:%M"),
                                 data=json.dumps(data, default=str))
    msgs = [{"role": m.get("role"), "text": m.get("text")} for m in body.history[-10:]
            if m.get("role") in ("user", "model") and m.get("text")]
    msgs.append({"role": "user", "text": body.message})
    try:
        dashboard._llm = dashboard._llm or make_llm()
        turn = dashboard._llm.generate(system, msgs, [], allow_tools=False)
    except LLMError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Ask Dokta can't answer right now. Try again shortly.") from exc
    return {"reply": turn.text or "No answer came back. Try asking another way.",
            "model": getattr(dashboard._llm, "last_model", None)}
