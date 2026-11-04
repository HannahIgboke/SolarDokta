"""WhatsApp: Twilio's signature, who gets which answer, voice notes, and alerts out."""

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app import dashboard, main, whatsapp
from app.agent import tools
from app.agent.llm import LLMTurn
from app.config import get_settings
from tests.fakedb import FakeDB
from tests.test_dashboard_api import ORG, site_row

TOKEN = "test-auth-token"
URL = "https://api.test/whatsapp/webhook"


class OneLine:
    last_model = "fake"

    def __init__(self, text="Your battery dey fine."):
        self.text, self.calls = text, []

    def generate(self, system, messages, tools, allow_tools=True):
        self.calls.append((system, messages))
        return LLMTurn(text=self.text)


@pytest.fixture
def wa(monkeypatch):
    db = FakeDB()
    db.tables["profiles"] = [
        {"id": "u-staff", "org_id": ORG, "role": "staff", "full_name": "Tunde",
         "whatsapp_number": "+2348030000001", "preferred_language": "en"},
        {"id": "u-ada", "org_id": ORG, "role": "customer", "full_name": "Ada",
         "whatsapp_number": "0803 000 0002", "preferred_language": "pcm"},
    ]
    db.tables["sites"] = [site_row("lagos-001", "s1", ORG, customer="u-ada"),
                          site_row("lagos-002", "s2", ORG)]
    for mod in (dashboard, tools, whatsapp):
        monkeypatch.setattr(mod, "get_client", lambda: db)
    s = get_settings()
    for k, v in {"twilio_auth_token": TOKEN, "twilio_account_sid": "AC1", "public_api_url": "https://api.test",
                 "whatsapp_demo": True, "demo_site": "lagos-001", "alerts_enabled": True}.items():
        monkeypatch.setattr(s, k, v)
    outbox = []
    monkeypatch.setattr(whatsapp, "send", lambda to, body, status_callback=False, from_=None: outbox.append((to, body)) or "SM1")
    llm = OneLine()
    monkeypatch.setattr(dashboard, "_llm", llm)
    whatsapp._recent.clear()
    whatsapp._seen.clear()
    return TestClient(main.app), db, outbox, llm


def post(client, params, sign=True):
    import base64
    import hashlib
    import hmac
    payload = URL + "".join(k + params[k] for k in sorted(params))
    good = base64.b64encode(hmac.new(TOKEN.encode(), payload.encode(), hashlib.sha1).digest()).decode()
    return client.post("/whatsapp/webhook", data=params,
                       headers={"X-Twilio-Signature": good if sign else "forged"})


def test_phone_numbers_are_normalised():
    assert whatsapp.normalize_phone("whatsapp:+234 803 000 0002") == "+2348030000002"
    assert whatsapp.normalize_phone("08030000002") == "+2348030000002"


def test_unsigned_requests_are_refused(wa):
    client, _, outbox, _ = wa
    r = post(client, {"From": "whatsapp:+2348030000002", "Body": "hi", "MessageSid": "SMa"}, sign=False)
    assert r.status_code == 403 and outbox == []


def test_customer_gets_an_answer_about_their_own_home(wa):
    client, db, outbox, llm = wa
    r = post(client, {"From": "whatsapp:+2348030000002", "Body": "How my battery dey?", "MessageSid": "SMb"})
    assert r.status_code == 200 and "<Response>" in r.text
    assert outbox == [("+2348030000002", "Your battery dey fine.")]
    assert "lagos-001 home" in llm.calls[0][0]                          # Ada's site, not another
    saved = db.tables["conversations"]
    assert [m["direction"] for m in saved] == ["in", "out"] and saved[0]["profile_id"] == "u-ada"
    post(client, {"From": "whatsapp:+2348030000002", "Body": "How my battery dey?", "MessageSid": "SMb"})
    assert len(outbox) == 1                                             # Twilio retry ignored


