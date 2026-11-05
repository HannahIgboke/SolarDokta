"""SolarDokta on WhatsApp, through Twilio.

In:   POST /whatsapp/webhook   Twilio calls this for every message sent to our WhatsApp number.
      Text or a voice note goes to the same Ask Dokta agent as the web app. Customers get answers
      about their own home; technicians get answers about all their sites. A number that isn't
      linked to anyone chats with the demo home (WHATSAPP_DEMO), a few questions an hour.
Out:  the "alerts" job (hourly, after detection) sends each new problem to the customer in their
      language, and critical ones to the installer's technicians: as phone notifications (push.py)
      and, when WHATSAPP_ALERTS is on, by WhatsApp.
      POST /whatsapp/status    Twilio reports whether each alert was delivered, read or failed.

Twilio signs every request (X-Twilio-Signature) with our auth token, so nobody else can post to
these endpoints. We answer Twilio straight away and do the slow work (AI, voice) in the
background, then send the reply through Twilio's API, because Twilio only waits 15 seconds.

Voice notes are transcribed and the audio is thrown away. Conversations are kept 90 days.
"""

import base64
import hashlib
import hmac
import logging
import time
from collections import defaultdict, deque
from types import SimpleNamespace

import httpx
import pandas as pd
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response, status

from app.config import get_settings
from app.db import get_client
from app.simulator.faults import _iso
from app.simulator.site import _from_row

log = logging.getLogger(__name__)
router = APIRouter(prefix="/whatsapp")

TWIML_OK = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'
MAX_AUDIO = 5 * 1024 * 1024
HISTORY_HOURS = 24
KEEP_DAYS = 90


# ---------- small helpers ----------

def normalize_phone(raw: str | None) -> str:
    """'whatsapp:+234 801 234 5678' or '08012345678' -> '+2348012345678'."""
    digits = "".join(ch for ch in (raw or "") if ch.isdigit())
    if digits.startswith("0") and len(digits) == 11:            # Nigerian local format
        digits = "234" + digits[1:]
    return "+" + digits if digits else ""


def signature_ok(url: str, params: dict, signature: str | None, token: str) -> bool:
    """Twilio's check: HMAC-SHA1 of the URL followed by every form field (sorted), base64."""
    if not signature or not token:
        return False
    payload = url + "".join(k + params[k] for k in sorted(params))
    expected = base64.b64encode(hmac.new(token.encode(), payload.encode(), hashlib.sha1).digest()).decode()
    return hmac.compare_digest(expected, signature)


def _public_url(request: Request) -> str:
    base = get_settings().public_api_url.rstrip("/")
    if base:
        return base + request.url.path
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    return f"{proto}://{request.headers.get('host', request.url.netloc)}{request.url.path}"


async def _verified_form(request: Request) -> dict:
    form = await request.form()
    params = {k: str(v) for k, v in form.items()}
    token = get_settings().twilio_auth_token
    if not token:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "WhatsApp is not set up on the server")
    if not signature_ok(_public_url(request), params, request.headers.get("x-twilio-signature"), token):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bad Twilio signature")
    return params


class TwilioError(RuntimeError):
    """Twilio refused a message; the text says why (e.g. code 63007: unknown 'From' number)."""


def send(to: str, body: str, status_callback: bool = False, from_: str | None = None) -> str | None:
    """Send one WhatsApp message through Twilio. Returns Twilio's message id."""
    s = get_settings()
    if not (s.twilio_account_sid and s.twilio_auth_token):
        raise RuntimeError("TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN are not set")
    # Reply from the number the person wrote to (from_), so a wrong TWILIO_WHATSAPP_FROM can't break replies.
    sender = from_ if (from_ or "").startswith("whatsapp:") else s.twilio_whatsapp_from
    data = {"From": sender, "To": f"whatsapp:{normalize_phone(to)}", "Body": body[:1500]}
    if status_callback and s.public_api_url:
        data["StatusCallback"] = s.public_api_url.rstrip("/") + "/whatsapp/status"
    r = httpx.post(f"https://api.twilio.com/2010-04-01/Accounts/{s.twilio_account_sid}/Messages.json",
                   data=data, auth=(s.twilio_account_sid, s.twilio_auth_token), timeout=15)
    if r.status_code >= 400:
        try:
            err = r.json()
            why = f"code {err.get('code')}: {err.get('message')} (from {sender})"
        except ValueError:
            why = r.text[:300]
        raise TwilioError(f"Twilio said {r.status_code}, {why}")
    return r.json().get("sid")


