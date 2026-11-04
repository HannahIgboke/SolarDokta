import threading

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app import main
from app.config import get_settings

SECRET = {"X-Cron-Secret": "test-secret"}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("CRON_SECRET", "test-secret")
    get_settings.cache_clear()
    main._last.clear()
    calls = []

    def fake_tick():
        calls.append("tick")
        ts = pd.Timestamp("2026-11-01 19:05", tz="Africa/Lagos")
        return {"lagos-001": {"rows": 1, "now_at": ts.isoformat(), "faults": []}}

    monkeypatch.setattr(main, "_tick", fake_tick)
    monkeypatch.setitem(main.JOBS, "forecast", lambda: calls.append("forecast") or {"points": 2})
    c = TestClient(main.app)
    c.calls = calls
    yield c
    get_settings.cache_clear()


def test_health_is_public(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_tick_needs_the_secret(client):
    assert client.post("/tick").status_code == 401
    assert client.post("/tick", headers={"X-Cron-Secret": "wrong"}).status_code == 401
    assert client.calls == []


def test_tick_runs_in_background_and_reports(client):
    r = client.post("/tick", headers=SECRET)
    assert r.status_code == 202 and r.json()["accepted"]
    assert client.calls == ["tick"]                      # TestClient runs background tasks
    assert client.get("/health").json()["last"]["tick"]["ok"] is True
    assert client.get("/status/tick", headers=SECRET).json()["result"]["lagos-001"]["rows"] == 1


def test_overlapping_tick_is_skipped(client):
    lock: threading.Lock = main._busy["tick"]
    lock.acquire()
    try:
        r = client.post("/tick", headers=SECRET)
        assert r.status_code == 202 and r.json()["accepted"] is False
    finally:
        lock.release()
    assert client.calls == []


def test_jobs(client):
    assert client.post("/jobs/forecast", headers=SECRET).status_code == 202
    assert client.calls == ["forecast"]
    assert client.post("/jobs/nonsense", headers=SECRET).status_code == 404


def test_failures_are_recorded_not_raised(client, monkeypatch):
    monkeypatch.setattr(main, "_tick", lambda: 1 / 0)
    assert client.post("/tick", headers=SECRET).status_code == 202
    last = client.get("/status/tick", headers=SECRET).json()
    assert last["ok"] is False and "ZeroDivisionError" in last["error"]
    assert not main._busy["tick"].locked()               # lock released after a failure


def test_server_without_secret_refuses(client, monkeypatch):
    monkeypatch.setenv("CRON_SECRET", "")
    get_settings.cache_clear()
    assert client.post("/tick", headers=SECRET).status_code == 503