def test_conversation_history_is_remembered(wa):
    client, _, _, llm = wa
    post(client, {"From": "whatsapp:+2348030000002", "Body": "Can I iron?", "MessageSid": "SM1"})
    post(client, {"From": "whatsapp:+2348030000002", "Body": "And tomorrow?", "MessageSid": "SM2"})
    texts = [m.get("text") for m in llm.calls[-1][1]]
    assert "Can I iron?" in texts and "Your battery dey fine." in texts


def test_unknown_numbers_get_the_demo_with_a_welcome_and_a_limit(wa, monkeypatch):
    client, _, outbox, _ = wa
    monkeypatch.setattr(get_settings(), "demo_chat_per_hour", 2)
    for i in range(3):
        post(client, {"From": "whatsapp:+447700900123", "Body": "Can I iron now?", "MessageSid": f"SMd{i}"})
    assert outbox[0][1].startswith("Welcome to the SolarDokta demo")
    assert not outbox[1][1].startswith("Welcome")                       # welcome only once
    assert outbox[2][1] == whatsapp.TOO_MANY


def test_unknown_numbers_are_told_when_the_demo_is_off(wa, monkeypatch):
    client, _, outbox, _ = wa
    monkeypatch.setattr(get_settings(), "whatsapp_demo", False)
    post(client, {"From": "whatsapp:+447700900123", "Body": "hi", "MessageSid": "SMe"})
    assert outbox == [("+447700900123", whatsapp.NOT_LINKED)]


def test_technicians_get_fleet_answers(wa, monkeypatch):
    client, _, outbox, llm = wa
    from app import staff_api
    monkeypatch.setattr(staff_api, "get_client", lambda: dashboard.get_client())
    monkeypatch.setattr(staff_api, "fleet", lambda profile: {"sites": [{"code": "lagos-001"}]})
    post(client, {"From": "whatsapp:+2348030000001", "Body": "Which site first?", "MessageSid": "SMf"})
    assert "FLEET DATA" in llm.calls[0][0] and outbox[0][0] == "+2348030000001"


def test_voice_notes_are_transcribed_then_answered(wa, monkeypatch):
    client, _, outbox, llm = wa
    from app.agent import reader
    monkeypatch.setattr(whatsapp, "_download", lambda url: b"OggS...")
    monkeypatch.setattr(reader, "read_file", lambda kind, data, mime: {"transcript": "Battery go reach morning?"})
    post(client, {"From": "whatsapp:+2348030000002", "Body": "", "NumMedia": "1", "MessageSid": "SMv",
                  "MediaUrl0": "https://api.twilio.com/media/1", "MediaContentType0": "audio/ogg"})
    asked = [m.get("text") or "" for m in llm.calls[0][1]]
    assert any(t.startswith("Battery go reach morning?") for t in asked)
    assert outbox[0][1].startswith('🎙️ "Battery go reach morning?"')


def test_photos_point_to_the_app(wa):
    client, _, outbox, llm = wa
    post(client, {"From": "whatsapp:+2348030000002", "Body": "", "NumMedia": "1", "MessageSid": "SMp",
                  "MediaUrl0": "https://api.twilio.com/media/2", "MediaContentType0": "image/jpeg"})
    assert "Tell us" in outbox[0][1] and llm.calls == []


# ---------- alerts out ----------

NOON = pd.Timestamp("2026-11-04 11:00", tz="UTC")          # 12 noon in Lagos


def finding(fid, kind, severity, created, site="s1", details=None):
    return {"id": fid, "site_id": site, "kind": kind, "severity": severity, "status": "open",
            "ts_start": (created - pd.Timedelta(minutes=30)).isoformat(), "details": details or {},
            "created_at": created.isoformat()}


