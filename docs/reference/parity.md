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
PANEL_SCRAPE_ENABLED=1 python3 scripts/panel_server.py   # → :5051
cd frontend && npm run build   # React pagination → static/dist/board.js
```

Board loads via paginated `GET /api/board` (25 companies/page, filter-aware). Full user stats on admin: `GET /api/admin/panel-stats`.

**Batch catalog:** `python3 scripts/build_companies.py <country>`
