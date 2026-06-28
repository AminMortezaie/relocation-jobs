# v2 bugfix & parity handoff

**Date:** 2026-06-24 (updated 2026-06-25)  
**Entry point:** [`docs/README.md`](../README.md)  
**Branch:** check `git status` — uncommitted work is common; **do not commit unless user asks**

User is on **v2** (`relocation_jobs/`) as the active spine. v1 remains on port **5050** for comparison; v2 on **5051**. Same Postgres (AWS EC2), same static UI, same `/api/*` paths.

**Read before editing v2:**

- [`docs/reference/rules.md`](../reference/rules.md)
- [`v2-coding-verdict.md`](v2-coding-verdict.md)
- [`docs/reference/parity.md`](../reference/parity.md)
- [`.cursor/rules/v2-coding.mdc`](../.cursor/rules/v2-coding.mdc)

**Do not commit** unless user asks.

---

## How to run v2

```bash
# From repo root; requires .env (DATABASE_URL, PANEL_SECRET_KEY, admin creds)
PANEL_SCRAPE_ENABLED=1 python3 -c "from relocation_jobs.web.server import app; app.run(host='127.0.0.1', port=5051, debug=True)"
```

| | v1 | v2 |
|---|----|----|
| Port | 5050 | 5051 |
| Entry | `python3 -m relocation_jobs.panel_server` | `relocation_jobs.web.server` |
| URL | http://127.0.0.1:5050 | http://127.0.0.1:5051 |

- **Separate Flask sessions** — log in again on `:5051`
- After JS changes: hard refresh (`Cmd+Shift+R`); cache buster is `main.js?v=95` in `index.html`; React bundle is `static/dist/board.js` (rebuild with `cd frontend && npm run build`)

**Tests:**

```bash
python3 -m pytest tests -o addopts=                          # full v2 suite (~100 tests)
python3 -m pytest tests/test_route_manifest.py -o addopts=   # fast route parity
```

Use `-o addopts=` — bare `pytest` may miss deps or hit `-n auto` issues locally.

---

## User-reported bugs (5)

| # | Bug | Status |
|---|-----|--------|
| 1 | Single-company fetch not working | **Fixed** — verify `PANEL_SCRAPE_ENABLED=1` |
| 2 | Country fetch not working | **Fixed** on AWS Postgres at 16 workers |
| 3 | Admin panel empty/broken | Likely session on `:5051` — log in as admin separately |
| 4 | **Position state changes wrong job** | **Fixed** (server + client) |
| 5 | Filters don't match labels | **Partially fixed** — LTA filter wired; others not fully audited |
| 6 | **Not-for-me slow** | **Fixed** — client uses local board update, not full reload; server `get_job_by_url` indexed |
| 7 | **Panel slow / full catalog load** | **Fixed** — paginated `GET /api/board`, country-scoped catalog, stats moved to admin |

---

## What was committed (HEAD: `5d57d4a`)

**Message:** Add single-company fetch, improve concurrency handling, and expand HTTP route tests…

### Fetch / concurrency

- `fetch/runner.py` — single-company fetch via background thread; busy guard; concurrency handling
- `web/routes/companies.py` — `POST /api/companies/fetch` wired to async fetch
- `web/server.py` — `fetch_repo.reap_orphan_running_fetch_runs()` on bootstrap (fixes stale `fetch_runs` → 409 busy)
- `tests/web/test_fetch_api.py` — expanded fetch API tests

### Parity infrastructure

- `relocation_jobs/PARITY.md` — living v1 vs v2 checklist
- `tests/helpers/route_manifest.py` + `tests/test_route_manifest.py` — route surface parity test

### Position state (first pass)

- `catalog/repo.py` — `get_job_by_url` scoped by `company_name` + `country_key`
- `positions/service.py` — `_require_catalog_job`, `_with_catalog_url`, returns `idempotency_key`
- `static/js/events.js` — cards pass `idempotencyKey` from `data-idempotency-key`
- `static/js/api.js` — early idempotency wiring

### Filter fix (committed)

- `panel/service.py` — `flatten_companies()` was passing `looking_to_apply_only=` instead of `position_looking_to_apply_only=` → filter silently ignored

---

## Uncommitted changes (review / commit when user approves)

```
 M relocation_jobs/static/index.html
 M relocation_jobs/static/js/api.js
 M relocation_jobs/static/js/job-board.js
 M relocation_jobs/static/js/state.js
 M relocation_jobs/catalog/lookup.py
 M relocation_jobs/catalog/repo.py
 M relocation_jobs/panel/flatten.py
 M relocation_jobs/panel/tracking.py
 M relocation_jobs/positions/repo.py
 M relocation_jobs/positions/service.py
 M tests/catalog/test_repo.py
 M tests/positions/test_workflows.py
?? relocation_jobs/positions/tracking_resolve.py
```

