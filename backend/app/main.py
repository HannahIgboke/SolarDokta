"""SolarDokta backend API.

Endpoints so far:
    GET  /health        is the server up? when did the last tick run? (public)
    POST /tick          run the virtual inverter up to now (Supabase Cron, every 5 minutes)
    POST /jobs/{name}   run a background job: "forecast", "purge", "anomaly", "detect", "alerts", "evening"
    POST /whatsapp/...  Twilio's WhatsApp webhook and delivery reports (signed by Twilio)
    /api/...            the dashboard's endpoints (see app/dashboard.py; need a login token)

/tick and /jobs/* need the header  X-Cron-Secret: <CRON_SECRET from .env>.
They answer straight away (202 Accepted) and do the work in the background, because the
scheduler only waits a few seconds for a reply. If a tick is still running when the next one
arrives, the new one is skipped; the following tick catches up anyway.

Run locally (from backend/):
    uvicorn app.main:app --reload
then open http://127.0.0.1:8000/docs
"""

import logging
import secrets
import threading
import time
from typing import Annotated

import pandas as pd
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from app import dashboard, push, staff_api, uploads, whatsapp
from app.config import get_settings
from app.jobs import JOBS, active_sites
from app.simulator.tick import run_tick

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("solardokta")

app = FastAPI(title="SolarDokta API", version="0.4.0")
app.add_middleware(                      # let the dashboard (another web address) call the API
    CORSMiddleware,
    allow_origins=[o.strip() for o in get_settings().frontend_origins.split(",") if o.strip()],
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
app.include_router(dashboard.router)
app.include_router(staff_api.router)
app.include_router(uploads.router)
app.include_router(whatsapp.router)
app.include_router(push.router)

_busy = {"tick": threading.Lock(), **{name: threading.Lock() for name in JOBS}}
_started: dict[str, float] = {}        # when the current run of each task began
_last: dict[str, dict] = {}            # last result of each task, shown on /health
# A run that takes longer than this is treated as stuck (e.g. a network call that never returned),
# so the next run goes ahead instead of being skipped forever.
STUCK_AFTER = {"tick": 10 * 60}
STUCK_DEFAULT = 60 * 60


def require_cron_secret(x_cron_secret: Annotated[str | None, Header()] = None) -> None:
    expected = get_settings().cron_secret
    if not expected:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "CRON_SECRET is not set on the server")
    if not x_cron_secret or not secrets.compare_digest(x_cron_secret, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong or missing X-Cron-Secret")


def _running_for(name: str) -> float:
    return time.monotonic() - _started.get(name, time.monotonic())


def _claim(name: str) -> "threading.Lock | None":
    """Take the task's lock. If the previous run looks stuck, give up on it and start fresh."""
    lock = _busy[name]
    if lock.acquire(blocking=False):
        _started[name] = time.monotonic()
        return lock
    if _running_for(name) > STUCK_AFTER.get(name, STUCK_DEFAULT):
        log.error("%s: previous run stuck for %.0f min; starting a fresh one", name, _running_for(name) / 60)
        fresh = threading.Lock()
        fresh.acquire()
        _busy[name], _started[name] = fresh, time.monotonic()
        return fresh
    return None


def _run(name: str, fn) -> None:
    """Run a task in the background, never two copies of the same task at once."""
    lock = _claim(name)
    if lock is None:
        log.warning("%s skipped: previous run still going (%.0f s)", name, _running_for(name))
        return
    t0 = time.monotonic()
    try:
        result = fn()
        _last[name] = {"ok": True, "at": pd.Timestamp.now(tz="UTC").isoformat(),
                       "seconds": round(time.monotonic() - t0, 1), "result": result}
        log.info("%s done in %.1fs: %s", name, time.monotonic() - t0, result)
    except Exception as exc:
        _last[name] = {"ok": False, "at": pd.Timestamp.now(tz="UTC").isoformat(), "error": repr(exc)}
        log.exception("%s failed", name)
    finally:
        lock.release()


def _tick() -> dict:
    results = run_tick(active_sites())
    return {r.site: {"rows": r.rows, "now_at": r.last_ts.isoformat(), "faults": r.faults}
            for r in results}


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "time": pd.Timestamp.now(tz="UTC").isoformat(),
            "last": {k: {kk: v[kk] for kk in ("ok", "at", "seconds") if kk in v} for k, v in _last.items()}}


@app.post("/tick", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(require_cron_secret)])
def tick(background: BackgroundTasks) -> dict:
    if _busy["tick"].locked() and _running_for("tick") <= STUCK_AFTER["tick"]:
        return {"accepted": False, "reason": "previous tick still running"}
    background.add_task(_run, "tick", _tick)
    return {"accepted": True}


@app.post("/jobs/{name}", status_code=status.HTTP_202_ACCEPTED,
          dependencies=[Depends(require_cron_secret)])
def job(name: str, background: BackgroundTasks) -> dict:
    if name not in JOBS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown job {name!r}. Jobs: {sorted(JOBS)}")
    background.add_task(_run, name, JOBS[name])
    return {"accepted": True, "job": name}


@app.get("/status/{name}", dependencies=[Depends(require_cron_secret)])
def last_result(name: str) -> dict:
    """Full result of the last run of a task (handy when testing)."""
    return _last.get(name, {"ok": None, "message": "not run since the server started"})