def _download(url: str) -> bytes:
    s = get_settings()
    with httpx.stream("GET", url, auth=(s.twilio_account_sid, s.twilio_auth_token),
                      follow_redirects=True, timeout=30) as r:
        r.raise_for_status()
        data = b""
        for chunk in r.iter_bytes():
            data += chunk
            if len(data) > MAX_AUDIO:
                raise ValueError("voice note too long")
    return data


# ---------- who is writing? ----------

def find_person(phone: str, client) -> dict | None:
    """The profile whose WhatsApp number matches (customers and technicians)."""
    rows = (client.table("profiles").select("id,org_id,role,full_name,whatsapp_number,preferred_language")
            .range(0, 4999).execute().data)
    for p in rows:
        if p.get("whatsapp_number") and normalize_phone(p["whatsapp_number"]) == phone:
            return p
    return None


def _customer_site(person: dict, client):
    rows = client.table("sites").select("*").eq("customer_id", person["id"]).order("code").execute().data
    return _from_row(rows[0]) if rows else None


def _demo_site(client):
    rows = client.table("sites").select("*").eq("code", get_settings().demo_site).execute().data
    return _from_row(rows[0]) if rows else None


_recent: dict[str, deque] = defaultdict(deque)       # phone -> question times (last hour)
_seen: deque = deque(maxlen=500)                     # Twilio message ids already handled


def _allowed(phone: str, limit: int) -> bool:
    times, now = _recent[phone], time.time()
    while times and now - times[0] > 3600:
        times.popleft()
    if len(times) >= limit:
        return False
    times.append(now)
    return True


# ---------- conversation memory ----------

def _history(phone: str, client) -> list[dict]:
    since = pd.Timestamp.now(tz="UTC") - pd.Timedelta(hours=HISTORY_HOURS)
    rows = (client.table("conversations").select("direction,content,created_at").eq("phone", phone)
            .gte("created_at", _iso(since)).order("created_at", desc=True).range(0, 9).execute().data)
    return [{"role": "user" if r["direction"] == "in" else "model", "text": r["content"]}
            for r in reversed(rows)]


def _has_chatted(phone: str, client) -> bool:
    return bool(client.table("conversations").select("id").eq("phone", phone).range(0, 0).execute().data)


def _log(client, phone: str, direction: str, kind: str, content: str, site=None,
         person: dict | None = None, tools: list | None = None) -> None:
    try:
        client.table("conversations").insert({
            "site_id": site.id if site else None, "profile_id": (person or {}).get("id"),
            "phone": phone, "direction": direction, "message_type": kind,
            "content": content[:4000], "tool_calls": tools or None,
            "created_at": _iso(pd.Timestamp.now(tz="UTC")),
        }, returning="minimal").execute()
    except Exception:
        log.exception("Couldn't save WhatsApp message")


# ---------- answering ----------

WELCOME = ("Welcome to the SolarDokta demo! You're chatting with a live, simulated solar home in "
           "Ikeja. Ask me anything, in English, Pidgin or Igbo, by text or voice note. Try:\n"
           "• Can I iron now?\n• Will my battery last tonight?\n• Wetin dey worry my panel?")
NOT_LINKED = ("Hello! This number isn't linked to a SolarDokta system yet. "
              "Ask your installer to add your WhatsApp number to your account.")
TOO_MANY = "You've asked a lot this hour. Please try again a little later."
PHOTO = {"en": "Thanks! To send a receipt or a photo of your equipment, use 'Tell us' in the "
               "SolarDokta app{link}. Here I can answer text and voice questions.",
         "pcm": "Thank you! To send receipt or picture of your equipment, use 'Tell us' for the "
                "SolarDokta app{link}. For here, I fit answer text and voice question.",
         "ig": "Daalụ! Iji zipu akwụkwọ ọnụahịa ma ọ bụ foto, jiri 'Tell us' na ngwa SolarDokta{link}. "
               "Ebe a, m na-aza ajụjụ ederede na olu."}
