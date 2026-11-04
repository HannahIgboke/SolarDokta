"""Quick check that the backend can reach Supabase.

Usage (from backend/):
    python -m scripts.check_connection
"""

from app.config import get_settings
from app.db import get_client


def main() -> None:
    print(f"Connecting to {get_settings().supabase_url} ...")
    rows = get_client().table("sites").select("code,city").order("code").execute().data
    print(f"Connected. {len(rows)} sites found:")
    for r in rows:
        print(f"  {r['code']:<10} {r['city']}")


if __name__ == "__main__":
    main()
