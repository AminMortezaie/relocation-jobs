#!/usr/bin/env python3
"""Run the job panel."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if __name__ == "__main__":
    import os

    from relocation_jobs.web.server import app

    port = int(os.environ.get("PORT") or os.environ.get("PANEL_PORT", "5051"))
    host = os.environ.get("PANEL_HOST")
    if not host:
        host = "0.0.0.0" if os.environ.get("PORT") else "127.0.0.1"
    app.run(host=host, port=port)
