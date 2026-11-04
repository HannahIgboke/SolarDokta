"""Bad NEPA supply, heat / El Niño, customer inputs, the staff API and the agent fixes."""
# ruff: noqa: F811  (the db fixture is shared with test_agent)

from dataclasses import replace
from datetime import date

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app import dashboard, main, staff_api, uploads
from app.agent import reader, tools
from app.agent.agent import Agent, guess_tools
from app.agent.llm import LLMTurn
from app.detect import live
from app.simulator import grid
from app.simulator.faults import _iso
from tests.test_agent import HOURLY, NOW, ctx_for, db, set_latest, sim  # noqa: F401
from tests.test_live import HOME

# ---------- NEPA supply ----------

def hours_of_light(site, start, days=30):
    state, total = None, 0.0
    for d in pd.date_range(start, periods=days, freq="D", tz=site.timezone):
        g, state = grid.simulate_grid(site, d, state)
        total += g["grid_on"].mean() * 24
    return total / days


def test_grid_conditions_cut_supply():
    grid.set_conditions(None)                                          # the defaults
    lagos = replace(HOME, city="Lagos", tariff_band="A")
    assert hours_of_light(lagos, "2026-08-01") == pytest.approx(18, abs=3)     # normal band A
    assert hours_of_light(lagos, "2026-10-25", days=40) == pytest.approx(6, abs=2.5)  # the crisis
    crash, _, cond = grid.supply(lagos, pd.Timestamp("2026-10-19"))
    assert crash == 1.5 and "500 MW" in cond.note                      # newest condition wins
    grid.set_conditions([grid.GridCondition("Lagos", date(2026, 8, 1), None, 3.0, 8.0)])
    assert hours_of_light(lagos, "2026-08-01") == pytest.approx(3, abs=1.5)
    grid.set_conditions(None)


def test_light_tracker(db):
    db.tables["findings"] = [{"site_id": HOME.id, "kind": "battery_ran_out", "status": "resolved",
                              "ts_start": _iso(NOW - pd.Timedelta(days=2)),
                              "details": {"blackout_minutes": 90}, "dedupe_key": "x"}]
    res = tools.light_tracker(ctx_for(db), days=7)
    assert len(res["days"]) == 7 and res["normal_hours_for_band"] == 18.0
    assert res["home_blackout_hours"] == 1.5 and res["home_blackouts"] == 1


# ---------- heat / El Niño ----------

def test_heat_outlook(db, monkeypatch):
    hot = HOURLY.copy()
    hot["temp_c"] = 37.0
    monkeypatch.setattr(tools, "forecast_weather", lambda ctx: (hot, "left"))
    for r in db.tables["telemetry_hourly"]:
        r["batt_temp_max"] = 36.0                                      # a hot battery room
    res = tools.heat_outlook(ctx_for(db))
    assert res["ageing_speed_vs_25c"] == pytest.approx(2 ** 1.1, rel=0.01)
    assert res["extra_wear_percent_per_year"] > 0 and res["battery_hot_days_last_30"] >= 7
    assert res["heatwave_tomorrow"] and res["panel_midday_loss_percent"] >= 14
    assert "El Niño" in res["el_nino"] and "ask your installer" in res["tips"][0]


def test_heatwave_finding_from_saved_forecast(db):
    tomorrow = (NOW.normalize() + pd.Timedelta(days=1)).tz_convert("UTC")
    db.tables["weather_forecast"] = [
        {"latitude": 6.5, "longitude": 3.5, "ts": _iso(tomorrow + pd.Timedelta(hours=h)),
         "ghi_wm2": 500.0, "temp_c": 30.0 + (8 if 11 <= h <= 15 else 0), "cloud_cover_pct": 20.0,
         "fetched_at": _iso(NOW)} for h in range(1, 25)]
    alarms = live.heatwave(HOME, NOW, db)
    assert alarms and alarms[0].kind == "heatwave" and alarms[0].details["high_c"] == 38


# ---------- agent fixes ----------

def test_guess_tools_new_topics():
    names = dict(guess_tools("Why did my inverter go off yesterday?"))
    assert names["open_problems"] == {"days": 30}
    assert "light_tracker" in dict(guess_tools("How many hours of light did we get this week?"))
    assert "heat_outlook" in dict(guess_tools("Wetin this heat dey do my battery?"))


class Scripted:
    last_model = "fake"

    def __init__(self, turns):
        self.turns, self.seen = list(turns), []

    def generate(self, system, messages, tools, allow_tools=True):
        self.seen.append([dict(m) for m in messages])
        return self.turns.pop(0)


def test_agent_redoes_a_reply_in_the_wrong_language(db):
    llm = Scripted([LLMTurn(text="Your battery dey full, no wahala."),
                    LLMTurn(text="Your battery is full, no problem.")])
    r = Agent(llm, ctx_for(db)).reply("Is my battery full right now?")
    assert r.text == "Your battery is full, no problem."
    assert "wrong language" in llm.seen[1][-1]["text"]


