"""Dashboard API: logins, who can open which site, tools and chat (fake database, no internet)."""

import pytest
from fastapi.testclient import TestClient

from app import dashboard, main
from app.agent import tools
from app.agent.llm import LLMTurn
from tests.fakedb import FakeDB

ORG, OTHER_ORG = "org-1", "org-2"


def site_row(code, site_id, org, customer=None):
    return {"id": site_id, "code": code, "name": f"{code} home", "org_id": org,
            "customer_id": customer, "city": "Lagos", "latitude": 6.6, "longitude": 3.35,
            "timezone": "Africa/Lagos", "pv1_kwp": 3.6, "pv2_kwp": 1.4, "tilt_deg": 10,
            "azimuth_deg": 180, "inverter_kw": 6, "battery_kwh": 10,
            "battery_chemistry": "lifepo4", "tariff_band": "A", "load_profile": "home",
            "inverter_mode": "SBU"}


@pytest.fixture
def api(monkeypatch):
    db = FakeDB()
    db.tables["profiles"] = [
        {"id": "u-staff", "org_id": ORG, "role": "staff", "full_name": "Tunde"},
        {"id": "u-ada", "org_id": ORG, "role": "customer", "full_name": "Ada",
         "preferred_language": "pcm"},
    ]
    db.tables["sites"] = [site_row("lagos-001", "s1", ORG, customer="u-ada"),
                          site_row("lagos-002", "s2", ORG),
                          site_row("kano-001", "s3", OTHER_ORG)]
    tokens = {"staff-token": "u-staff", "ada-token": "u-ada", "stranger-token": "u-nobody"}

    def verify(token):
        if token not in tokens:
            raise ValueError("bad token")
        return tokens[token]

    monkeypatch.setattr(dashboard, "get_client", lambda: db)
    monkeypatch.setattr(tools, "get_client", lambda: db)
    monkeypatch.setattr(dashboard, "verify_token", verify)
    return TestClient(main.app), db


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_login_is_required(api):
    client, _ = api
    assert client.get("/api/me").status_code == 401
    assert client.get("/api/me", headers=auth("forged")).status_code == 401
    assert client.get("/api/me", headers=auth("stranger-token")).status_code == 403   # no profile


def test_staff_see_their_organisation_customers_their_own_site(api):
    client, _ = api
    staff = client.get("/api/me", headers=auth("staff-token")).json()
    assert staff["role"] == "staff" and [s["code"] for s in staff["sites"]] == ["lagos-001", "lagos-002"]
    ada = client.get("/api/me", headers=auth("ada-token")).json()
    assert ada["role"] == "customer" and [s["code"] for s in ada["sites"]] == ["lagos-001"]
    assert ada["preferred_language"] == "pcm"


def test_tools_respect_site_access(api):
    client, db = api
    db.tables["findings"] = [{"site_id": "s1", "kind": "unusual_day", "severity": "info",
                              "status": "open", "ts_start": "2026-11-01T10:00:00+00:00",
                              "details": {}, "dedupe_key": "x"}]
    r = client.get("/api/sites/lagos-001/tools/open_problems", headers=auth("ada-token"))
    assert r.status_code == 200 and r.json()["all_clear"]           # customers don't see ML days
    r = client.get("/api/sites/lagos-001/tools/open_problems", headers=auth("staff-token"))
    assert r.json()["open_problems"][0]["kind"] == "unusual_day"
    assert client.get("/api/sites/lagos-002/tools/battery_now",
                      headers=auth("ada-token")).status_code == 404  # not her site
    assert client.get("/api/sites/kano-001/tools/battery_now",
                      headers=auth("staff-token")).status_code == 404  # another installer
    assert client.get("/api/sites/lagos-001/tools/drop_tables",
                      headers=auth("staff-token")).status_code == 404


def test_chat_uses_the_agent(api, monkeypatch):
    client, _ = api

    class OneLine:
        last_model = "fake"

        def generate(self, system, messages, tools, allow_tools=True):
            assert "lagos-001 home" in system
            return LLMTurn(text="Your battery dey fine.")

    monkeypatch.setattr(dashboard, "_llm", OneLine())
    r = client.post("/api/sites/lagos-001/chat", headers=auth("ada-token"),
                    json={"message": "How my battery dey?", "history": []})
    assert r.status_code == 200 and r.json()["reply"] == "Your battery dey fine."
    bad = client.post("/api/sites/lagos-001/chat", headers=auth("ada-token"),
                      json={"message": "", "history": []})
    assert bad.status_code == 422                                   # empty message refused


def test_public_demo_is_read_only(api, monkeypatch):
    client, _ = api
    from app import staff_api, uploads
    monkeypatch.setattr(staff_api, "get_client", dashboard.get_client)
    monkeypatch.setattr(uploads, "get_client", dashboard.get_client)
    me = client.get("/api/me", headers=auth("demo-customer")).json()
    assert me["demo"] and me["role"] == "customer" and [s["code"] for s in me["sites"]] == ["lagos-001"]
    staff = client.get("/api/me", headers=auth("demo-staff")).json()
    assert [s["code"] for s in staff["sites"]] == ["lagos-001", "lagos-002"]     # the demo installer
    assert client.get("/api/sites/lagos-002/tools/battery_now", headers=auth("demo-customer")).status_code == 404
    for path, body in (("/api/sites/lagos-001/fuel", {"fuel": "petrol", "litres": 10, "amount_ngn": 12000}),
                       ("/api/sites/lagos-001/demo/fault", {"kind": "overload"}),
                       ("/api/findings/1", {"status": "resolved"})):
        who = "demo-customer" if "fuel" in path else "demo-staff"
        assert client.post(path, headers=auth(who), json=body).status_code == 403
    info = client.get("/api/sites/lagos-001/customer", headers=auth("demo-staff")).json()
    assert info["customer"] is None or "•" in (info["customer"]["whatsapp_number"] or "•")


def test_demo_chat_is_limited(api, monkeypatch):
    client, _ = api

    class OneLine:
        last_model = "fake"

        def generate(self, *a, **k):
            return LLMTurn(text="Battery is fine.")

    monkeypatch.setattr(dashboard, "_llm", OneLine())
    dashboard._demo_questions.clear()
    def ask():
        return client.post("/api/sites/lagos-001/chat", headers=auth("demo-customer"),
                           json={"message": "How is my battery?", "history": []})

    assert all(ask().status_code == 200 for _ in range(5))
    over = ask()
    assert over.status_code == 429 and "5 questions an hour" in over.json()["detail"]
