# v2 rules

How we build `relocation_jobs/v2/`. v1 (`services/`, `catalog/`, `scrape/`, `web/` shims) is **reference only** — read for behavior, do not import or bulk-copy.

Also read: `.claude/V2_CODING_VERDICT.md` (handoff + known violations), `.cursor/rules/v2-coding.mdc` (agent rule).

## Boundaries

| Layer | Role | SQL? | May import |
|-------|------|------|------------|
| **`*/repo.py`** | Load and persist domain data | **Yes — only here** | `core.*`, domain `types` |
| **`*/service.py`** | Business orchestration, validation | No | repos, other v2 domains, `core.*` |
| **`*/pipeline.py`** | Multi-step workflows (e.g. fetch → scrape → repo) | No | services, repos, scrape |
| **`web/routes/*.py`** | HTTP: parse request, call deps/service, JSON | No | `web/deps`, v2 services |
| **`shared/`** | Small cross-cutting helpers (no domain rules) | No | stdlib, `core` if needed |
| **`types.py`** | Pydantic models at domain boundaries | No | `shared.schema` |

**Do not** put `conn.execute`, `db_transaction`, or `get_connection` outside a domain’s `repo.py` (and `v2/db/migrate.py` for v2-only schema).

**Known violation:** `users/history.py` and `users/applied.py` still contain SQL — move into `users/repo.py`.

**Do not** import v1 application code (`services.*`, `catalog.*`, `catalog_db`, `scrape_jobs`, v1 `web.*`).

**OK to import** `relocation_jobs.core.*` (DB helpers, auth, `job_identity`, `location_tags`, `ats_constants`, paths) and `relocation_jobs.db.init_db` from the app entry/bootstrap only.

## Imports

- Top of module, unconditionally.
- No `try/except ImportError` for optional dependencies.
- No imports inside function bodies — fix structure instead of lazy imports.
- **Known violations:** `fetch/runner.py` (`httpx`), `positions/repo.py` (`get_connection` in one function), bootstrap lazy imports in `web/server.py`.

## File and module shape

- **Few files per domain**, not a mirror of v1’s tree.
- **~30–40 lines per function** where practical; split when a function mixes concerns or steps.
- **`types.py` per domain** for enums and API/DB boundary models (`BaseSchema` from `shared/schema.py`).
- **No re-export facades** — contract is **function name + tests**, not an extra module.
- **No `cp -r` from v1.** Copy one reviewed module at a time when porting scrape logic.
- **Delete dead code** — no shims, no “just in case” files (e.g. empty `web/routes/catalog.py`).

### Section order (within a module)

Keep **declarations before behavior** — do not interleave predicate tables with functions.

1. Imports  
2. **Types** — type aliases, enums, `@dataclass`, Pydantic models  
3. **Rules** — predicate tuples, early-exit tables, module constants used only by those rules  
4. **Private helpers** — `_`-prefixed functions  
5. **Public API** — functions routes and other domains call  

Predicate lambdas may call helpers defined later (runtime); still keep the **tuple definitions** above all functions.

### No comments in v2 source

- No section-divider comments (`# --- types ---`, `# --- rules ---`, etc.).
- No narrating comments on blocks (“first match wins”, “public API”).
- No docstrings by default — behavior should be clear from names and `tests/v2`.

### Readable flow

Prefer a **clear linear story** in orchestration code over many small wrappers and result dataclasses. Good reference: `scrape/merge.py` (index → walk scrape → keep stale → stamp).

## Naming

Names should state **what** and **when**, not generic verbs.

| Avoid | Prefer |
|-------|--------|
| `writes.py`, `save_company` | `repo.sync_company_board_to_catalog` |
| `persist()`, `save_fn` in cross-layer APIs | `sync_company_board_to_catalog` at scrape/fetch boundaries |
| `touch_*` without context | `patch_country_catalog_meta` |

**Known violation:** `save_fn` still used in `scrape/company.py`, `fetch/pipeline.py`, `fetch/service.py`.

## Control flow (branching)

