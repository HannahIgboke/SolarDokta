"""Run the 5-minute tick by hand (Phase 3 will run it automatically on a schedule).

Usage (from backend/):
    python -m scripts.run_tick            # one tick: bring every site up to now
    python -m scripts.run_tick --loop     # keep ticking every 5 minutes until you press Ctrl+C
"""

import argparse
import logging
import time

import pandas as pd

from app.simulator.site import load_site
from app.simulator.tick import run_tick
from scripts.generate_history import DEFAULT_SITES

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)


def once(codes: list[str]) -> None:
    sites = [load_site(c) for c in codes]
    for r in run_tick(sites):
        flag = f"  inverter faults: {', '.join(r.faults)}" if r.faults else ""
        print(f"{r.site:10s} +{r.rows:4d} rows  now at {r.last_ts:%Y-%m-%d %H:%M}{flag}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sites", nargs="+", default=DEFAULT_SITES)
    parser.add_argument("--loop", action="store_true")
    args = parser.parse_args()

    once(args.sites)
    while args.loop:
        now = pd.Timestamp.now(tz="UTC")
        wait = ((now.floor("5min") + pd.Timedelta(minutes=5)) - now).total_seconds() + 5
        time.sleep(wait)
        once(args.sites)


if __name__ == "__main__":
    main()
