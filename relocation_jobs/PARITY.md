# Parity — complete

Legacy v1 stack removed. Single application under `relocation_jobs/`:

| Domain | Path |
|--------|------|
| Core (auth, db, ATS) | `core/` |
| User tracking, fetch runs | `db/` |
| Schemas | `schemas/` |
| Catalog | `catalog/` |
| Companies | `companies/` |
| Panel flatten/stats | `panel/` |
| Job state | `positions/` |
| Flask API | `web/` |
| ATS scrape | `scrape/` |
| In-process fetch | `fetch/` |

**Tests:**

```bash
pytest tests -o addopts=
pytest tests/test_route_manifest.py -o addopts=
```

**Panel locally:**

```bash
PANEL_SCRAPE_ENABLED=1 python3 scripts/panel_server.py
```

**Batch catalog:** `python3 scripts/build_companies.py <country>`
