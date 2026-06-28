# v2 coding verdict (handoff)

Read this before continuing v2 work. **Entry point:** [`docs/README.md`](../README.md).

**Rules for humans and agents:**
- `docs/reference/rules.md` — canonical
- `.cursor/rules/v2-coding.mdc` — Cursor auto-loads when editing v2
- `.claude/skills/module-layout/SKILL.md`, `.claude/skills/engineering-standards/SKILL.md`

---

## What v2 is

- **`relocation_jobs/`** is the new spine. v1 (`services/`, `catalog/`, `scrape/`, v1 `web/`) is **reference only** — read behavior, **never import** into v2 app layers.
- Tests during v2 work: **`pytest tests`** (not the full v1 suite every edit).
- Do not commit unless explicitly asked.

---

## Layer rules (non‑negotiable)

| Layer | SQL? | Role |
|-------|------|------|
| `*/repo.py` | **Yes — only here** (+ `db/migrate.py`) | Load/persist domain data |
| `*/service.py`, `*/pipeline.py` | No | Orchestration, validation |
| `web/routes/*.py` | No | Parse HTTP → call service/deps → JSON |
| `shared/` | No | Small helpers (coerce, predicates, timestamps) |
| `types.py` | No | Pydantic boundary models |

**Fix next:** move SQL out of `users/history.py` and `users/applied.py` into `users/repo.py`.

---

## Module layout (every file)

Order inside a file — **do not mix**:

1. Imports  
2. Types (aliases, enums, `@dataclass`, Pydantic)  
3. Rules (predicate tuples, early-exit tables, constants for those rules)  
4. Private helpers (`_` prefix)  
5. Public API  

**No comments** in source: no section banners (`# --- types ---`), no narrating block comments, no docstrings unless you later decide one public entry truly needs it (default: none).

Predicate lambdas may call helpers defined below them (runtime); still put **tuple definitions above all functions**.

---

## Function size & control flow

- Target **~30–40 lines** per function. Split when a function does multiple steps (index → merge → append → stamp).
- **Different workflows = different functions** (scrape vs enrich, apply vs unapply). Not one boolean that changes everything.
- **Independent guards** = predicate tuples + `shared/predicates.any_of` / `all_of`, or first-match priority table. Do not explode into one named function per trivial rule.
- Prefer **readable linear flow** over many indirection layers (see `merge.py` — three clear passes, not a result dataclass + six orchestration helpers).

---

## Naming

| Avoid | Prefer |
|-------|--------|
| `save_fn`, `persist()` | `sync_company_board_to_catalog` at boundaries |
| `writes.py`, `save_company` | `catalog/repo.sync_company_board_to_catalog` |
| Generic verbs without context | Names that say **what** and **when** |

---

## Imports (engineering standards)

- Imports at **top of module**, unconditionally.
- No `try/except ImportError` for optional deps.
- No imports inside functions — except genuine bootstrap/circular cases (v2 still has violations in `fetch/runner.py`, `positions/repo.py`, `web/server.py` to clean up).
- If top-level import causes circular import → **fix structure**, don’t lazy-import.

---

## Data rules

- **Postgres (AWS EC2 Docker) is source of truth** for dev and prod. No Redis on Render for now.
- **`sync_company_board_to_catalog`**: caller passes **full** `matching_jobs` after `merge_matching_jobs`. Repo upserts + deletes stragglers. Partial list wipes catalog jobs.
- Scrape merge **never deletes roles**; repo delete only reflects the merged in-memory board.

---

## Scrape & fetch

- `process_company(..., fetch_board=...)` — `fetch_board` injected; v2 must not default-import v1 ATS code.
- Country fetch: v2 **in-process** asyncio (`fetch/country_runner.py`, `fetch/runner.py`), DB-backed status/cancel.
- Concurrency: `DEFAULT_CONCURRENCY = 16`, hard cap `MAX_CONCURRENCY = 16` — do not raise without EC2 upgrade.
- ATS boards under `scrape/boards/` (greenhouse, lever, ashby, workable, …).
- Attempt logging: `fetch/repo.py` (`company_fetch_attempts`). Fetch runs: `fetch_runs` table.

---

## Files & dead code

- Few files per domain — no mirror of v1 tree.
- **No re-export facades** — contract = function name + tests.
- **Delete dead code** — e.g. empty `web/routes/catalog.py` should go or get real routes.
- No `cp -r` from v1; port one reviewed module at a time.

---

## Known violations to fix (priority order)

1. **SQL outside repo:** `users/history.py`, `users/applied.py`  
2. **Long functions:** `panel/flatten.py`, `fetch/runner.py`, `fetch/repo.py`, `web/routes/jobs.py`, `web/routes/fetch.py`  
3. **`save_fn` naming:** `scrape/company.py`, `fetch/pipeline.py`, `fetch/service.py`  
4. **Lazy imports:** `fetch/runner.py` (httpx), `positions/repo.py`  
5. **Empty shim:** `web/routes/catalog.py`  

---

## Roadmap still open

1. Fix violations above  
2. v2 Render cutover  
3. Port remaining `BUSINESS_RULES` test gaps  
4. Optional SQL optimizations (`resolve_tracking_url`, etc.)  

---

## Current state (2026-06-25)

- **~100 tests** passing in `tests/v2`
- Working: catalog sync, panel flatten, positions, all major ATS boards, parallel country fetch (cap 16), single-company fetch API, fetch cancel (in-process), `recent_fetch_runs` in stats
- Client: job mutations should use local board updates (`job-board.js`) — not full `reloadBoard()` after every action

Run locally:

```bash
pytest tests -o addopts=
PANEL_SCRAPE_ENABLED=1 python3 -c "from relocation_jobs.web.server import app; app.run(host='127.0.0.1', port=5051)"
```
