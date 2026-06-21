#!/usr/bin/env python3
"""Run the job panel web server."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from relocation_jobs.panel_server import main

if __name__ == "__main__":
    main()
