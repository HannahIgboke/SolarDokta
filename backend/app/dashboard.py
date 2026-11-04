"""API for the Next.js dashboard: who am I, my sites, the agent's tools, and the chat.

Security:
- The dashboard logs people in with Supabase Auth and sends their access token
  (Authorization: Bearer <token>). We ask Supabase who the token belongs to, then load their
  profile (role: staff or customer).
- Staff can open every site of their organisation; customers only the site(s) linked to them.
- The service role key stays here: the browser only ever gets results for sites it may open.

Public demo: the tokens "demo-customer" and "demo-staff" (no login) open the demo site
(DEMO_SITE in .env) read-only: as its customer, or as its installer's technician. Anything that
changes data is refused, and demo visitors get a few chat questions per hour.

Endpoints (all need the token):
    GET  /api/me                          profile + the sites this person can open
    GET  /api/sites/{code}/tools/{name}   run one agent tool (battery_now, money_view, ...)
                                          can_i_run takes ?appliance=pressing iron&watts=1000&minutes=30
    GET  /api/sites/{code}/views/{name}   dashboard data: live (the digital twin), today, money_history
    POST /api/sites/{code}/chat           ask SolarDokta, same brain as WhatsApp
"""

import logging
import time
from collections import defaultdict, deque
from typing import Annotated, Literal

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from pydantic import BaseModel, Field

from app.agent.tools import TOOLS, ToolContext, run_tool
from app.config import get_settings
from app.dashboard_views import VIEWS
from app.db import get_client
from app.simulator.site import SiteConfig, _from_row

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

_llm = None                       # one Gemini connection for the whole server (remembers backups)


def verify_token(token: str) -> str:
    """User id for a Supabase access token (raises if the token is invalid or expired)."""
    resp = get_client().auth.get_user(token)
    if resp is None or resp.user is None:
        raise ValueError("no user for this token")
    return resp.user.id


DEMO_TOKENS = {"demo-customer": "customer", "demo-staff": "staff"}


def demo_profile(role: str) -> dict:
    s = get_settings()
    if not s.demo_enabled:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "The demo is switched off")
    rows = get_client().table("sites").select("id,org_id,customer_id").eq("code", s.demo_site).execute().data
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Demo site {s.demo_site!r} not found")
    return {"id": f"demo-{role}", "role": role, "org_id": rows[0]["org_id"], "demo": True,
            "full_name": s.demo_customer_name if role == "customer" else "Demo technician",
            "preferred_language": "en", "demo_site": s.demo_site}


def no_demo(profile: dict) -> None:
    """Refuse anything that changes data when the visitor is on the public demo."""
    if profile.get("demo"):
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "This is a demo, so nothing can be changed. Sign in to do this for real.")


def current_profile(authorization: Annotated[str | None, Header()] = None) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Log in first")
    token = authorization.split(" ", 1)[1].strip()
    if token in DEMO_TOKENS:
        return demo_profile(DEMO_TOKENS[token])
    try:
        user_id = verify_token(token)
    except Exception as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired: log in again") from exc
    rows = get_client().table("profiles").select("*").eq("id", user_id).execute().data
    if not rows:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account has no SolarDokta profile")
    return rows[0]


Profile = Annotated[dict, Depends(current_profile)]


def visible_sites(profile: dict) -> list[dict]:
    q = get_client().table("sites").select("*")
    if profile.get("demo") and profile["role"] == "customer":
        q = q.eq("code", profile["demo_site"])
    elif profile["role"] == "staff":
        q = q.eq("org_id", profile["org_id"])
    else:
        q = q.eq("customer_id", profile["id"])
    return q.order("code").execute().data


def site_for(code: str, profile: dict) -> SiteConfig:
    for row in visible_sites(profile):
        if row["code"] == code:
            return _from_row(row)
    raise HTTPException(status.HTTP_404_NOT_FOUND, f"No site {code!r} for this account")


@router.get("/me")
def me(profile: Profile) -> dict:
    sites = [{"code": r["code"], "name": r["name"], "city": r["city"]} for r in visible_sites(profile)]
    return {"id": profile["id"], "role": profile["role"], "full_name": profile.get("full_name"),
            "preferred_language": profile.get("preferred_language", "en"), "sites": sites,
            "demo": bool(profile.get("demo"))}