SORRY = "Sorry, I couldn't answer just now. Please try again in a minute."


def _agent_answer(site, person: dict, text: str, history: list[dict], role: str = "customer"):
    from app import dashboard
    from app.agent.agent import Agent
    from app.agent.providers import make_llm
    from app.agent.tools import ToolContext

    dashboard._llm = dashboard._llm or make_llm()
    agent = Agent(dashboard._llm, ToolContext(site, role=role),
                  language=person.get("preferred_language") or "en")
    r = agent.reply(text, history)
    log.info("WhatsApp on %s answered by %s in %ss", site.code, r.timings.get("model") or "no AI",
             r.timings.get("seconds"))
    return r.text, [c["name"] for c in r.tool_calls]


def handle(params: dict) -> None:
    """Everything after Twilio's call: work out who it is, understand the message, reply."""
    client, s = get_client(), get_settings()
    phone = normalize_phone(params.get("From"))
    if not phone:
        return
    ours = params.get("To")                       # our WhatsApp number, as the person wrote to it

    def reply(body: str) -> None:
        send(phone, body, from_=ours)

    try:
        person = find_person(phone, client)
        demo = person is None
        if demo:
            if not s.whatsapp_demo:
                reply(NOT_LINKED)
                return
            person = {"id": None, "role": "customer", "preferred_language": "en"}
        lang = person.get("preferred_language") or "en"
        site = None
        if person["role"] == "customer":
            site = _demo_site(client) if demo else _customer_site(person, client)
            if site is None:
                reply(NOT_LINKED)
                return
        if not _allowed(phone, s.demo_chat_per_hour if demo else s.whatsapp_per_hour):
            reply(TOO_MANY)
            return

        text, kind = (params.get("Body") or "").strip(), "text"
        media_type = (params.get("MediaContentType0") or "").split(";")[0].strip().lower()
        if int(params.get("NumMedia") or 0) > 0:
            if media_type.startswith("audio/"):
                from app.agent import reader

                heard = reader.read_file("question", _download(params["MediaUrl0"]), media_type)
                text, kind = (heard.get("transcript") or "").strip()[:1000], "voice"
                if not text:
                    reply("I couldn't hear that clearly. Please try again or type it.")
                    return
            elif not text:
                link = f" ({s.app_url.rstrip('/')})" if s.app_url else ""
                reply(PHOTO.get(lang, PHOTO["en"]).format(link=link))
                return
        if not text:
            return

        first_time = demo and not _has_chatted(phone, client)
        history = _history(phone, client)
        _log(client, phone, "in", kind, text, site, None if demo else person)
        if person["role"] == "staff":
            from app.staff_api import fleet_answer

            answer, tools = fleet_answer(person, text, history)[0], []
        else:
            answer, tools = _agent_answer(site, person, text, history)
        if kind == "voice":
            answer = f'🎙️ "{text}"\n\n{answer}'
        if first_time:
            answer = f"{WELCOME}\n\n{answer}"
        _log(client, phone, "out", "text", answer, site, None if demo else person, tools)
        reply(answer)
    except Exception:
        log.exception("WhatsApp message from %s failed", phone[:6] + "…")
        try:
            reply(SORRY)
        except Exception:
            log.exception("Couldn't even send the apology")


@router.post("/webhook")
async def webhook(request: Request, background: BackgroundTasks) -> Response:
    params = await _verified_form(request)
    sid = params.get("MessageSid") or params.get("SmsMessageSid")
    if sid and sid in _seen:                       # Twilio retried: already handled
        return Response(TWIML_OK, media_type="application/xml")
    if sid:
        _seen.append(sid)
    background.add_task(handle, params)
    return Response(TWIML_OK, media_type="application/xml")


@router.post("/status")
async def delivery_status(request: Request) -> Response:
    """Twilio tells us what happened to an alert: delivered, read or failed."""
    params = await _verified_form(request)
    state = params.get("MessageStatus")
    if params.get("MessageSid") and state in ("sent", "delivered", "read", "failed", "undelivered"):
        get_client().table("alerts").update({"status": "failed" if state == "undelivered" else state}) \
            .eq("provider_message_id", params["MessageSid"]).execute()
    return Response(status_code=204)


