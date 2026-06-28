# Architecture

**Last updated:** 2026-06-26

v2 layout and data flow. Setup: [contributing.md](../contributing.md). Board details: [board.md](board.md).

---

## Data flow

```
relocate.me (country page)
    ↓
build_companies.py       ← careers URL discovery → Postgres catalog
    ↓
v2 fetch (panel) or scrape_jobs.py (CLI)  ← ATS scrape → Postgres catalog
    ↓
web/server.py            ← Flask API (catalog + per-user tracking merge)
    ↓
static/js/ + frontend/   ← UI; React pagination in static/dist/
```

---

## v2 package layout

```
relocation_jobs/
├── catalog/      repo — companies, jobs, sync_company_board_to_catalog
├── positions/    repo + service — apply, reject, not-for-me
├── panel/        flatten_companies, flatten_companies_page, stats, filters
├── fetch/        country_runner, runner — in-process asyncio fetch
├── scrape/       boards/, merge, enrich, ats_resolve
├── companies/    company CRUD
├── users/        history, applied
├── admin/        dashboard aggregates
├── web/          server, routes, deps
├── shared/       predicates, coerce, schema
└── db/           v2-only migrations
```

**Layer rule:** SQL only in `*/repo.py`. See [rules.md](rules.md).

---

## Data stores

| Store | Contents |
|-------|----------|
| **Postgres** (`DATABASE_URL`) | Catalog, users, tracking, fetch runs |
| `companies/*.json` | Git archive only — not read at runtime |
| `data/custom_cities.json` | User-added cities (`PANEL_DATA_DIR`) |

---

## Panel read path

**Main board:** `GET /api/board` → `panel/board.load_catalog_board_page()` → `flatten_companies_page()`.

1. Load catalog for **selected country only**
2. Load per-user tracking scoped to that country
3. Merge tracking onto catalog jobs at read time
4. Route each job to one bucket: `jobs`, `rejected_jobs`, or `not_for_me_jobs`
5. Reinject orphans per [business-rules.md](business-rules.md)
6. Apply panel filters + search; paginate with **visible offset**

Response: `{ companies, meta, user_stats }`. Default `page_size` = 25.

**Stats:** Full dashboard at `GET /api/admin/panel-stats` (admin only). Board returns lightweight `user_stats`.

**Sort / newest:** [board.md](board.md) — client-side per page; server returns DB order.

---

## Panel UI (client)

| Piece | Location |
|-------|----------|
| Board load / pagination | `static/js/board.js`, `board-view.js`, `api.js` |
| React pagination | `frontend/src/BoardPagination.jsx` → `#board-pagination-root` |
| Company cards | `frontend/src/CompanyCard.jsx`, `static/js/render.js` |
| Job mutations | `static/js/job-board.js` (prefer local updates) |

Layout: **pagination → search → sort/filters → company cards**.

---

## Fetch (v2)

- In-process asyncio in `fetch/country_runner.py`
- Concurrency: 16 max (`core/ats_constants.MAX_CONCURRENCY`)
- Poll `GET /api/fetch/status`
- Country fetch: admin; per-company: `POST /api/companies/fetch`

---

## v1 (reference only)

Legacy panel on port 5050. Subprocess scrape CLI. Do not extend — use v2 paths above.