def test_alerts_go_to_the_right_people_in_their_language(wa):
    _, db, _, _ = wa
    db.tables["findings"] = [
        finding("f1", "soiling", "warning", NOON - pd.Timedelta(hours=1)),
        finding("f2", "string_failure", "critical", NOON - pd.Timedelta(hours=1), details={"target": "pv2"}),
        finding("f3", "unusual_day", "info", NOON - pd.Timedelta(hours=1)),         # technicians' screen only
        finding("f4", "soiling", "warning", NOON - pd.Timedelta(days=2)),           # too old
    ]
    sent = []
    out = whatsapp.send_alerts(db, now=NOON, sender=lambda to, body: sent.append((to, body)) or "SMx")
    assert out["sent"] == 3
    ada = [b for to, b in sent if to == "+2348030000002"]
    assert len(ada) == 2 and "Dust don cover your panel" in ada[0]               # Pidgin, as she prefers
    tunde = [b for to, b in sent if to == "+2348030000001"]
    assert len(tunde) == 1 and "CRITICAL" in tunde[0] and "string 2" in tunde[0] and "Ada" in tunde[0]
    again = whatsapp.send_alerts(db, now=NOON + pd.Timedelta(hours=1), sender=lambda to, body: "SMy")
    assert again["sent"] == 0                                                     # never twice


def test_alerts_wait_for_morning_except_critical_ones(wa):
    _, db, _, _ = wa
    night = pd.Timestamp("2026-11-04 22:00", tz="UTC")                          # 11 pm in Lagos
    db.tables["findings"] = [finding("f1", "overload", "warning", night - pd.Timedelta(minutes=20)),
                             finding("f2", "string_failure", "critical", night - pd.Timedelta(minutes=20))]
    out = whatsapp.send_alerts(db, now=night, sender=lambda to, body: "SMz")
    assert out["sent"] == 2 and out["held_for_morning"] == 1
    morning = whatsapp.send_alerts(db, now=night + pd.Timedelta(hours=8), sender=lambda to, body: "SMz")
    assert morning["sent"] == 1


def test_repeated_events_are_sent_at_most_once_a_day(wa):
    _, db, _, _ = wa
    db.tables["findings"] = [finding("f1", "overload", "warning", NOON - pd.Timedelta(hours=3)),
                             finding("f2", "overload", "warning", NOON - pd.Timedelta(hours=1))]
    assert whatsapp.send_alerts(db, now=NOON, sender=lambda to, body: "SM")["sent"] == 1


def test_delivery_reports_update_the_alert(wa):
    client, db, _, _ = wa
    db.tables["alerts"] = [{"id": "a1", "provider_message_id": "SM9", "status": "sent"}]
    import base64
    import hashlib
    import hmac
    params = {"MessageSid": "SM9", "MessageStatus": "read"}
    url = "https://api.test/whatsapp/status"
    payload = url + "".join(k + params[k] for k in sorted(params))
    sig = base64.b64encode(hmac.new(TOKEN.encode(), payload.encode(), hashlib.sha1).digest()).decode()
    r = client.post("/whatsapp/status", data=params, headers={"X-Twilio-Signature": sig})
    assert r.status_code == 204 and db.tables["alerts"][0]["status"] == "read"


def test_replies_come_from_the_number_they_wrote_to(wa, monkeypatch):
    client, _, _, _ = wa
    sent = []
    monkeypatch.setattr(whatsapp, "send", lambda to, body, status_callback=False, from_=None: sent.append(from_))
    post(client, {"From": "whatsapp:+2348030000002", "To": "whatsapp:+17372508034", "Body": "hi", "MessageSid": "SMt"})
    assert sent == ["whatsapp:+17372508034"]


def test_twilio_refusals_say_why(monkeypatch):
    import httpx
    s = get_settings()
    monkeypatch.setattr(s, "twilio_account_sid", "AC1")
    monkeypatch.setattr(s, "twilio_auth_token", TOKEN)
    monkeypatch.setattr(httpx, "post", lambda *a, **k: httpx.Response(
        400, json={"code": 63007, "message": "Twilio could not find a Channel with the specified From address"}))
    with pytest.raises(whatsapp.TwilioError, match="63007"):
        whatsapp.send("+2348030000002", "hello", from_="whatsapp:+14155238886")
