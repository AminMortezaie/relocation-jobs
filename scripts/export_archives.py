#!/usr/bin/env python3
"""Export read-only company/job snapshots from SQLite to companies/*.json."""

from __future__ import annotations

import sys

from relocation_jobs.catalog_db import export_all_archives, export_country_archive
from relocation_jobs.db import init_db
from relocation_jobs.paths import COUNTRY_FILE_NAMES


def main() -> None:
    init_db()
    if len(sys.argv) > 1:
        country = sys.argv[1].lower()
        if country not in COUNTRY_FILE_NAMES:
            raise SystemExit(f"Unknown country: {country}. Use: {', '.join(COUNTRY_FILE_NAMES)}")
        path = export_country_archive(country)
        if path is None:
            raise SystemExit(f"No catalog data for {country}")
        print(path)
        return

    paths = export_all_archives()
    if not paths:
        print("No catalog data to export")
        return
    for p in paths:
        print(p)


if __name__ == "__main__":
    main()
