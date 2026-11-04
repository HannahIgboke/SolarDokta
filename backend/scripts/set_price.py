"""Record a new fuel or electricity price (older prices are kept for history).

Usage (from backend/):
    python -m scripts.set_price petrol 1050 --source "NNPC Lagos retail, 31 Oct 2026"
    python -m scripts.set_price grid_band_a 209.50 --source "NERC PHED order, May 2026"
    python -m scripts.set_price --list
"""

import argparse
from datetime import date

from app.db import get_client, upsert_rows

UNITS = {
    "petrol": "ngn_per_litre",
    "diesel": "ngn_per_litre",
    **{f"grid_band_{b}": "ngn_per_kwh" for b in "abcde"},
}


def latest_prices(client) -> list[dict]:
    rows = (client.table("prices").select("*")
            .order("item").order("effective_from", desc=True).execute().data)
    latest: dict[str, dict] = {}
    for r in rows:
        latest.setdefault(r["item"], r)   # first row per item is the newest
    return list(latest.values())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("item", nargs="?", choices=sorted(UNITS))
    parser.add_argument("price_ngn", nargs="?", type=float)
    parser.add_argument("--source", default="")
    parser.add_argument("--date", type=date.fromisoformat, default=date.today())
    parser.add_argument("--list", action="store_true", help="show the latest price of each item")
    args = parser.parse_args()

    client = get_client()

    if args.list or args.item is None:
        for r in latest_prices(client):
            print(f"{r['item']:<12} N{float(r['price_ngn']):>10,.2f}  {r['unit']:<14} "
                  f"from {r['effective_from']}  ({r['source']})")
        return

    if args.price_ngn is None or args.price_ngn <= 0:
        parser.error("give a positive price")
    upsert_rows("prices", [{
        "item": args.item,
        "unit": UNITS[args.item],
        "price_ngn": args.price_ngn,
        "effective_from": args.date.isoformat(),
        "source": args.source,
    }], on_conflict="item,effective_from", client=client)
    print(f"Saved {args.item} = N{args.price_ngn:,.2f} ({UNITS[args.item]}) from {args.date}")


if __name__ == "__main__":
    main()
