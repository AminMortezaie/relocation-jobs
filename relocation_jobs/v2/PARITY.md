# v2 parity checklist

Living assessment of v1 (`relocation_jobs/web/`, `panel_server`) vs v2 (`relocation_jobs/v2/`).

**How to use:** update status when you close a gap. Do not duplicate v1’s `test_panel_api_full.py` — use this doc + `tests/v2/test_route_manifest.py` + rule-ID tests in `tests/BUSINESS_RULES.md`.

**Run checks:**

```bash
pytest tests/v2/test_route_manifest.py -o addopts=   # route surface (~ms)
pytest tests/v2 -o addopts=                          # full v2 suite
```

---

## Status legend

| Mark | Meaning |
|------|---------|
| ✅ | Implemented and covered by v2 tests |
| ⚠️ | Partial / behavioral gap |
| ❌ | Not implemented |
| ➕ | v2-only (not in v1) |

---

## HTTP routes (panel + admin UI)

Automated: `tests/v2/helpers/route_manifest.py` + `tests/v2/test_route_manifest.py`.

| Area | v1 | v2 | Status |
|------|----|----|--------|
| Auth (4) | `web/routes/auth.py` | `v2/web/routes/auth.py` | ✅ |
| Catalog metadata (6) | `web/routes/catalog.py` | `v2/web/routes/catalog.py` | ✅ |
| Jobs + tracking (9) | `web/routes/jobs.py` | `v2/web/routes/jobs.py` | ✅ |
| Companies (12) | `web/routes/companies.py` | `v2/web/routes/companies.py` | ✅ + ➕ company detail GET |
| Fetch (5) | `web/routes/fetch.py` | `v2/web/routes/fetch.py` | ✅ + ➕ `/api/fetch/attempts` |
| Admin (6) | `web/routes/admin.py` | `v2/web/routes/admin.py` | ✅ |
| Pages `/`, `/admin` | `web/app.py` | `v2/web/server.py` | ✅ |

`static/js/api.js` paths must stay in `route_manifest.py` (enforced by test).

---

## Fetch / scrape behavior

| Feature | v1 | v2 | Status | Priority |
|---------|----|----|--------|----------|
| Country fetch runner | Subprocess `scrape_jobs.py` + IPC | In-process thread + asyncio | ⚠️ different architecture | — |
| Parallel workers (`workers` / `concurrency`) | Yes, default 16 | Serial; field stored only | ❌ | P2 |
| Default concurrency on `POST /api/fetch` | 16 (`DEFAULT_CONCURRENCY`) | 16 (`DEFAULT_CONCURRENCY`) | ✅ | P1 |
| ATS boards (all `ATS_TYPE_CHOICES`) | `scrape_jobs.py` | `v2/scrape/boards/` | ✅ | — |
| Generic careers fallback | `scrape/generic.py` | `v2/scrape/boards/generic.py` | ✅ | — |
| ATS detect before fetch | `scrape/dispatch.py` | `v2/scrape/ats_resolve.py` | ✅ | — |
| Job enrichment (visa/relocation) | `scrape/enrich.py` | `v2/scrape/enrich.py` | ✅ | — |
| `review_jobs` in fetch status (modal) | `@@REVIEW@@` IPC | DB column exists, not populated | ❌ | P2 |
| Live `activity` during fetch | IPC `@@ACTIVITY@@` | Log lines only | ⚠️ | P2 |
| `GET /api/fetch/history` | Admin user runs | Same | ✅ | — |
| `GET /api/fetch/attempts` | — | Per-company attempt log | ➕ | — |
| Country cancel (admin only) | Yes | Yes | ✅ | — |
| Post-fetch country meta | `touch_country_meta` | `patch_country_catalog_meta` | ✅ | — |
| Single-company fetch | `fetch_run` + thread; 409 if busy | `fetch_run` + background thread | ✅ | — |
| `touch_company_fetch_time` on company fetch | Yes | Yes | ✅ | — |
| Busy guard on `POST /api/companies/fetch` | 409 if fetch running | 409 if fetch running | ✅ | — |
| Cancel reliability | Subprocess SIGTERM (broken UX) | In-process cancel | ⚠️ verify manually | P0 |

---

## Panel read path & business rules

Spec: `tests/BUSINESS_RULES.md` (rules 1–16).

| Feature | v1 | v2 | Status |
|---------|----|----|--------|
| `flatten_companies` | `services/catalog_service.py` | `v2/panel/` | ✅ |
| Job buckets (jobs / rejected / not-for-me) | v1 tests | `tests/v2/positions/test_state.py` | ✅ partial |
| Orphan reinjection | v1 tests | `test_state.py` | ✅ partial |
| Full rule matrix | `test_job_state_rules.py`, `test_business_rules_coverage.py` | `tests/v2/positions/test_workflows.py` | ⚠️ port gaps by rule ID |
| Panel filters (visa, location, ATS, …) | `test_panel_api_full.py` | Thin `test_jobs_api.py` only | ⚠️ |
| `compute_stats` / recent fetch runs | v1 | `v2/panel/stats.py` | ✅ |
| Custom cities (`POST /api/locations`) | v1 | v2 catalog route | ✅ |

---

## Data / domain layer

| Feature | v1 | v2 | Status |
|---------|----|----|--------|
| Catalog Postgres reads/writes | `catalog_db` / `catalog/` | `v2/catalog/repo.py` | ✅ |
| User tracking | `db/` + `services/` | `v2/users/repo.py`, `v2/positions/` | ✅ |
| Company CRUD orchestration | `companies/service.py` | Re-export `relocation_jobs.companies.service` | ⚠️ not native v2 |
| Admin dashboard aggregates | `services/admin_service.py` | `v2/admin/service.py` + `v2/catalog/stats.py` | ✅ |
| Locations list | `catalog_service.list_company_locations` | `v2/catalog/locations.py` | ✅ |

---

## Ops / cutover

| Item | v1 | v2 | Status |
|------|----|----|--------|
| Production entry | `panel_server` :5050 | `v2/web/server.py` :5051 | ❌ not switched |
| Render `render.yaml` | v1 | v1 | ❌ |
| `PANEL_SCRAPE_ENABLED=0` on Render | Yes | Supported in routes | ✅ |

---

## Cutover gate (manual)

Before pointing `panel_server` at v2:

1. [x] P0 fetch gaps closed (single-company fetch run, busy guard, `touch_company_fetch_time`)
2. [ ] `pytest tests/v2 -o addopts=` green
3. [ ] `pytest tests/v2/test_route_manifest.py -o addopts=` green
4. [ ] Smoke: login → jobs list → apply job → country fetch → cancel → admin dashboard
5. [ ] Fetch cancel verified on real scrape (local)

Optional pre-cutover script (not in CI): `scripts/smoke_v2_panel.sh` — add when ready.

---

## Test strategy (do not regress)

| Layer | Location | CI |
|-------|----------|-----|
| Route manifest | `tests/v2/test_route_manifest.py` | Yes, fast |
| Business rules | `tests/v2/positions/`, `tests/v2/panel/`, `tests/v2/catalog/` | Yes |
| Thin API contracts | `tests/v2/web/` | Yes |
| Full v1 API clone | `tests/test_panel_api_full.py` | v1 only until delete |
| Browser E2E | — | No |

When fixing a v2 bug, add the **smallest** test in the matching `tests/v2/<domain>/` file — not a new mega integration file.
