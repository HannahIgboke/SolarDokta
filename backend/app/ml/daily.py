"""Daily anomaly check: score yesterday for every site and record unusual days.

Runs once a day (Supabase Cron -> POST /jobs/anomaly):
1. For each site, rebuild yesterday's 216 day-features from the stored telemetry + weather.
2. Send all sites in ONE call to the autoencoder on Modal.
3. If Modal can't be reached, score locally with the Isolation Forest instead (no PyTorch needed).
4. Days scoring above the threshold become 'unusual_day' findings for the technician dashboard
   (not WhatsApp alerts: the evaluation showed ~2 false alarms per site per year).
"""

import logging

import numpy as np
import pandas as pd

from app.config import REPO_ROOT
from app.detect.expected import expected_power
from app.findings import open_finding
from app.ml.features import daily_features
from app.simulator import store
from app.simulator.site import SiteConfig
from app.simulator.weather_source import hourly_weather

log = logging.getLogger(__name__)

MODEL_DIR = REPO_ROOT / "ml" / "models"
MODAL_APP = "solardokta-anomaly"


def day_features(site: SiteConfig, day: pd.Timestamp, client=None) -> np.ndarray | None:
    """Yesterday's feature row for one site, or None if the day isn't complete."""
    tel = store.load_telemetry(site, day, day + pd.Timedelta(days=1), client)
    if len(tel) < 288:
        return None
    hourly, label = hourly_weather(site, day, day + pd.Timedelta(days=1))
    x = daily_features(site, tel, expected_power(site, hourly, label, tel.index))
    return x.iloc[0].to_numpy() if len(x) else None


def score_on_modal(x: np.ndarray) -> tuple[np.ndarray, list]:
    """Score on Modal. Needs MODAL_TOKEN_ID / MODAL_TOKEN_SECRET (or `modal setup` locally)."""
    import modal

    scorer = modal.Cls.from_name(MODAL_APP, "Scorer")()
    res = scorer.score.remote(x.tolist())
    return np.asarray(res["scores"]) / res["threshold"], res["hints"]


def score_locally(x: np.ndarray) -> tuple[np.ndarray, list]:
    from app.ml.models import ForestDetector

    forest = ForestDetector.load(MODEL_DIR)
    return forest.score(x) / forest.threshold, [None] * len(x)


def run(sites: list[SiteConfig], day: pd.Timestamp | None = None, client=None,
        remote=score_on_modal, fallback=score_locally) -> dict:
    tz = sites[0].timezone
    day = (day.tz_convert(tz) if day is not None
           else pd.Timestamp.now(tz=tz).normalize() - pd.Timedelta(days=1)).normalize()

    rows, scored, skipped = [], [], []
    for site in sites:
        try:
            x = day_features(site, day, client)
        except Exception:
            log.exception("Could not build features for %s", site.code)
            x = None
        if x is None:
            skipped.append(site.code)
        else:
            rows.append(x)
            scored.append(site)
    if not rows:
        return {"day": f"{day:%Y-%m-%d}", "scored": 0, "skipped": skipped}

    x = np.vstack(rows).astype(np.float32)
    try:
        ratio, hints = remote(x)
        model = "autoencoder"
    except Exception as exc:
        log.warning("Modal unavailable (%s); using the local Isolation Forest", exc)
        ratio, hints = fallback(x)
        model = "isolation_forest"

    unusual = []
    for site, r, hint in zip(scored, ratio, hints, strict=True):
        if r <= 1.0:
            continue
        unusual.append(site.code)
        open_finding(site, kind="unusual_day", severity="info",
                     dedupe_key=f"unusual_day:{day:%Y-%m-%d}",
                     ts_start=day, ts_end=day + pd.Timedelta(days=1), score=round(float(r), 2),
                     details={"model": model, "hint": hint, "score_vs_threshold": round(float(r), 2)},
                     client=client)
    return {"day": f"{day:%Y-%m-%d}", "model": model, "scored": len(scored),
            "unusual": unusual, "skipped": skipped,
            "scores": {s.code: round(float(r), 2) for s, r in zip(scored, ratio, strict=True)}}
