#!/usr/bin/env python3
"""stdio MCP entry point for Claude Desktop — see docs/reference/mcp-application.md."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from relocation_jobs.mcp.server import main

if __name__ == "__main__":
    main()
