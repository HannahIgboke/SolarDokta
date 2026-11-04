"""Agent tools and the Gemini loop, on a fake database and a scripted fake LLM (no internet)."""

import pandas as pd
import pytest

from app.agent import tools
from app.agent.agent import MAX_ROUNDS, Agent, guess_tools, reply_language
from app.agent.appliances import find_appliance
from app.agent.llm import LLMError, LLMTurn
from app.agent.tools import ToolContext, run_tool
from app.simulator import store
from app.simulator.battery import BatteryState
from app.simulator.engine import STEP, SimState, simulate_window
from app.simulator.faults import _iso
from tests.fakedb import FakeDB
from tests.test_engine import _weather
from tests.test_live import HOME

TZ = "Africa/Lagos"
START = pd.Timestamp("2026-02-01", tz=TZ)
DAYS = 9
HOURLY = _weather(days=DAYS + 2)
NOW = START + pd.Timedelta(days=DAYS - 1, hours=13)          # early afternoon on day 9


@pytest.fixture(scope="module")
def sim():
    out, _ = simulate_window(HOME, START - STEP, NOW, HOURLY, "left",
                             SimState(BatteryState(soc=0.6)), [])
    return out


@pytest.fixture
def db(sim):
    db = FakeDB()
    db.tables["sites"] = [{"id": HOME.id, "code": HOME.code, "name": "Ikeja home",
                           "generator_fuel": "petrol", "generator_kwh_per_litre": 1.5,
                           "load_profile": "home", "install_date": "2025-01-01"}]
    db.tables["prices"] = [
        {"item": "petrol", "price_ngn": 1000, "effective_from": "2026-01-01", "source": "test"},
        {"item": "grid_band_a", "price_ngn": 200, "effective_from": "2026-01-01", "source": "test"},
        {"item": "grid_band_a", "price_ngn": 150, "effective_from": "2025-01-01", "source": "old"},
    ]
    store.save_telemetry(HOME, sim, db)
    store.save_summaries(HOME, sim, db)
    return db


def ctx_for(db, now=NOW, role="customer"):
    return ToolContext(HOME, client=db, role=role, now=now)


def set_latest(db, **values):
    """Overwrite the newest reading (to test particular situations)."""
    row = max(db.tables["telemetry"], key=lambda r: r["ts"])
    row.update(values)
    return row


# ---------- appliances ----------

def test_appliance_matching():
    assert find_appliance("Can I use my pressing iron?").name == "pressing iron"
    assert find_appliance("pumping machine").surge == 3.0
    assert find_appliance("my 1.5hp AC").watts == 1300            # longest alias wins
    assert find_appliance("the AC").watts == 900
    assert find_appliance("spaceship") is None


# ---------- tools ----------

def test_battery_now_matches_latest_reading(db):
    row = max(db.tables["telemetry"], key=lambda r: r["ts"])
    res = tools.battery_now(ctx_for(db))
    assert res["battery_percent"] == round(row["batt_soc"] * 100)
    assert res["house_using_w"] == round(row["load_w"])
    assert "warning" not in res                                  # reading is fresh
    late = tools.battery_now(ctx_for(db, NOW + pd.Timedelta(hours=2)))
    assert "offline" in late["warning"]


def test_battery_now_at_night_says_if_it_lasts_until_morning(db):
    night = START + pd.Timedelta(days=DAYS - 2, hours=23, minutes=30)
    rows = [r for r in db.tables["telemetry"] if pd.Timestamp(r["ts"]) <= night]
    latest = max(rows, key=lambda r: r["ts"])
    latest.update(batt_soc=1.0, batt_v=52.0, batt_a=-7.5, pv1_w=0, pv2_w=0, load_w=390)
    res = tools.battery_now(ctx_for(db, night))
    assert res["lasts_until_morning_sun"] and "empty_around" not in res
    latest.update(batt_soc=0.3, batt_a=-40.0)                   # ~2 kW, ~1.9 kWh left: ~1 hour
    res = tools.battery_now(ctx_for(db, night))
    assert res["empty_around"].startswith("tomorrow")           # runs out after midnight