def test_tomorrow_plan_names_a_dead_string(db, monkeypatch):
    monkeypatch.setattr(tools, "forecast_weather", lambda ctx: (HOURLY, "left"))
    db.tables["findings"] = [{"site_id": HOME.id, "kind": "string_failure", "status": "open",
                              "details": {"target": "pv2"}, "severity": "critical"}]
    res = tools.tomorrow_plan(ctx_for(db))
    assert res["dead_panel_strings"] == ["string 2"] and "producing nothing" in res["note"]


# ---------- customer inputs and the staff API ----------

@pytest.fixture
def api(db, monkeypatch):
    db.tables["sites"][0].update({
        "org_id": "org-1", "customer_id": "u-ada", "city": "Lagos", "latitude": HOME.latitude,
        "longitude": HOME.longitude, "timezone": HOME.timezone, "pv1_kwp": HOME.pv1_kwp,
        "pv2_kwp": HOME.pv2_kwp, "tilt_deg": 10, "azimuth_deg": 180, "inverter_kw": 6,
        "battery_kwh": 10, "battery_chemistry": "lifepo4", "tariff_band": "A",
        "inverter_mode": "SBU", "is_simulated": True})
    db.tables["profiles"] = [
        {"id": "u-staff", "org_id": "org-1", "role": "staff", "full_name": "Tunde"},
        {"id": "u-ada", "org_id": "org-1", "role": "customer", "full_name": "Ada"}]
    for mod in (dashboard, staff_api, uploads, tools):
        monkeypatch.setattr(mod, "get_client", lambda: db)
    monkeypatch.setattr(dashboard, "verify_token", lambda t: {"s": "u-staff", "a": "u-ada"}[t])
    return TestClient(main.app), db


def as_(who):
    return {"Authorization": f"Bearer {who}"}


def test_token_receipt_sets_the_real_nepa_price(api, monkeypatch):
    client, db = api
    monkeypatch.setattr(reader, "read_file", lambda kind, data, mime: {
        "readable": True, "amount_ngn": 10000, "units_kwh": 45.5, "date": "2026-02-08"})
    r = client.post("/api/sites/lagos-001/uploads", headers=as_("a"),
                    data={"kind": "token_receipt"}, files={"file": ("r.jpg", b"img", "image/jpeg")})
    assert r.status_code == 200 and r.json()["status"] == "read"
    assert "N220 per kWh" in r.json()["extracted"]["applied"]
    assert db.storage.files                                          # the file was stored
    pr = tools.pricing(ctx_for(db))
    assert pr["tariff"] == pytest.approx(219.78, abs=0.01) and pr["own_prices"] == ["grid"]
    bad = client.post("/api/sites/lagos-001/uploads", headers=as_("a"),
                      data={"kind": "voice_note"}, files={"file": ("r.jpg", b"img", "image/jpeg")})
    assert bad.status_code == 400                                    # a voice note must be audio


def test_voice_note_problem_reaches_the_technician(api, monkeypatch):
    client, db = api
    monkeypatch.setattr(reader, "read_file", lambda kind, data, mime: {
        "transcript": "Inverter dey beep since morning", "summary": "The inverter has been beeping.",
        "reports_problem": True, "problem": "beeping"})
    client.post("/api/sites/lagos-001/uploads", headers=as_("a"), data={"kind": "voice_note"},
                files={"file": ("v.ogg", b"aud", "audio/ogg")})
    inbox = client.get("/api/findings", headers=as_("s")).json()["findings"]
    report = next(f for f in inbox if f["kind"] == "customer_report")
    assert report["details"]["problem"] == "beeping"
    done = client.post(f"/api/findings/{report['id']}", headers=as_("s"),
                       json={"status": "resolved", "note": "Fan replaced"})
    assert done.status_code == 200
    assert next(f for f in db.tables["findings"] if f["id"] == report["id"])["note"] == "Fan replaced"


def test_fuel_form_and_appliance_list(api):
    client, _ = api
    assert client.post("/api/sites/lagos-001/fuel", headers=as_("a"),
                       json={"fuel": "petrol", "litres": 20, "amount_ngn": 24000}).json()["price_per_litre"] == 1200
    assert client.post("/api/sites/lagos-001/fuel", headers=as_("a"),
                       json={"fuel": "petrol", "litres": 20, "amount_ngn": 200}).status_code == 400
    assert client.get("/api/sites/lagos-001/appliances", headers=as_("a")).json()["source"] == "usual"
    client.put("/api/sites/lagos-001/appliances", headers=as_("a"),
               json=[{"name": "Deep freezer", "watts": 250}, {"name": "router", "watts": 15}])
    mine = client.get("/api/sites/lagos-001/appliances", headers=as_("a")).json()
    assert mine["source"] == "yours" and {a["name"] for a in mine["appliances"]} == {"deep freezer", "router"}