# ---------- alerts out ----------

CUSTOMER_ALERTS = {
    "string_failure": {
        "en": "⚠️ One set of your panels stopped producing at {time}, so you'll get less solar until "
              "it's fixed. We've told your installer. Please don't climb up or touch the wiring.",
        "pcm": "⚠️ One set of your panel don stop to produce since {time}, so solar go reduce until dem "
               "fix am. We don tell your installer. Abeg no climb roof or touch any wire.",
        "ig": "⚠️ Otu akụkụ panel gị akwụsịla ịrụ ọrụ kemgbe {time}. Anyị agwala onye nrụnye gị. "
              "Biko arịgola n'elu ụlọ ma ọ bụ metụ waya aka."},
    "overload": {
        "en": "Your inverter switched off at {time} because too many big appliances were on at once. "
              "Use the iron, pump, AC or microwave one at a time.",
        "pcm": "Your inverter off for {time} because too many big appliance dey on at once. "
               "Use iron, pumping machine, AC or microwave one by one.",
        "ig": "Inverter gị gbanyụrụ na {time} n'ihi na ọtụtụ ngwa ọkụ buru ibu nọ na ya otu oge. "
              "Jiri ígwè, pump, AC ma ọ bụ microwave otu otu."},
    "battery_ran_out": {
        "en": "Your battery ran empty at {time} and the power went off. Use less at night and run heavy "
              "appliances in the afternoon sun. Ask me \"will my battery last tonight?\"",
        "pcm": "Your battery finish for {time} and light off. Use small thing for night, run heavy "
               "appliance for afternoon when sun strong. Ask me \"battery go reach morning?\"",
        "ig": "Batrị gị gwụrụ na {time}, ọkụ wee anyụ. N'abalị, jiri obere ọkụ; jiri ngwa ọkụ buru ibu "
              "n'ehihie mgbe anyanwụ siri ike."},
    "soiling": {
        "en": "Dust on your panels is cutting your solar power. Have them washed with clean water early "
              "morning or evening.",
        "pcm": "Dust don cover your panel, e dey reduce your solar. Make dem wash am with clean water "
               "early morning or evening.",
        "ig": "Ájá dị na panel gị na-ebelata ike anyanwụ gị. Jiri mmiri dị ọcha saa ha n'ụtụtụ "
              "ma ọ bụ n'anyasị."},
    "hot_battery_room": {
        "en": "Your battery is staying hot, which ages it faster in this El Niño heat. Open up the room "
              "or add a fan, and keep it out of direct sun.",
        "pcm": "Your battery dey hot pass, e go make am spoil quick for this El Niño heat. Open the room "
               "or put fan, no let sun touch am.",
        "ig": "Batrị gị na-ekpo ọkụ nke ukwuu, nke na-eme ka ọ mebie ngwa ngwa n'oge okpomọkụ El Niño a. "
              "Meghee ọnụ ụlọ ahụ ma ọ bụ tinye fan."},
    "battery_fade": {
        "en": "Your battery is losing capacity faster than normal. We've told your installer; it may be "
              "a warranty case.",
        "pcm": "Your battery dey lose power pass how e suppose. We don tell your installer; e fit be "
               "warranty matter.",
        "ig": "Batrị gị na-efunahụ ike karịa ka o kwesịrị. Anyị agwala onye nrụnye gị; ọ nwere ike ịbụ "
              "okwu warranty."},
    "underrated_panel": {
        "en": "One set of your panels gives much less than it should. We've told your installer; it may "
              "be covered by warranty.",
        "pcm": "One set of your panel no dey give the power wey e suppose give. We don tell your installer.",
        "ig": "Otu akụkụ panel gị anaghị enye ike ha kwesịrị inye. Anyị agwala onye nrụnye gị."},
    "heatwave": {
        "en": "Very hot day forecast tomorrow ({high}°C). Keep the battery room airy, and expect a little "
              "less solar at midday.",
        "pcm": "Tomorrow go hot well well ({high}°C). Make air dey enter the battery room; solar fit "
               "reduce small for afternoon.",
        "ig": "Echi ga-ekpo ọkụ nke ukwuu ({high}°C). Hapụ ikuku ka ọ banye n'ọnụ ụlọ batrị."},
}
FOOTER = {"en": "Reply here to ask me anything.", "pcm": "Reply me if you get question.",
          "ig": "Zaa m ma ị nwere ajụjụ."}