def test_can_i_run_overload_and_unknown(db):
    res = tools.can_i_run(ctx_for(db), "welding machine", watts=7000)
    assert res["verdict"] == "no" and "limit" in res["reasons"][0]
    assert tools.can_i_run(ctx_for(db), "spaceship")["verdict"] == "need_watts"


def test_can_i_run_daytime_with_sun(db):
    set_latest(db, batt_soc=0.8, load_w=300, pv1_w=2500, pv2_w=1500, grid_v=0, fault_code=None)
    res = tools.can_i_run(ctx_for(db), "pressing iron")
    assert res["verdict"] == "yes" and res["powered_by"] == "solar"


def test_can_i_run_at_night_checks_the_battery_lasts(db):
    night = START + pd.Timedelta(days=DAYS - 2, hours=21)
    rows = [r for r in db.tables["telemetry"] if pd.Timestamp(r["ts"]) <= night]
    latest = max(rows, key=lambda r: r["ts"])
    common = {"load_w": 300, "pv1_w": 0, "pv2_w": 0, "grid_v": 0, "fault_code": None}
    latest.update(batt_soc=0.9, **common)
    assert tools.can_i_run(ctx_for(db, night), "pressing iron")["verdict"] == "yes"
    latest.update(batt_soc=0.25, **common)                      # low battery, long night ahead
    res = tools.can_i_run(ctx_for(db, night), "pressing iron")
    assert res["verdict"] == "yes_but"
    assert res["left_after_kwh"] < res["needed_until_morning_kwh"]
    latest.update(batt_soc=0.12, **common)                      # nearly empty
    assert tools.can_i_run(ctx_for(db, night), "pressing iron")["verdict"] == "no"


def test_can_i_run_on_nepa(db):
    set_latest(db, batt_soc=0.2, load_w=300, pv1_w=0, pv2_w=0, grid_v=230, fault_code=None)
    res = tools.can_i_run(ctx_for(db), "microwave")
    assert res["verdict"] == "yes" and res["powered_by"] == "nepa"


def test_tomorrow_plan(db, monkeypatch):
    monkeypatch.setattr(tools, "forecast_weather", lambda ctx: (HOURLY, "left"))
    res = tools.tomorrow_plan(ctx_for(db))
    assert res["expected_solar_kwh"] > 10                        # 8.8 kWp on a fairly sunny day
    assert res["normal_daily_use_kwh"] > 0
    assert res["best_hours_for_heavy_appliances"]               # some midday hours have spare sun
    assert res["expected_nepa_hours"] == 18.0                   # band A

    # a dead string 2 lowers the forecast
    store.save_health(HOME, pd.DataFrame(
        {"pr_pv1": [0.95] * 5, "pr_pv2": [0.0] * 5, "usable_steps": [50] * 5, "batt_heat_c": [3.0] * 5},
        index=pd.date_range(NOW.normalize() - pd.Timedelta(days=5), periods=5, freq="D")), db)
    weak = tools.tomorrow_plan(ctx_for(db))
    assert weak["weak_panel_strings"] == {"pv2": 0.0}
    assert weak["expected_solar_kwh"] < 0.6 * res["expected_solar_kwh"]


def test_tomorrow_plan_counts_an_open_dead_string(db, monkeypatch):
    monkeypatch.setattr(tools, "forecast_weather", lambda ctx: (HOURLY, "left"))
    full = tools.tomorrow_plan(ctx_for(db))["expected_solar_kwh"]
    db.tables["findings"] = [{"site_id": HOME.id, "kind": "string_failure", "status": "open",
                              "details": {"target": "pv1"}, "severity": "critical"}]
    res = tools.tomorrow_plan(ctx_for(db))                      # found today: no health history yet
    assert res["weak_panel_strings"] == {"pv1": 0.0}
    assert res["expected_solar_kwh"] == pytest.approx(full / 2, rel=0.05)


