"""Talk to Supabase over HTTPS (its REST API) instead of a direct database connection.

Uses SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY from .env. The service role key bypasses
Row Level Security, so it must only ever be used by the backend, never the frontend.
"""

import threading
from collections.abc import Iterable

from supabase import Client, create_client

from app.config import get_settings

BATCH_SIZE = 1000   # rows per request; keeps each HTTPS call small and reliable


_local = threading.local()


def get_client() -> Client:
    """One Supabase client per thread. The web server answers several requests at once on
    different threads, and one shared HTTP/2 connection can get its streams mixed up
    ("KeyError" in httpcore's http2 code), so each thread gets its own connection."""
    client = getattr(_local, "client", None)
    if client is None:
        s = get_settings()
        if not s.supabase_url or not s.supabase_service_role_key:
            raise RuntimeError("Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in the .env file")
        client = _local.client = create_client(s.supabase_url, s.supabase_service_role_key)
    return client


def upsert_rows(table: str, rows: Iterable[dict], on_conflict: str, client: Client | None = None) -> int:
    """Insert rows, or update them if a row with the same key already exists. Returns rows sent.

    on_conflict: comma-separated key columns, e.g. "latitude,longitude,ts".
    Safe to re-run: existing rows are updated, not duplicated.
    """
    client = client or get_client()
    batch: list[dict] = []
    total = 0
    for row in rows:
        batch.append(row)
        if len(batch) == BATCH_SIZE:
            _send(client, table, batch, on_conflict)
            total += len(batch)
            batch = []
    if batch:
        _send(client, table, batch, on_conflict)
        total += len(batch)
    return total


def _send(client: Client, table: str, batch: list[dict], on_conflict: str) -> None:
    client.table(table).upsert(batch, on_conflict=on_conflict, returning="minimal").execute()
