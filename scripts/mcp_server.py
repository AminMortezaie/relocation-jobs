#!/usr/bin/env python3
"""stdio MCP entry point for Claude Desktop — see docs/reference/mcp-application.md."""

from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()

from relocation_jobs.mcp.server import main

if __name__ == "__main__":
    main()