def test_money_view(db):
    res = tools.money_view(ctx_for(db), days=30)
    daily = [r for r in db.tables["telemetry_daily"] if r["day"] < NOW.strftime("%Y-%m-%d")]
    solar = sum(r["pv_kwh"] for r in daily)
    share = sum(r["grid_on_minutes"] for r in daily) / (len(daily) * 1440)
    expected = solar * share * 200 + solar * (1 - share) * 1000 / 1.5    # newest prices used
    assert res["period_days"] == len(daily)
    assert res["saved_by_solar_ngn"] == pytest.approx(expected, abs=100)
    assert "warning" not in res
    db.tables["prices"][0]["source"] = "PLACEHOLDER - update"
    assert "placeholders" in tools.money_view(ctx_for(db))["warning"]


def test_battery_card(db):
    assert "not measured" in tools.battery_card(ctx_for(db))["health"]
    est = pd.Series([0.95 - 0.0003 * i for i in range(60)],
                    index=pd.date_range(NOW - pd.Timedelta(days=150), periods=60, freq="60h"))
    store.save_battery_estimates(HOME, est, db)
    card = tools.battery_card(ctx_for(db))
    assert 90 <= card["health_percent"] <= 95 and card["status"] == "healthy"
    assert card["equivalent_full_cycles"] >= 1
    assert card["age_years"] > 1


def test_open_problems_hides_staff_only_findings(db):
    def finding(kind, sev, status, hours_ago, **details):
        t = NOW - pd.Timedelta(hours=hours_ago)
        return {"site_id": HOME.id, "kind": kind, "severity": sev, "status": status,
                "ts_start": _iso(t), "ts_end": None, "details": details, "dedupe_key": kind}
    db.tables["findings"] = [
        finding("soiling", "warning", "open", 300, target="all"),
        finding("string_failure", "critical", "open", 5, target="pv2"),
        finding("unusual_day", "info", "open", 20),
        finding("overload", "warning", "resolved", 30, target="all"),
        finding("overload", "warning", "resolved", 24 * 20, target="all"),   # too old to list
    ]
    res = tools.open_problems(ctx_for(db))
    assert [p["urgency"] for p in res["open_problems"]] == ["critical", "warning"]   # worst first
    assert res["open_problems"][0]["panel_string"] == "string 2"
    assert len(res["events_last_7_days"]) == 1 and not res["all_clear"]
    staff = tools.open_problems(ctx_for(db, role="staff"))
    assert any(p["kind"] == "unusual_day" for p in staff["open_problems"])


def test_run_tool_never_raises(db):
    assert "unknown tool" in run_tool(ctx_for(db), "launch_rocket", {})["error"]
    assert "bad arguments" in run_tool(ctx_for(db), "battery_now", {"x": 1})["error"]


# ---------- the agent loop ----------

class FakeLLM:
    """Plays back scripted turns and remembers what it was sent."""

    def __init__(self, turns):
        self.turns, self.seen = list(turns), []

    def generate(self, system, messages, tools, allow_tools=True):
        self.seen.append({"system": system, "messages": [dict(m) for m in messages],
                          "allow_tools": allow_tools})
        turn = self.turns.pop(0)
        if isinstance(turn, Exception):
            raise turn
        return turn


def test_guess_tools_from_the_question():
    def names(m):
        return [n for n, _ in guess_tools(m)]

    assert guess_tools("Can I use my pressing iron for 20 minutes?") == [
        ("can_i_run", {"appliance": "pressing iron", "minutes": 20.0})]
    assert names("Abeg, how my battery dey?") == ["battery_now"]
    assert names("Wetin dey wrong with my system?") == ["open_problems"]
    assert names("When should I pump water tomorrow?") == ["can_i_run", "tomorrow_plan"]
    assert names("Is light on?") == ["battery_now"]                # "light" = NEPA, not bulbs
    assert names("hello") == []


