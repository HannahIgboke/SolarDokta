"""Add or end a fault on a live site (great for demos: "watch, I'll break string 2 now").

The next tick picks it up automatically.

Usage (from backend/):
    python -m scripts.inject_fault --list --site lagos-001
    python -m scripts.inject_fault --site lagos-001 --kind string_failure --target pv2
    python -m scripts.inject_fault --site lagos-001 --kind soiling --max-loss 0.3 --ramp-days 1 --hours 48
    python -m scripts.inject_fault --site lagos-001 --kind overload --extra-w 7000 --hours 0.5
    python -m scripts.inject_fault --site lagos-001 --kind shading --target pv1 --shade-hours 2
    python -m scripts.inject_fault --site lagos-001 --end 42        # fault id 42 ends now
"""

import argparse

import pandas as pd

from app.db import get_client
from app.simulator.faults import KINDS, Fault, _iso
from app.simulator.site import load_site

DEFAULTS = {
    "soiling": {"max_loss": 0.25, "ramp_days": 14},
    "shading": {"from_hour": 15.0, "hours": 2.0, "loss": 0.6},
    "string_failure": {},
    "underrated_panel": {"factor": 0.78},
    "battery_fade": {"soh_per_day": 0.002},
    "hot_battery_room": {"extra_c": 10.0},
    "overload": {"extra_w": 7000},
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", required=True)
    parser.add_argument("--kind", choices=KINDS)
    parser.add_argument("--target", default="all", choices=["all", "pv1", "pv2"])
    parser.add_argument("--hours", type=float, help="how long it lasts (default: until you end it)")
    parser.add_argument("--list", action="store_true", help="show this site's open faults")
    parser.add_argument("--end", type=int, metavar="ID", help="end fault ID now")
    for name in sorted({k for d in DEFAULTS.values() for k in d}):
        flag = "shade-hours" if name == "hours" else name.replace("_", "-")   # --hours is taken
        parser.add_argument(f"--{flag}", type=float, dest=f"p_{name}")
    args = parser.parse_args()

    client = get_client()
    site = load_site(args.site)
    now = pd.Timestamp.now(tz=site.timezone).floor("5min")

    if args.end:
        client.table("injected_faults").update({"end_ts": _iso(now)}).eq("id", args.end).execute()
        print(f"Fault {args.end} ends at {now:%H:%M}")
    elif args.kind:
        params = {k: (getattr(args, f"p_{k}") if getattr(args, f"p_{k}") is not None else v)
                  for k, v in DEFAULTS[args.kind].items()}
        end = now + pd.Timedelta(hours=args.hours) if args.hours else None
        f = Fault(args.kind, now + pd.Timedelta(minutes=5), end, args.target, params)
        row = client.table("injected_faults").insert(f.to_row(site.id)).execute().data[0]
        until = f"until {end:%Y-%m-%d %H:%M}" if end is not None else "until you end it"
        print(f"Added fault {row['id']}: {args.kind} on {args.target} {params} from "
              f"{f.start:%H:%M}, {until}")

    if args.list or not (args.kind or args.end):
        rows = (client.table("injected_faults").select("*").eq("site_id", site.id)
                .or_(f"end_ts.is.null,end_ts.gt.{_iso(now)}").order("start_ts").execute().data)
        print(f"\nOpen faults on {site.code}:")
        for r in rows:
            print(f"  {r['id']:>5}  {r['kind']:17s} {r['params']}  from {r['start_ts'][:16]}"
                  f"  to {(r['end_ts'] or 'open')[:16]}")


if __name__ == "__main__":
    main()
