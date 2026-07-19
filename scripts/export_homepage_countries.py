#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "homepage" / "data" / "countries.json"


def main() -> int:
    sys.path.insert(0, str(ROOT))
    from relocation_jobs.catalog.custom_countries import (
        DEFAULT_COUNTRY_LABELS,
        load_country_labels_store,
    )

    labels = dict(DEFAULT_COUNTRY_LABELS)
    if OUT.is_file():
        try:
            existing = json.loads(OUT.read_text(encoding="utf-8"))
            if isinstance(existing, dict):
                for key, label in existing.items():
                    if isinstance(key, str) and isinstance(label, str) and key.strip() and label.strip():
                        labels[key.strip().lower()] = label.strip()
        except (OSError, json.JSONDecodeError) as exc:
            print(f"export_homepage_countries: fallback JSON unreadable ({exc})", file=sys.stderr)
    try:
        labels.update(load_country_labels_store())
    except Exception as exc:
        print(f"export_homepage_countries: store unavailable ({exc}); using defaults", file=sys.stderr)

    ordered = {
        key: labels[key]
        for key in sorted(labels)
        if key and labels[key].strip()
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(ordered, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(ordered)} countries to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
