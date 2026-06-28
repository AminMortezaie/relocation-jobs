# Refactor handoff — historical (v1 Phase A–C)

> **Superseded by v2** (2026-06-25). New work goes in `relocation_jobs/`. Read [`docs/contributing.md`](../contributing.md) instead of continuing Phase D unless the user explicitly asks.

**Status (2026-06-23):** Phases **A, B, C complete** in the working tree. **Phase D not started** — paused in favor of v2 domain layout.

---

## Verify before touching anything

```bash
python3 -m pytest -q              # business tier — expect 334 passed
python3 -m pytest -m scrape -q    # scraper tier — expect 403 passed
```

CI (`.github/workflows/ci.yml`): business tier + 90% coverage gate (`fail_under=90`; scrape CLIs omitted).

---

## What was just finished (Phase C — do not redo)

`scrape_jobs.py` went from ~1,545 LOC monolith → **~231 LOC shim**. Implementation lives in `relocation_jobs/scrape/`.

### Layout

```
relocation_jobs/
├── scrape_jobs.py              # shim: re-exports, monkeypatch wrappers, main/run_country CLI
└── scrape/
    ├── __init__.py             # public: merge_matching_jobs, is_relevant, …
    ├── _compat.py              # bulk re-exports copied into scrape_jobs (incl. _underscore names)
    ├── shim_bind.py            # scrape_jobs_shim() — lazy bind back to scrape_jobs module
    ├── enrich.py               # fetch_job_description, enrich_jobs, async enrichment
    ├── dispatch.py             # get_jobs, get_jobs_async, ATS override helpers
    ├── runner.py               # process_company_async, run_file_async
    ├── ipc.py                  # progress/review/activity IPC + review_filtered_jobs
    ├── util.py                 # today(), safe_print()
    ├── http.py                 # requests/httpx — HTTP mock patch target
    ├── playwright.py           # PLAYWRIGHT_AVAILABLE, sync_playwright — PW mock target
    ├── listing.py, descriptions.py, generic.py, merge.py, relevance.py
    └── greenhouse.py, lever.py, recruitee.py, ashby.py, workable.py, … (per-ATS)
```

### Critical design: test monkeypatch contract

Hundreds of scraper tests do `from relocation_jobs import scrape_jobs as sj` and `monkeypatch.setattr(sj, "…")`. **Do not break this.**

| Pattern | Why |
|---------|-----|
| `scrape_jobs_shim()` in dispatch/enrich/runner | `get_jobs_async`, `load_country_catalog`, `fetch_job_description`, etc. resolve via `sj` at **call time** so patches work |
| Wrappers stay on shim (not bare aliases) | `_jobs_from_listing_html_async`, `scrape_ashby_async`, `scrape_personio`, `scrape_jibe`, `scrape_atlassian`, `scrape_teamtailor`, `_report_activity` |
| `main` / `run_country` on shim | Tests patch `sj.run_country` / `sj.run_file_async` |
| `_compat` + `globals().update` loop | Re-exports `_underscore` names (`import *` skips them) |
| `PLAYWRIGHT_AVAILABLE` refreshed from `ats_detection` after `_compat` loop | `test_scrape_import_error_playwright` reloads `ats_detection` and expects shim to pick up `False` |

**If you move or rename `scrape_jobs.py`:** update `tests/helpers/http_mock.py`, `tests/helpers/playwright_mock.py`, `web/scrape_runner.py` (`-m relocation_jobs.scrape_jobs`), and every `sj.*` patch path — or keep a root shim re-exporting the new location.

### Prior phases (summary)

| Phase | Done |
|-------|------|
| **A** | Removed `panel_data`/`admin_data` shims; test consolidation; `core/ats_constants`, `core/slug`; Postgres-only |
| **B** | ATS detection → `core/ats_detection.py`; `company_service` no longer imports `scrape_jobs`; JSON-era naming cleanup |
| **C** | `panel_server` → `web/`; `catalog_db` → `catalog/`; `scrape_jobs` → `scrape/` + shim |

---

## Phase D — your work (NEXT)

Read `.claude/skills/restructure-plan/SKILL.md` and `.claude/skills/project-state/SKILL.md` first.

### Target (user-approved direction)

```
relocation_jobs/
├── core/           # shared utils, core/db.py
├── companies/      # repo + service (+ domain if needed)
├── jobs/           # repo + service; scrape_jobs.py moves here eventually
├── users/
├── admin/
├── web/            # already exists (from Phase C panel split)
├── catalog/        # already exists (from Phase C catalog split)
└── schemas/        # Pydantic contracts — already in use; clarify scope with user if unsure
```

### Suggested sequence (ask user before starting)

