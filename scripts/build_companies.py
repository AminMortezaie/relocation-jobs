#!/usr/bin/env python3
"""Discover careers URLs and sort company lists."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from relocation_jobs.build_companies import main

if __name__ == "__main__":
    main()
