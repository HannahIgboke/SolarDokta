"""Settings loaded from environment variables or the repo-root .env file."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    supabase_url: str = ""
    supabase_service_role_key: str = ""
    database_url: str = ""   # optional: only needed if we ever connect to Postgres directly
    cron_secret: str = ""    # shared password that Supabase Cron sends to /tick and /jobs/*
    gemini_api_key: str = ""
    gemini_model: str = "gemini-flash-lite-latest"        # fastest Flash model: quick replies
    gemini_backup_models: str = "gemini-3.5-flash-lite"   # used if the main one is busy
    gemini_timeout_s: float = 10.0                         # give up on a slow model after this
    # Other AI companies, tried in this order when Gemini fails (no key in .env = left out)
    llm_providers: str = "gemini,groq,github,openrouter,mistral,cerebras"
    llm_timeout_s: float = 12.0
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    cerebras_api_key: str = ""
    cerebras_model: str = "gpt-oss-120b"
    openrouter_api_key: str = ""
    openrouter_model: str = "meta-llama/llama-3.3-70b-instruct:free"
    github_models_token: str = ""
    github_model: str = "openai/gpt-4.1-mini"
    mistral_api_key: str = ""
    mistral_model: str = "mistral-small-latest"
    # Public demo (no login): visitors see this site as its customer, or its installer's view
    demo_enabled: bool = True
    demo_site: str = "lagos-001"
    demo_customer_name: str = "Ada"
    demo_chat_per_hour: int = 5          # questions per visitor per hour (protects the AI quota)
    frontend_origins: str = "http://localhost:3000"        # dashboard address(es), comma-separated
    app_url: str = ""                      # the live web app, e.g. https://solardokta.vercel.app (for links)
    public_api_url: str = ""               # this API's public address, e.g. https://solardokta-api.onrender.com
    # WhatsApp through Twilio
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_whatsapp_from: str = "whatsapp:+14155238886"    # Twilio's sandbox number until we get our own
    whatsapp_demo: bool = True             # numbers not linked to a site chat with the demo home
    whatsapp_per_hour: int = 20            # questions per linked number per hour
    alerts_enabled: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