1. **Audit import graph** — grep all imports of `services/`, `catalog_db`, `db/`, `scrape_jobs`, `panel_server`.
2. **`core/` consolidation** — mostly done; fix `core/db` ↔ `catalog.schema` cycle if structurally feasible (today: lazy import in `init_db()`).
3. **One domain at a time** — e.g. `companies/` first (smallest blast radius), then `jobs/`, `users/`, `admin/`.
4. **Keep shims during transition** — like `catalog_db.py` (13 LOC) and `panel_server.py` (72 LOC): old import paths re-export until tests/callers updated.
5. **Move `scrape_jobs.py` → `jobs/scrape_jobs.py`** only when `jobs/` package exists; leave `relocation_jobs/scrape_jobs.py` as thin re-export shim OR update `web/scrape_runner.py` subprocess cmd + all test imports in one block.
6. **Run tests after each logical block** — not after every file.

### Open questions for user (ask, don't guess)

- Exact contents of each domain's `repo.py` vs keeping `catalog/` as shared catalog layer
- Whether `services/catalog_service.py` becomes cross-domain or splits per domain
- `schemas/` ownership — already has Pydantic models; confirm before moving SQL/schema init

---

## Minor cleanup (low priority, no domain moves)

- [ ] Hoist remaining lazy imports in `services/`
- [ ] `README.md` stale `panel_data` / JSON references
- [ ] Commit when user asks

---

## Current import graph

```
panel_server → web.app + web.scrape_runner + web.deps (re-exports)
web.routes   → web.deps + services + catalog_db + db/
services     → catalog (via catalog_db shim) + db/ + core/
scrape_jobs  → scrape/* + catalog_db + core/ats_detection + core/   (shim only)
company_service → core/ats_detection + catalog_db + db/              (NOT scrape_jobs) ✅
catalog_db   → catalog/* shim
catalog/*    → core.db directly ✅
scrape/*     → scrape.http, core/ats_detection, scrape_jobs_shim() at runtime
core/db      → lazy import catalog.schema.init_catalog_schema (cycle — open)
```

---

## Key files

| Path | Role |
|------|------|
| `relocation_jobs/scrape_jobs.py` | Scraper CLI shim (~231 LOC) |
| `relocation_jobs/scrape/` | Scraper implementation |
| `relocation_jobs/panel_server.py` | HTTP entry shim (72 LOC) |
| `relocation_jobs/catalog_db.py` | Catalog shim (13 LOC) |
| `relocation_jobs/web/scrape_runner.py` | Spawns `python -m relocation_jobs.scrape_jobs` |
| `relocation_jobs/core/ats_detection.py` | Shared ATS detection (827 LOC) |
| `relocation_jobs/services/` | Business logic (move targets for Phase D) |
| `relocation_jobs/db/` | User/tracking repos (move targets for Phase D) |
| `tests/BUSINESS_RULES.md` | Job state contracts — read before touching tracking logic |
| `tests/helpers/http_mock.py` | Patches `scrape.http` + `scrape_jobs` |
| `tests/helpers/playwright_mock.py` | Patches `scrape_jobs`, `scrape.playwright`, `scrape.generic`, `scrape.misc`, `core.ats_detection` |

---

## Uncommitted files (snapshot)

Staged/new: `relocation_jobs/scrape/*` (ATS modules, merge, listing, …).

Untracked (Phase C finish): `scrape/_compat.py`, `dispatch.py`, `enrich.py`, `runner.py`, `shim_bind.py`, `util.py`, `playwright.py`.

Modified: `scrape_jobs.py`, `scrape/generic.py`, `scrape/ipc.py`, `scrape/misc.py`, `scrape/teamtailor.py`, `core/ats_detection.py`, test helpers + scrape tests.

---

## Do NOT

- Re-add `panel_data.py` / `admin_data.py` shims
- Re-split `scrape_jobs` / undo Phase C without user approval
- Big-bang Phase D in one PR — move one domain at a time with shims
- Replace monkeypatch-sensitive shim wrappers with bare `foo = module.foo` assignments
- Duplicate ATS detection outside `core/ats_detection.py`
- Break `from relocation_jobs.scrape_jobs import merge_matching_jobs` without updating callers
- Run `pytest -m scrape` on every business-tier-only edit
- Commit unless user asks

---

## Suggested first prompt for next agent

> Read `.claude/REFACTOR_HANDOFF.md`, `restructure-plan`, and `project-state` skills. Phase C is done (334 business + 403 scrape tests pass; `scrape_jobs.py` is a ~231 LOC shim over `scrape/`). Start Phase D: audit the import graph and propose a move sequence for `companies/` first — ask me before creating domain folders. Keep compatibility shims like `catalog_db.py`. Run `python3 -m pytest` and `python3 -m pytest -m scrape` after each block. Do not commit unless I ask.
