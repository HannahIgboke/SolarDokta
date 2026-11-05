"""Phone notifications: subscribing, test alerts, problem alerts and the evening summary."""

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app import dashboard, main, push, whatsapp
from app.agent import tools
from app.config import get_settings
from tests.fakedb import FakeDB
from tests.test_dashboard_api import ORG, auth, site_row

EP = "https://fcm.googleapis.com/fcm/send/abc"
SUB = {"endpoint": EP, "keys": {"p256dh": "BPk", "auth": "xyz"}, "lang": "pcm"}


@pytest.fixture
def api(monkeypatch):
    db = FakeDB()
    db.tables["profiles"] = [
        {"id": "u-staff", "org_id": ORG, "role": "staff", "full_name": "Tunde"},
        {"id": "u-ada", "org_id": ORG, "role": "customer", "full_name": "Ada", "preferred_language": "pcm"},
    ]
    db.tables["sites"] = [site_row("lagos-001", "s1", ORG, customer="u-ada"), site_row("lagos-002", "s2", ORG)]
    for mod in (dashboard, tools, push, whatsapp):
        monkeypatch.setattr(mod, "get_client", lambda: db)
    s = get_settings()
    for k, v in {"vapid_public_key": "PUB", "vapid_private_key": "PRIV", "demo_site": "lagos-001",
                 "alerts_enabled": True, "whatsapp_alerts": False}.items():
        monkeypatch.setattr(s, k, v)
    tokens = {"staff-token": "u-staff", "ada-token": "u-ada"}

    def verify(token):
        if token not in tokens:
            raise ValueError("bad token")
        return tokens[token]

    monkeypatch.setattr(dashboard, "verify_token", verify)
    delivered = []
    monkeypatch.setattr(push, "deliver", lambda sub, payload: delivered.append((sub["id"], payload)))
    push._tests.clear()
    return TestClient(main.app), db, delivered


def test_public_key_and_login_needed(api):
    client, _, _ = api
    assert client.get("/api/push/key").json() == {"key": "PUB"}
    assert client.post("/api/push/subscribe", json=SUB).status_code == 401


def test_customer_subscribes_to_their_own_site(api):
    client, db, _ = api
    assert client.post("/api/push/subscribe", headers=auth("ada-token"), json=SUB).status_code == 200
    row = db.tables["push_subscriptions"][0]
    assert row["site_id"] == "s1" and row["role"] == "customer" and row["lang"] == "pcm"
    client.post("/api/push/subscribe", headers=auth("ada-token"), json=SUB)          # same phone again
    assert len(db.tables["push_subscriptions"]) == 1
    client.post("/api/push/unsubscribe", headers=auth("ada-token"), json={"endpoint": EP})
    assert db.tables["push_subscriptions"] == []


def test_demo_visitors_can_try_alerts(api):
    client, db, delivered = api
    assert client.post("/api/push/subscribe", headers=auth("demo-customer"), json=SUB).status_code == 200
    assert db.tables["push_subscriptions"][0]["demo"] and db.tables["push_subscriptions"][0]["profile_id"] is None
    for _ in range(3):
        assert client.post("/api/push/test", headers=auth("demo-customer"), json={"endpoint": EP}).status_code == 200
    assert "Dust don cover your panel" in delivered[0][1]["body"]                     # in Pidgin
    assert client.post("/api/push/test", headers=auth("demo-customer"), json={"endpoint": EP}).status_code == 429


def test_problem_alerts_pop_up_on_the_right_phones(api):
    client, db, _ = api
    client.post("/api/push/subscribe", headers=auth("ada-token"), json=SUB)
    client.post("/api/push/subscribe", headers=auth("staff-token"),
                json={**SUB, "endpoint": EP + "-tunde", "lang": "en"})
    noon = pd.Timestamp("2026-11-04 11:00", tz="UTC")
    db.tables["findings"] = [
        {"id": "f1", "site_id": "s1", "kind": "string_failure", "severity": "critical", "status": "open",
         "ts_start": (noon - pd.Timedelta(hours=1)).isoformat(), "details": {"target": "pv2"},
         "created_at": (noon - pd.Timedelta(minutes=30)).isoformat()}]
    got = []
    out = whatsapp.send_alerts(db, now=noon, pusher=lambda sub, msg: got.append((sub["role"], msg)))
    assert out["sent"] == 2
    roles = {r: m for r, m in got}
    assert "panel" in roles["customer"]["body"] and roles["customer"]["url"] == "/my"
    assert "string 2" in roles["staff"]["body"] and roles["staff"]["url"] == "/staff/sites/lagos-001#problems"
    assert db.tables["alerts"][0]["channel"] == "push"
    assert whatsapp.send_alerts(db, now=noon, pusher=lambda sub, msg: got.append(1))["sent"] == 0   # never twice


def test_dead_subscriptions_are_removed(api):
    client, db, _ = api
    client.post("/api/push/subscribe", headers=auth("ada-token"), json=SUB)
    noon = pd.Timestamp("2026-11-04 11:00", tz="UTC")
    db.tables["findings"] = [{"id": "f1", "site_id": "s1", "kind": "soiling", "severity": "warning",
                              "status": "open", "ts_start": noon.isoformat(), "details": {},
                              "created_at": noon.isoformat()}]

    def gone(sub, msg):
        raise push.Gone()

    whatsapp.send_alerts(db, now=noon, pusher=gone)
    assert db.tables["push_subscriptions"] == []


def test_evening_summary_for_customers(api, monkeypatch):
    client, db, _ = api
    client.post("/api/push/subscribe", headers=auth("ada-token"), json=SUB)
    monkeypatch.setattr(tools, "run_tool", lambda ctx, name, args: (
        {"battery_percent": 80, "status": "charging", "nepa_on": False, "solar_now_w": 300,
         "house_using_w": 200, "lasts_until_morning_sun": True} if name == "battery_now"
        else {"date": "Thu 05 Nov", "sky": "sunny", "expected_solar_kwh": 21}))
    seen = []
    out = push.evening(db, sender=lambda sub, payload: seen.append(payload) or True)
    assert out["sent"] == 1 and "80%" in seen[0]["body"] and "reach morning" in seen[0]["body"]   # Pidgin