STAFF_KINDS = {"string_failure", "customer_report"}       # technicians hear about these at once
LOOKBACK = pd.Timedelta(hours=12)
COOLDOWN = pd.Timedelta(hours=24)                         # same problem, same person: once a day


def _quiet(now_lagos: pd.Timestamp) -> bool:
    """No non-urgent messages between 9:30 pm and 6:30 am."""
    minutes = now_lagos.hour * 60 + now_lagos.minute
    return minutes >= 21 * 60 + 30 or minutes < 6 * 60 + 30


def customer_message(kind: str, finding: dict, lang: str, tz: str) -> str:
    texts = CUSTOMER_ALERTS[kind]
    when = pd.Timestamp(finding["ts_start"]).tz_convert(tz).strftime("%I:%M %p").lstrip("0")
    high = (finding.get("details") or {}).get("high_c", "")
    body = texts.get(lang, texts["en"]).format(time=when, high=high)
    return f"SolarDokta: {body}\n{FOOTER.get(lang, FOOTER['en'])}"


def staff_message(kind: str, finding: dict, site_row: dict, customer: dict | None) -> str:
    from app.agent.tools import PLAIN

    what, todo = PLAIN.get(kind, (kind.replace("_", " "), "check the site"))
    who = f" Customer: {customer.get('full_name')}." if customer else ""
    target = (finding.get("details") or {}).get("target")
    which = f" ({'string 1' if target == 'pv1' else 'string 2'})" if target in ("pv1", "pv2") else ""
    return (f"SolarDokta [{finding['severity'].upper()}] {site_row['name']} ({site_row['code']}): "
            f"{what}{which}. To do: {todo}.{who}")


def _push_text(kind: str, finding: dict, site: dict, lang: str, customer: dict | None, staff: bool) -> dict:
    """A phone notification: short title, the same plain message, and where tapping it goes."""
    if staff:
        from app.agent.tools import PLAIN

        what, todo = PLAIN.get(kind, (kind.replace("_", " "), "check the site"))
        target = (finding.get("details") or {}).get("target")
        which = f" ({'string 1' if target == 'pv1' else 'string 2'})" if target in ("pv1", "pv2") else ""
        who = f" Customer: {customer.get('full_name')}." if customer else ""
        return {"title": f"[{finding['severity'].upper()}] {site['name']}",
                "body": f"{what[0].upper()}{what[1:]}{which}. {todo[0].upper()}{todo[1:]}.{who}",
                "url": f"/staff/sites/{site['code']}#problems", "tag": f"{site['code']}-{kind}"}
    texts = CUSTOMER_ALERTS[kind]
    when = pd.Timestamp(finding["ts_start"]).tz_convert(site.get("timezone") or "Africa/Lagos")
    body = texts.get(lang, texts["en"]).format(time=when.strftime("%I:%M %p").lstrip("0"),
                                               high=(finding.get("details") or {}).get("high_c", ""))
    return {"title": f"SolarDokta: {site['name']}", "body": body, "url": "/my", "tag": f"{site['code']}-{kind}"}


