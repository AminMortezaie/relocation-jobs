#!/usr/bin/env python3
"""Streamable HTTP MCP entry point with OAuth — see docs/reference/mcp-application.md."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from relocation_jobs.core.db import init_db
from relocation_jobs.mcp.http_app import run_http

if __name__ == "__main__":
    init_db()
    run_http()