def test_staff_only_endpoints(api):
    client, db = api
    assert client.get("/api/fleet", headers=as_("a")).status_code == 403
    fleet = client.get("/api/fleet", headers=as_("s")).json()
    assert fleet["totals"]["sites"] == 1 and fleet["sites"][0]["code"] == "lagos-001"
    hist = client.get("/api/sites/lagos-001/history", headers=as_("s")).json()
    assert set(hist) == {"strings", "battery", "battery_trend", "energy"}   # (data is from Feb)
    added = client.post("/api/sites/lagos-001/demo/fault", headers=as_("s"), json={"kind": "string_failure"})
    assert added.status_code == 200 and added.json()["target"] == "pv2"
    assert client.post("/api/sites/lagos-001/demo/fix", headers=as_("s")).json()["ended"] == 1
    db.tables["sites"][0]["is_simulated"] = False
    assert client.post("/api/sites/lagos-001/demo/fault", headers=as_("s"),
                       json={"kind": "overload"}).status_code == 400


def test_igbo_is_recognised_and_can_be_forced(db):
    from app.agent.agent import reply_language
    assert reply_language("Batrị m ọ ga-eru ụtụtụ?") == "ig"
    assert reply_language("How my battery dey?") == "pcm"
    llm = Scripted([LLMTurn(text="Ee, batrị gị ga-eru ụtụtụ.")])
    r = Agent(llm, ctx_for(db)).reply("Will my battery last?", language="ig")
    assert r.text.startswith("Ee") and "[Reply in Igbo]" in llm.seen[0][-1]["text"]


def test_voice_question_is_transcribed_then_answered(api, monkeypatch):
    client, _ = api
    monkeypatch.setattr(reader, "read_file", lambda kind, data, mime: {"language": "pcm", "transcript": "How my battery dey?"})

    class OneLine:
        last_model = "fake"

        def generate(self, *a, **k):
            return LLMTurn(text="Your battery dey 80%.")

    monkeypatch.setattr(dashboard, "_llm", OneLine())
    r = client.post("/api/sites/lagos-001/chat/voice", headers=as_("a"), data={"language": "pcm"},
                    files={"audio": ("q.webm", b"aud", "audio/webm")})
    assert r.status_code == 200 and r.json()["transcript"] == "How my battery dey?"
    assert r.json()["reply"] == "Your battery dey 80%."


def test_what_if_runs_in_memory_and_compares(api, monkeypatch):
    import time

    from app import whatif
    client, db = api
    monkeypatch.setattr(whatif, "weather_for", lambda site, a, b: (HOURLY, "left"))
    rows_before = len(db.tables.get("telemetry", []))
    t0 = time.perf_counter()
    r = client.post("/api/sites/lagos-001/whatif", headers=as_("s"),
                    json={"days": 2, "nepa_hours": 0, "heatwave_c": 6, "battery_room_c": 8,
                          "new_appliance": {"name": "AC", "watts": 1200, "hours_per_day": 6, "from_hour": 20}})
    took = time.perf_counter() - t0
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["what_if"]["nepa_hours_per_day"] < 1 < out["as_is"]["nepa_hours_per_day"]
    assert out["what_if"]["battery_hottest_c"] > out["as_is"]["battery_hottest_c"]
    assert out["what_if"]["battery_ageing_speed"] > out["as_is"]["battery_ageing_speed"]
    assert out["what_if"]["blackout_hours"] >= out["as_is"]["blackout_hours"] and out["summary"]
    assert len(db.tables.get("telemetry", [])) == rows_before            # nothing saved
    assert client.post("/api/sites/lagos-001/whatif", headers=as_("a"), json={}).status_code == 403
    assert took < 30


def test_fleet_shows_heat_light_and_blackouts(api):
    client, _ = api
    s = client.get("/api/fleet", headers=as_("s")).json()
    site = s["sites"][0]
    assert site["heat"]["risk"] in ("low", "medium", "high") and "blackouts_7d" in site
    assert {"need_visit", "blackout_hours_7d", "heat_risk_sites"} <= set(s["totals"])


def test_fleet_chat_sends_fleet_data(api, monkeypatch):
    client, _ = api
    seen = {}

    class Fake:
        last_model = "fake"

        def generate(self, system, messages, tools, allow_tools=True):
            seen["system"], seen["tools"] = system, tools
            return LLMTurn(text="Visit lagos-001 first.")

    monkeypatch.setattr(dashboard, "_llm", Fake())
    r = client.post("/api/fleet/chat", headers=as_("s"), json={"message": "Which site first?"})
    assert r.json()["reply"] == "Visit lagos-001 first." and "lagos-001" in seen["system"] and seen["tools"] == []
    assert client.post("/api/fleet/chat", headers=as_("a"), json={"message": "hi"}).status_code == 403