### Bug #4 — position state isolation (main fix)

**Root cause:** Job identity resolved too loosely in three places:

1. Catalog lookup by idempotency hash only (not exact URL first)
2. Tracking writes used click URL, not catalog canonical URL
3. `resolve_track` picked first idempotency alias arbitrarily
4. Client used optimistic local patches + loose URL matching → wrong in-memory job updated

#### Server

| File | Change |
|------|--------|
| **`positions/tracking_resolve.py`** *(NEW)* | Port of v1 URL resolution: `resolve_tracking_url()`, `tracking_urls_for_job()` |
| **`positions/repo.py`** | All mutations use `resolve_tracking_url` + clear all alias rows on unapply via `tracking_urls_for_job`; `_base_result` includes `idempotency_key` |
| **`positions/service.py`** | `_catalog_url()` helper; all repo writes use **catalog URL** not request URL; `_with_catalog_url()` on responses |
| **`catalog/repo.py`** | `get_job_by_url`: exact normalized URL first, then idempotency column, then idempotency from stored URL |
| **`catalog/lookup.py`** | `find_job_in_data`: idempotency fallback only when exactly one match in company |
| **`panel/tracking.py`** | `resolve_track`: among idempotency siblings, prefer exact normalized URL match before first alias |
| **`panel/flatten.py`** | Orphan skip: also skip when idempotency key already listed on board |

#### Client (shared by v1 and v2)

| File | Change |
|------|--------|
| **`static/js/state.js`** | `findJobInCompany()` — exact URL → loose URL → idempotency with disambiguation |
| **`static/js/job-board.js`** | `jobMatches()` delegates to `findJobInCompany` |
| **`static/js/api.js`** | After mutations: `reloadBoard()` → `loadJobs({ silent: true })` instead of optimistic local patch; sends `idempotency_key` in apply/reject/LTA/seen bodies |
| **`static/index.html`** | Cache bust `main.js?v=78` |

#### Tests

| File | Change |
|------|--------|
| **`tests/positions/test_workflows.py`** | `TestPositionIsolation`, `TestPositionFilters` |
| **`tests/catalog/test_repo.py`** | `test_get_job_by_url_prefers_exact_match_within_company` |

**Last test run:** `93 passed` with `python3 -m pytest tests -o addopts=`

---

## Board performance & pagination (2026-06-25)

Main panel no longer loads the full country catalog in one response.

### Server

| Change | Files |
|--------|-------|
| Paginated board API | `web/routes/board.py` — `GET /api/board?page=&page_size=25`, filter flags, `q` search |
| Visible-offset pagination | `panel/service.flatten_companies_page`, `panel/board.py` |
| Country-scoped catalog load | `panel/service.py`, `catalog/repo.py` (`load_catalog_companies_page`) |
| Scoped tracking queries | `users/repo.py` |
| Deferred location list | `catalog/locations.py` — country-scoped when country ≠ all |
| AWS integer fix | `fetch_problem` count uses `COALESCE(c.fetch_problem, 0) <> 0` (not `IS TRUE`) |
| Admin full stats | `GET /api/admin/panel-stats` in `web/routes/admin.py` |
| Lightweight board stats | `user_stats` in board response; `/api/board/stats` no longer re-flattens catalog |

### Client

| Change | Files |
|--------|-------|
| Removed main-panel stats block | `index.html`, `board.js` |
| Page navigation (not infinite scroll) | `board.js`, `board-view.js`, `api.js`, `state.js` |
| React pagination portal | `frontend/src/BoardPagination.jsx`, `main.jsx` → `#board-pagination-root` above search |
| Admin stats section | `admin.html`, `admin.js`, `stats-dashboard.js` |
| Default country | `data.js` — first real country when no `panel_country` in localStorage |

### Tests

- `tests/web/test_board_api.py` — pagination, filters, meta
- `tests/web/test_catalog_api.py::test_admin_panel_stats`

**Caveat:** page 2+ rescans catalog from the start (visible-offset). Acceptable for now; cursor pagination is a future optimization.

---

## Architecture reminders

### v2 layering (strict)

```
routes → deps → service → repo → core/db
```

SQL only in `*/repo.py` + `db/migrate.py`. See `RULES.md`.

### Position mutation flow

```
Card click (events.js)
  → api.js POST /api/jobs/{applied|rejected|...}  { country, company, url, idempotency_key? }
  → web/routes/jobs.py
  → positions/service.py  _require_catalog_job() → get_job_by_url (scoped)
  → positions/repo.py      resolve_tracking_url() → job_tracking row
  → api.js                    local board update (job-board.js) OR reloadBoard() if company missing
```

### Panel read path