def test_reply_language():
    assert reply_language("Can I use my electric iron now?") == "en"
    assert reply_language("Abeg, how my battery dey?") == "pcm"
    assert reply_language("I wan pump water now, e go work?") == "pcm"
    assert reply_language("Wetin dey wrong?") == "pcm"
    assert reply_language("battery?", "pcm") == "pcm"            # too short: use the preference
    assert reply_language("battery?", "en") == "en"
    assert reply_language("Is the battery fit for the night?") == "en"   # English "fit"
    assert reply_language("Why don't my panels work?") == "en"


def test_battery_now_says_how_tonight_looks(db):
    day = tools.battery_now(ctx_for(db))                       # early afternoon
    assert day["normal_night_use_kwh"] > 0 and "tonight" in day
    night = START + pd.Timedelta(days=DAYS - 2, hours=22)
    late = tools.battery_now(ctx_for(db, night))
    assert late["needed_until_morning_kwh"] > 0 and "morning" in late["tonight"]


def test_prefetch_answers_in_one_gemini_call(db):
    set_latest(db, batt_soc=0.8, load_w=300, pv1_w=2500, pv2_w=1500, grid_v=0, fault_code=None)
    llm = FakeLLM([LLMTurn(text="Yes, iron now.")])
    r = Agent(llm, ctx_for(db)).reply("Can I use my pressing iron now?")
    assert r.text == "Yes, iron now." and r.timings["gemini_calls"] == 1
    sent = llm.seen[0]["messages"][-1]["text"]
    assert "LIVE DATA" in sent and '"verdict": "yes"' in sent
    assert sent.endswith("[Reply in English]")
    assert r.tool_calls[0]["name"] == "can_i_run"


def test_agent_runs_tools_then_answers(db):
    set_latest(db, batt_soc=0.8, load_w=300, pv1_w=2500, pv2_w=1500, grid_v=0, fault_code=None)
    llm = FakeLLM([LLMTurn(calls=[{"id": "1", "name": "can_i_run",
                                   "args": {"appliance": "pressing iron"}}]),
                   LLMTurn(text="Yes, you fit iron now. Sun dey strong.")])
    agent = Agent(llm, ctx_for(db), language="pcm")
    r = agent.reply("Abeg, I fit do am now?",                   # no keywords: Gemini picks tools
                    history=[{"role": "user", "text": "hi"}, {"role": "model", "text": "Hello!"}])
    assert r.ok and r.text.startswith("Yes")
    assert r.tool_calls[0]["result"]["verdict"] == "yes"
    sent = llm.seen[1]["messages"]
    assert [m["role"] for m in sent] == ["user", "model", "user", "model", "tool"]
    assert sent[-1]["results"][0]["result"]["appliance"] == "pressing iron"
    system = llm.seen[0]["system"]
    assert "Ikeja home" in system and "Nigerian Pidgin" in system and "10 kWh" in system


def test_agent_stops_runaway_tool_loops(db):
    call = LLMTurn(calls=[{"id": "x", "name": "battery_now", "args": {}}])
    llm = FakeLLM([call] * MAX_ROUNDS + [LLMTurn(text="Battery is at 80%.")])
    r = Agent(llm, ctx_for(db)).reply("hello?")
    assert r.text == "Battery is at 80%." and len(r.tool_calls) == MAX_ROUNDS
    assert llm.seen[-1]["allow_tools"] is False                 # last round must answer


def test_agent_falls_back_when_gemini_fails(db):
    r = Agent(FakeLLM([LLMError("quota")]), ctx_for(db), language="pcm").reply("battery?")
    assert not r.ok and r.text.startswith("Battery dey") and "no fit reach the AI" in r.text
    r = Agent(FakeLLM([LLMError("offline")]), ctx_for(db)).reply("Can I use my pressing iron now?")
    assert r.text.split(" ")[0] in ("Yes,", "Better") and "can't reach its AI" in r.text
    r = Agent(FakeLLM([LLMError("offline")]), ctx_for(db)).reply("Tell me a joke")
    assert "I can still answer" in r.text