def send_alerts(client=None, now: pd.Timestamp | None = None, sender=None, pusher=None) -> dict:
    """Tell people about problems found in the last 12 hours that nobody has been told about,
    by phone notification (push) and, when WHATSAPP_ALERTS is on, by WhatsApp."""
    from app import push

    client, s = client or get_client(), get_settings()
    if not s.alerts_enabled:
        return {"sent": 0, "note": "alerts are switched off"}
    sender = sender or (lambda to, body: send(to, body, status_callback=True))
    pusher = pusher or push.deliver
    use_whatsapp = s.whatsapp_alerts
    use_push = pusher is not push.deliver or push.configured()
    now = now or pd.Timestamp.now(tz="UTC")
    quiet = _quiet(now.tz_convert("Africa/Lagos"))
    findings = (client.table("findings").select("id,site_id,kind,severity,status,ts_start,details,created_at")
                .gte("created_at", _iso(now - LOOKBACK)).order("created_at").range(0, 999).execute().data)
    past = (client.table("alerts").select("finding_id,recipient,template,site_id,created_at")
            .gte("created_at", _iso(now - COOLDOWN - LOOKBACK)).range(0, 4999).execute().data)
    told = {(a["finding_id"], a["recipient"]) for a in past}
    recent = {(a["site_id"], a["template"], a["recipient"]) for a in past
              if pd.Timestamp(a["created_at"]) >= now - COOLDOWN}
    profiles = {p["id"]: p for p in client.table("profiles").select(
        "id,org_id,role,full_name,whatsapp_number,preferred_language").range(0, 4999).execute().data}
    sites = {r["id"]: r for r in client.table("sites").select("*").range(0, 4999).execute().data}
    subs = push.subscriptions(client) if use_push else []

    sent = failed = held = 0
    for f in findings:
        site = sites.get(f["site_id"])
        if not site or f["status"] == "dismissed":
            continue
        kind, urgent = f["kind"], f["severity"] == "critical"
        customer = profiles.get(site.get("customer_id"))
        out = []          # (channel, recipient, text for the log, how to send it)
        if kind in CUSTOMER_ALERTS:
            if use_whatsapp and customer and customer.get("whatsapp_number"):
                lang = customer.get("preferred_language") or "en"
                body = customer_message(kind, f, lang, site.get("timezone") or "Africa/Lagos")
                out.append(("whatsapp", normalize_phone(customer["whatsapp_number"]), body, None))
            for sub in subs:
                if sub["role"] == "customer" and sub.get("site_id") == site["id"]:
                    msg = _push_text(kind, f, site, sub.get("lang") or "en", customer, staff=False)
                    if sub.get("demo"):
                        msg["url"] = "/demo/customer"
                    out.append(("push", sub["id"], msg["body"], (sub, msg)))
        if kind in STAFF_KINDS:
            if use_whatsapp:
                for p in profiles.values():
                    if p["role"] == "staff" and p["org_id"] == site["org_id"] and p.get("whatsapp_number"):
                        out.append(("whatsapp", normalize_phone(p["whatsapp_number"]),
                                    staff_message(kind, f, site, customer), None))
            for sub in subs:
                if sub["role"] == "staff" and sub.get("org_id") == site["org_id"]:
                    msg = _push_text(kind, f, site, "en", customer, staff=True)
                    if sub.get("demo"):
                        msg["url"] = "/demo/technician"
                    out.append(("push", sub["id"], msg["body"], (sub, msg)))
        for channel, to, body, pushed in out:
            if (f["id"], to) in told or (site["id"], kind, to) in recent:
                continue
            if quiet and not urgent:
                held += 1                      # try again after 6:30 am (still inside the 12 hours)
                continue
            row = {"site_id": site["id"], "finding_id": f["id"], "channel": channel, "recipient": to,
                   "template": kind, "body": body, "created_at": _iso(now)}
            try:
                if channel == "push":
                    pusher(*pushed)
                    row.update(status="sent", sent_at=_iso(now))
                else:
                    row.update(status="sent", provider_message_id=sender(to, body), sent_at=_iso(now))
                    mine = customer and normalize_phone(customer.get("whatsapp_number")) == to
                    _log(client, to, "out", "template", body, SimpleNamespace(id=site["id"]) if mine else None)
                sent += 1
            except push.Gone:
                client.table("push_subscriptions").delete().eq("id", to).execute()
                continue
            except Exception:
                log.exception("Alert by %s to %s… failed", channel, to[:6])
                row["status"] = "failed"
                failed += 1
            client.table("alerts").insert(row, returning="minimal").execute()
            told.add((f["id"], to))
            recent.add((site["id"], kind, to))
    return {"sent": sent, "failed": failed, "held_for_morning": held}


def purge_conversations(client=None) -> int:
    client = client or get_client()
    cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=KEEP_DAYS)
    return len(client.table("conversations").delete().lt("created_at", _iso(cutoff)).execute().data or [])