```
GET /api/board (paginated) → load_catalog_board_page → flatten_companies_page
  → flatten_company() → partition_stored_jobs()
  → resolve_track() overlays DB tracking onto catalog jobs
  → derive_bucket() → jobs | rejected_jobs | not_for_me_jobs
  → _append_tracked_orphans() for applied/rejected/LTA orphans removed from catalog
  → apply panel filters + search → skip visible_offset → return limit rows
```

Full stats dashboard: `GET /api/admin/panel-stats` (admin) — uses `flatten_companies()` + `compute_stats`.

### Job identity

- `relocation_jobs/core/job_identity.py` — `normalize_job_url()`, `job_idempotency_key()`
- Catalog: unique `(company_id, idempotency_key)` — two visible roles at same company **must** have different keys
- Tracking alias merge is intentional for URL variants (e.g. `utm_source`), not for distinct roles

---

## Fetch — notes (2026-06-25)

Country fetch works on AWS EC2 at **16 workers** (`MAX_CONCURRENCY` hard cap). Do not raise without upgrading instance (OOM at 24 on `t4g.micro`).

Common issues:

1. **`PANEL_SCRAPE_ENABLED=0`** in `.env` — fetch buttons no-op
2. **Orphan `fetch_runs` row** with `status=running` → 409 on new fetch (reap on v2 bootstrap should help; verify)
3. **Country fetch is admin-only** (`POST /api/fetch`)
4. **Admin on `:5051`** needs separate login; check `GET /api/admin/dashboard` in Network tab
5. v2 fetch is **in-process asyncio** — cancel via DB flag + cooperative checks in `country_runner.py`

**Reproduce:**

```bash
PANEL_SCRAPE_ENABLED=1 python3 -c "from relocation_jobs.web.server import app; app.run(port=5051)"
# Watch GET /api/fetch/status during run; check server logs
```

**Key files:** `fetch/runner.py`, `fetch/repo.py`, `web/routes/fetch.py`, `web/routes/companies.py`, `static/js/scrape.js`, `static/js/admin-scrape.js`

---

## Admin panel — investigation notes

- v2 admin routes: `web/routes/admin.py`, `admin/service.py`
- Static admin UI: `static/admin.html`, `static/js/admin.js`
- Likely issues: not logged in as admin on `:5051`, or scrape disabled hiding controls
- Verify: `GET /api/admin/dashboard`, `GET /api/admin/users` after admin login

---

## Filters — investigation notes

**Fixed:** `position_looking_to_apply_only` wiring in `panel/service.py` → `FlattenFilters.from_kwargs()` maps to `PositionFilters.looking_to_apply_only`.

**Not fully audited:** other filters (visa, hide applied, position applied only, location, ATS, fetch ok/problem). Compare v1 `web/query.py` vs `web/query.py` if user reports more mismatches.

---

## Key file map

| Area | Paths |
|------|-------|
| v2 entry | `relocation_jobs/web/server.py` |
| Routes | `web/routes/{jobs,fetch,companies,admin,auth,catalog,board}.py` |
| Panel read | `panel/{service,board,flatten,tracking,stats,types}.py` |
| Positions | `positions/{service,repo,tracking_resolve,state,types}.py` |
| Catalog | `catalog/{repo,lookup,locations}.py` |
| Fetch/scrape | `fetch/`, `scrape/` |
| Client | `relocation_jobs/static/js/{api,board,board-view,events,state,job-board,scrape,render,data}.js`; `frontend/` → `static/dist/board.js` |
| Tests | `tests/` |
| Parity doc | `relocation_jobs/PARITY.md` |
| Business rules | `tests/BUSINESS_RULES.md` |

---

## Recommended next steps

1. **Verify position fix with user** on `:5051` after hard refresh — if still broken, get company name + two job titles + whether wrong job updates immediately or after reload.
2. **Stage & commit uncommitted work** if user approves — one logical commit for position isolation fix.
3. **Reproduce fetch live** — check `.env`, admin login, `GET /api/fetch/status`, orphan rows in `fetch_runs`.
4. **Reproduce admin** — admin login on `:5051`, inspect dashboard API response.
5. **Audit remaining filters** — v1 vs v2 query flag wiring.
6. **Run full v2 suite** before cutover: `python3 -m pytest tests -o addopts=`
7. **Do not switch production** — `panel_server` still v1; see `PARITY.md` cutover gate.

---

## If position bug persists after fixes

Check in order:

1. Browser cache — hard refresh, confirm `main.js?v=95` and `static/dist/board.js` loaded
2. Two jobs sharing idempotency — query param not in `_ID_QUERY_KEYS` in `core/job_identity.py`
3. Duplicate cards — catalog job + orphan with same idempotency (orphan skip should prevent)
4. User on v1 (`:5050`) not v2 (`:5051`)
5. Add integration test reproducing user's exact company/URLs from live catalog