@router.get("/sites/{code}/tools/{name}")
def tool(code: str, name: str, profile: Profile, days: int | None = None,
         appliance: str | None = None, watts: float | None = None,
         minutes: float | None = None) -> dict:
    if name not in TOOLS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown tool {name!r}")
    ctx = ToolContext(site_for(code, profile), role=profile["role"])
    if name == "can_i_run":
        args = {"appliance": (appliance or "")[:60], "watts": watts, "minutes": minutes}
    else:
        args = {"days": days} if days and name in ("money_view", "open_problems", "light_tracker") else {}
    return run_tool(ctx, name, args)


@router.get("/sites/{code}/views/{name}")
def view(code: str, name: str, profile: Profile, months: int | None = None,
         start: str | None = None, end: str | None = None, lang: str = "en") -> dict:
    if name not in VIEWS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown view {name!r}")
    ctx = ToolContext(site_for(code, profile), role=profile["role"])
    try:
        if name == "money_history":
            return VIEWS[name](ctx, months=months)
        if name == "usage":
            return VIEWS[name](ctx, start=start, end=end)
        if name == "live":
            return VIEWS[name](ctx, lang=lang)
        return VIEWS[name](ctx)
    except Exception:
        log.exception("View %s failed for %s", name, code)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Couldn't load {name}") from None


class ChatTurn(BaseModel):
    role: str = Field(pattern="^(user|model)$")
    text: str = Field(max_length=2000)


Lang = Literal["en", "pcm", "ig"]


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    history: list[ChatTurn] = Field(default_factory=list, max_length=20)
    language: Lang | None = None          # the app's language switch; None = follow the message


_demo_questions: dict[str, deque] = defaultdict(deque)     # visitor address -> question times


def demo_chat_allowed(request: Request) -> None:
    """A few questions per visitor per hour on the demo, so strangers can't use up the AI quota."""
    who = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "?")).split(",")[0].strip()
    times, now, limit = _demo_questions[who], time.time(), get_settings().demo_chat_per_hour
    while times and now - times[0] > 3600:
        times.popleft()
    if len(times) >= limit:
        wait = int((3600 - (now - times[0])) / 60) + 1
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            f"The demo allows {limit} questions an hour. Try again in {wait} minutes.")
    times.append(now)


def _agent_reply(code: str, profile: dict, request: Request, message: str, history: list[dict],
                 language: str | None):
    from app.agent.agent import Agent  # the AI is only loaded when someone chats
    from app.agent.llm import LLMError
    from app.agent.providers import make_llm

    global _llm
    ctx = ToolContext(site_for(code, profile), role=profile["role"])
    if profile.get("demo"):
        demo_chat_allowed(request)
    try:
        _llm = _llm or make_llm()
    except LLMError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    agent = Agent(_llm, ctx, language=profile.get("preferred_language", "en"))
    r = agent.reply(message, history, language=language)
    log.info("Chat on %s answered by %s in %ss (%s AI calls%s)", code, r.timings.get("model") or "no AI",
             r.timings.get("seconds"), r.timings.get("gemini_calls"), "" if r.ok else ", backup answer")
    return {"reply": r.text, "ok": r.ok, "timings": r.timings,
            "tools": [c["name"] for c in r.tool_calls]}


@router.post("/sites/{code}/chat")
def chat(code: str, body: ChatRequest, profile: Profile, request: Request) -> dict:
    return _agent_reply(code, profile, request, body.message,
                        [t.model_dump() for t in body.history], body.language)


@router.post("/sites/{code}/chat/voice")
def chat_voice(code: str, profile: Profile, request: Request, audio: Annotated[UploadFile, File()],
               language: Annotated[str | None, Form()] = None,
               history: Annotated[str, Form()] = "[]") -> dict:
    """Ask by voice: Gemini writes down what was said, then the agent answers it as usual."""
    import json

    from app.agent import reader
    from app.agent.llm import LLMError

    site_for(code, profile)
    mime = (audio.content_type or "").split(";")[0].strip().lower()
    if not mime.startswith("audio/"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Send an audio recording")
    data = audio.file.read(5 * 1024 * 1024 + 1)
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Keep voice questions under about 2 minutes")
    try:
        heard = reader.read_file("question", data, mime)
    except LLMError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Couldn't hear that clearly. Try again or type it.") from exc
    text = (heard.get("transcript") or "").strip()[:1000]
    if not text:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Couldn't hear a question. Try again closer to the phone.")
    try:
        past = [t for t in json.loads(history) if isinstance(t, dict) and t.get("text")][-20:]
    except ValueError:
        past = []
    lang = language if language in ("en", "pcm", "ig") else None
    return {"transcript": text, **_agent_reply(code, profile, request, text, past, lang)}
