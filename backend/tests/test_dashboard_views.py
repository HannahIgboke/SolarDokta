"""Dashboard pictures and charts: the live twin, today's curves, money by month."""
# ruff: noqa: F811  (the db fixture is shared with test_agent)

import pandas as pd
import pytest

from app import dashboard_views as views
from tests.test_agent import (  # noqa: F401
    DAYS,
    HOURLY,
    START,
    ctx_for,
    db,
    set_latest,
    sim,
)


def test_likely_appliances_explain_the_power():
    evening = views.likely_appliances("home", 20.5, 1400)
    on = {a["name"] for a in evening if a["on"]}
    assert "security light" in on and "router" in on                 # always on at night
    assert sum(a["watts"] for a in evening if a["on"]) == pytest.approx(1400, abs=250)
    assert not any(a["on"] for a in views.likely_appliances("home", 12, 0) if a["name"] == "tv")


def test_live_view_shows_holding_back_when_battery_is_full(db, monkeypatch):
    monkeypatch.setattr(views, "forecast_weather", lambda ctx: (HOURLY, "left"))
    set_latest(db, batt_soc=1.0, batt_a=0.0, pv1_w=200, pv2_w=100, load_w=300, grid_v=0,
               fault_code=None)
    live = views.live_view(ctx_for(db))
    assert live["is_day"] and live["held_back_w"] > 1000             # 8.8 kWp at 1pm, using 300 W
    assert live["headline"].startswith("Battery full")
    assert [s["status"] for s in live["strings"]] == ["ok", "ok"]
    assert len(live["appliances"]) > 5


def test_live_view_marks_a_dead_string(db, monkeypatch):
    monkeypatch.setattr(views, "forecast_weather", lambda ctx: (HOURLY, "left"))
    db.tables["findings"] = [{"site_id": "site-1",
                              "kind": "string_failure", "status": "open",
                              "details": {"target": "pv2"}, "severity": "critical"}]
    live = views.live_view(ctx_for(db))
    assert live["strings"][1]["status"] == "dead"
    assert "Panel group 2" in live["headline"]
    assert "Otu panel 2" in views.headline(live, "ig")


def test_live_view_at_night(db, monkeypatch):
    monkeypatch.setattr(views, "forecast_weather", lambda ctx: (HOURLY, "left"))
    night = START + pd.Timedelta(days=DAYS - 2, hours=22)
    live = views.live_view(ctx_for(db, night))
    assert not live["is_day"] and live["sun"] == 0


def test_today_view_has_15_minute_points(db, monkeypatch):
    monkeypatch.setattr(views, "forecast_weather", lambda ctx: (HOURLY, "left"))
    today = views.today_view(ctx_for(db))
    assert len(today["points"]) == 13 * 4 + 1                        # midnight to 1pm
    noon = next(p for p in today["points"] if p["time"] == "12:00")
    assert noon["could_make_w"] >= noon["solar_w"] and "battery_percent" in noon


def test_money_history_by_month(db):
    db.tables["telemetry_daily"].append({**db.tables["telemetry_daily"][0], "day": "2026-01-15"})
    res = views.money_history(ctx_for(db), months=3)
    assert [m["month"] for m in res["months"]] == ["Jan", "Feb"]
    assert res["months"][1]["saved_ngn"] > 0 and res["estimate"] is False


def test_usage_view_by_hour_and_by_day(db):
    ctx = ctx_for(db)
    day = ctx.time.strftime("%Y-%m-%d")
    one = views.usage_view(ctx, day, day)
    assert one["mode"] == "hours" and one["points"] and one["points"][0]["label"].endswith("am")
    assert one["story"][0].startswith("Your panels made")
    week = views.usage_view(ctx, (ctx.time - pd.Timedelta(days=6)).strftime("%Y-%m-%d"), day)
    assert week["mode"] == "days" and 2 <= len(week["points"]) <= 7
    assert week["totals"]["days"] == len(week["points"])
    assert views.usage_view(ctx, "not a date")["error"]


def test_live_view_reports_the_device(db, monkeypatch):
    monkeypatch.setattr(views, "forecast_weather", lambda ctx: (HOURLY, "left"))
    dev = views.live_view(ctx_for(db))["device"]
    assert dev["name"] == "SolarDokta Link" and dev["connected"] in (True, False)
    assert dev["last_seen_minutes"] >= 0


def test_battery_report_projects_with_and_without_heat(db):
    from app.battery_report import report
    for r in db.tables["telemetry_daily"]:
        r["batt_temp_max"] = 38.0                         # El Niño-hot battery room
    rep = report(ctx_for(db))
    assert rep["rated_cycles"] == 6000 and rep["grade"] in "ABCD"
    assert rep["fade_el_nino_percent"] > rep["fade_cool_percent"]
    assert rep["projection"][0]["soh"] == rep["projection_cool"][0]["soh"]
    assert rep["projection"][12]["soh"] < rep["projection_cool"][12]["soh"]
    assert rep["summary"] and rep["soc_percent"] is not None
