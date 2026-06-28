# Contributing

**Last updated:** 2026-06-26

Developer setup and where to work. Product usage: [README](../README.md). Doc index: [README.md](README.md).

---

## What this is

A job-search panel for backend/software roles at visa-friendly companies.

```
relocate.me → build_companies.py → Postgres catalog
                              ↓
                    country fetch (v2) → scrape ATS boards → Postgres
                              ↓
                    Flask panel (v2) + static JS UI → per-user tracking
```

**Supported countries:** Germany, Netherlands, UK, Portugal.

---

## Current architecture

| Layer | Status | Location |
|-------|--------|----------|
| **v2 application spine** | **Active — code here** | `relocation_jobs/` |
| **v1** | Reference only; do not extend | legacy paths under `relocation_jobs/` |
| **Static UI** | Shared | `relocation_jobs/static/` + `frontend/` |
| **Postgres** | AWS EC2 Docker (Frankfurt) | `DATABASE_URL` in `.env` |
| **Production panel** | Render (still v1 entry) | `render.yaml`, port 5050 in prod |

Local dev uses v2 on **5051**. More detail: [reference/architecture.md](reference/architecture.md).

---

## First 15 minutes

```bash
pip install -r requirements-dev.txt
python3 -m playwright install chromium
cp .env.example .env
# Set DATABASE_URL, PANEL_SECRET_KEY, PANEL_ADMIN_USER, PANEL_ADMIN_PASSWORD

PANEL_SCRAPE_ENABLED=1 python3 scripts/panel_server.py
# → http://127.0.0.1:5051

pytest tests -o addopts=
```

| Panel | Port | Entry |
|-------|------|-------|
| **v2 (dev)** | 5051 | `scripts/panel_server.py` |
| v1 (legacy) | 5050 | `python3 -m relocation_jobs.panel_server` |

After JS/CSS: hard refresh (`Cmd+Shift+R`). After React: `cd frontend && npm run build`.

---

## Where to code

### v2 domains (`relocation_jobs/`)

```
catalog/      Postgres company + job reads/writes (repo.py)
positions/    Per-user job state (apply, reject, not-for-me)
panel/        flatten_companies, paginated board, stats, filters
fetch/        Country + single-company fetch (in-process asyncio)
scrape/       ATS boards, merge, enrich, relevance
companies/    Company CRUD orchestration
users/        User history, applied dates
admin/        Dashboard aggregates
web/          Flask server, routes, deps
shared/       predicates, coerce, schema helpers
db/           v2-only migrations
```

**Rules:** [reference/rules.md](reference/rules.md) — SQL **only** in `*/repo.py`.

### Client

- Board: `GET /api/board` — see [reference/board.md](reference/board.md)
- Layout: pagination → search → sort/filters → company cards
- After job mutations: local updates in `job-board.js`, not full reload
- React bundle: `frontend/` → `npm run build` → `static/dist/board.js`

### Do not touch without asking

- v1 legacy modules — reference only
- `render.yaml` / production cutover
- AWS infra (`scripts/aws_postgres_migrate.sh`)
- **Do not commit** unless explicitly asked

---

## Database

- **Prod + dev:** AWS EC2 Postgres — [operations/aws-postgres.md](operations/aws-postgres.md)
- **After IP change:** `./scripts/aws_postgres_migrate.sh sync-sg`
- **Tests:** in-memory Postgres mock only — never hit live DB or ATS

---

## Fetch & scrape

- Country fetch: in-process asyncio (`fetch/country_runner.py`)
- Concurrency: default 16, hard cap 16 (`core/ats_constants.py`)
- Live state: `fetch_runs` + `GET /api/fetch/status`
- CLI: `scrape_jobs.py`, `build_companies.py` for batch/offline

---

## Tests

| Command | Scope |
|---------|--------|
| `pytest tests -o addopts=` | **Default for v2 work** |
| `pytest tests/test_route_manifest.py -o addopts=` | Fast API route check |
| `pytest -o addopts=` | v1 business tier (CI) |
| `pytest -m scrape -o addopts=` | Scraper + build_companies |

Job-state changes: read [reference/business-rules.md](reference/business-rules.md) first.

---

## Standards (agents)

| Resource | When |
|----------|------|
| [reference/rules.md](reference/rules.md) | Any `relocation_jobs/` or `tests/` edit |
| [reference/business-rules.md](reference/business-rules.md) | Job tracking / panel buckets |
| `.claude/skills/` | Collaboration, engineering standards, module layout |

---

## Known open items

1. Render cutover to v2 entry ([reference/parity.md](reference/parity.md))
2. SQL still in `users/history.py`, `users/applied.py` ([archive/v2-coding-verdict.md](archive/v2-coding-verdict.md))
3. Deep board pages rescan catalog from start (cursor pagination future work)
