#!/usr/bin/env python3
"""Scrape matching jobs from company careers pages."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from relocation_jobs.scrape_jobs import main

if __name__ == "__main__":
    main()
