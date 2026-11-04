"""See or change how bad NEPA supply is in each city (the simulator follows these conditions).

Usage (from backend/):
    python -m scripts.set_grid --list
    python -m scripts.set_grid --city Lagos --from 2026-11-04 --hours 4 --outage 8 --note "Worse this week"
    python -m scripts.set_grid --city Lagos --from 2026-11-10 --hours 12 --until 2026-11-30 --note "Better"
    python -m scripts.set_grid --delete 7

--hours: hours of light per day on average. --outage: typical length of one outage (hours).
Newer conditions win where they overlap. After a change, rebuild the affected days with
    python -m scripts.resimulate --since <the --from date>
"""

import argparse
from datetime import date

from app.db import get_client


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--list", action="store_true")
    p.add_argument("--city", choices=["Lagos", "Port Harcourt", "Abuja", "Kano"])
    p.add_argument("--from", dest="starts", type=date.fromisoformat)
    p.add_argument("--until", type=date.fromisoformat, help="last day (leave out = still going on)")
    p.add_argument("--hours", type=float, help="hours of light per day")
    p.add_argument("--outage", type=float, default=6.0, help="typical outage length in hours")
    p.add_argument("--note", default="")
    p.add_argument("--delete", type=int, metavar="ID")
    args = p.parse_args()
    client = get_client()

    if args.delete:
        client.table("grid_conditions").delete().eq("id", args.delete).execute()
        print(f"Deleted condition {args.delete}")
    elif not args.list:
        if not (args.city and args.starts and args.hours is not None):
            p.error("give --city, --from and --hours (or --list)")
        if not 0 <= args.hours <= 24:
            p.error("--hours must be between 0 and 24")
        client.table("grid_conditions").insert({
            "city": args.city, "starts": args.starts.isoformat(),
            "ends": args.until.isoformat() if args.until else None,
            "hours_per_day": args.hours, "mean_outage_h": args.outage, "note": args.note,
        }).execute()
        print(f"Saved: {args.city} from {args.starts}: {args.hours} h of light a day")

    rows = client.table("grid_conditions").select("*").order("city").order("starts").execute().data
    for r in rows:
        print(f"{r['id']:>3}  {r['city']:<14} {r['starts']} to {r['ends'] or 'now':<10}  "
              f"{float(r['hours_per_day']):>4.1f} h/day, outages ~{float(r['mean_outage_h']):.0f} h  {r.get('note') or ''}")


if __name__ == "__main__":
    main()
