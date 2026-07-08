#!/usr/bin/env python3
"""Long-running fetch scheduler worker (EC2 or local)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run scheduled country job fetches.")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single fetch cycle and exit.",
    )
    args = parser.parse_args()

    from relocation_jobs.fetch.scheduler import (
        bootstrap_scheduler,
        run_fetch_cycle,
        run_scheduler_loop,
        schedule_enabled,
    )

    if args.once:
        bootstrap_scheduler()
        if not schedule_enabled():
            print("FETCH_SCHEDULE_ENABLED is off", file=sys.stderr)
            return 1
        result = run_fetch_cycle()
        print(result)
        return 0

    run_scheduler_loop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