- **Independent guards** (filters, skip rules): predicate tuples + `shared/predicates.any_of` / `all_of`, or a first-match priority table. Keep lambdas in the tuple; avoid a named function per rule unless it’s reused.
- **Different workflows** (apply vs unapply, scrape vs enrich): separate functions or top-level branches, not one boolean that changes everything.
- **Do not** add Strategy/State patterns for simple job-tracking rules — tests + `BUSINESS_RULES.md` are the spec.

## Data rules (catalog)

- **Postgres (Neon) is source of truth** on Render; no Redis until profiling shows catalog reads are the bottleneck.
- **`sync_company_board_to_catalog`**: caller passes **full** `matching_jobs` after `merge_matching_jobs`. Repo makes DB rows match that list exactly (upsert + delete stragglers). Partial lists will wipe catalog jobs — merge first.
- **Scrape never deletes roles** at the merge layer; repo delete only reflects what’s in the merged in-memory board.
- **Panel per-request `country_cache`** in `panel/service.py` is dedup within one request, not a distributed cache.

## Scrape and fetch

- **`process_company(..., fetch_board=...)`** — `fetch_board` is required and injected; v2 scrape must not default-import v1 ATS code.
- **Country fetch:** in-process runner (`fetch/country_runner.py`, `fetch/runner.py`), DB-backed status/cancel via `fetch_runs`. Serial per company for now; concurrency stored on run, parallel workers not yet implemented.
- **Single-company fetch:** `fetch/runner.py` + `POST /api/companies/fetch`.
- **Attempt logging** and **fetch run persistence** in `fetch/repo.py`.
- **ATS boards:** only Greenhouse under `scrape/boards/` so far.

## HTTP (`v2/web/`)

- New routes in `v2/web/routes/`, registered from `routes/__init__.py`.
- Shared query/body checks in `web/validators.py` or route-local when one-off.
- `web/deps.py` wires v2 services for routes — thin, no SQL.

## Tests

- **`pytest tests/v2`** during v2 work (not the full v1 suite every edit).
- **`tests/v2/<domain>/`** mirrors v2 domains; seed via `tests/v2/helpers/seed.py`.
- Map position/panel behavior to `tests/BUSINESS_RULES.md`; port scenarios from v1 tests by **behavior**, not by importing v1.
- Business rules for catalog board sync: `tests/v2/catalog/test_repo.py`.

## Render / deploy

- Free tier: `PANEL_SCRAPE_ENABLED=0`, scrape locally → Neon (or seed), panel reads DB.
- No dependency on process-local cache for correctness across instances.
- Optional `REDIS_URL` only if added later: cache **raw catalog reads** per country, invalidate on `sync_company_board_to_catalog`, never cache per-user merged panel.

## When to ask first

- New domain folder or moving logic across domains.
- Importing anything from v1 into v2.
- ATS port order, or cutover from `panel_server`.
- Anything that changes module boundaries (see `.claude/skills/engineering-standards/SKILL.md`).

## Known violations (fix in this order)

1. SQL outside repo: `users/history.py`, `users/applied.py`
2. Long functions: `panel/flatten.py`, `fetch/runner.py`, `fetch/repo.py`, `web/routes/jobs.py`, `web/routes/fetch.py`
3. `save_fn` naming in scrape/fetch stack
4. Lazy imports in `fetch/runner.py`, `positions/repo.py`
5. Empty shim: `web/routes/catalog.py`

## Roadmap

1. Fix violations above  
2. More ATS boards (lever, ashby, …)  
3. Country fetch parallel workers (if needed)  
4. Company CRUD / admin routes  
5. v2 entry replaces `panel_server` (cutover)

## Target layout (living)

```
v2/
  shared/       coerce, schema, timestamps, predicates
  catalog/      repo, lookup
  users/        repo, history, applied
  positions/    types, state, service, repo
  panel/        types, flatten, tracking, service, stats
  fetch/        types, repo, service, pipeline, runner, country_runner
  scrape/       relevance, filter, merge, listing, company, board, boards/
  web/          server, routes, deps, query, validators
  db/           migrate.py (v2-only tables)
```

Add files only when the domain gains a clear responsibility — not ahead of need.

## Run locally

```bash
pytest tests/v2 -o addopts=
PANEL_SCRAPE_ENABLED=1 python3 -c "from relocation_jobs.v2.web.server import app; app.run(port=5051)"
```
