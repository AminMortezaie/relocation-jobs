#!/usr/bin/env python3
"""Backward-compatible wrapper — use scripts/fix_job_descriptions.py instead."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from fix_job_descriptions import main

if __name__ == "__main__":
    argv = ["--ats", "smartrecruiters", *sys.argv[1:]]
    raise SystemExit(main(argv))
