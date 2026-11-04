"""Run one of the scheduled jobs by hand (the server runs them on a schedule later).

Usage (from backend/):
    python -m scripts.run_job forecast
    python -m scripts.run_job anomaly                     # scores yesterday
    python -m scripts.run_job anomaly --day 2026-11-01    # a particular day
    python -m scripts.run_job anomaly --local             # skip Modal, use the Isolation Forest
"""

import argparse
import json
import logging

import pandas as pd

from app.jobs import JOBS, active_sites

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("name", choices=sorted(JOBS))
    parser.add_argument("--day", help="anomaly only: local date to score (default: yesterday)")
    parser.add_argument("--local", action="store_true", help="anomaly only: don't call Modal")
    args = parser.parse_args()

    if args.name == "anomaly" and (args.day or args.local):
        from app.ml import daily

        sites = active_sites()
        day = pd.Timestamp(args.day, tz=sites[0].timezone) if args.day else None
        kwargs = {"remote": daily.score_locally} if args.local else {}
        result = daily.run(sites, day=day, **kwargs)
    else:
        result = JOBS[args.name]()
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
