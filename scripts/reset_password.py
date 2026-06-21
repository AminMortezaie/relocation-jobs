#!/usr/bin/env python3
"""Reset a panel user's password."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from relocation_jobs.reset_password import main

if __name__ == "__main__":
    raise SystemExit(main())
