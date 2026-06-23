# Relocation Jobs

A job-search tool for backend and software engineering roles at tech companies that offer visa or relocation sponsorship. Company lists are sourced from [relocate.me](https://relocate.me); each employer's ATS (Applicant Tracking System) is auto-detected and jobs are scraped into a shared catalog. A Flask web panel lets you track applications per user.

**Supported countries:** Germany, Netherlands, UK, Portugal.

## Features

- **ATS auto-detection** — Greenhouse, Lever, Ashby, Personio, Workable, Recruitee, SmartRecruiters, TeamTailor, and a generic Playwright fallback
- **Relevance filtering** — include/exclude keyword rules for backend and software roles
- **Web panel** — browse jobs by country, mark applied / not-for-me, trigger scrapes, add companies
- **Per-user tracking** — applied state and rejections stored in Postgres, merged with the catalog at read time
- **Concurrent scraping** — asyncio + httpx for ATS API calls (default 16 workers); Playwright in a thread pool for detection

## Quick start

```bash
# Install
pip install -r requirements-dev.txt
python3 -m playwright install chromium

# Configure (see Environment below)
cp .env.example .env
# Edit .env — set DATABASE_URL at minimum

# Run the panel
python3 scripts/panel_server.py
# → http://127.0.0.1:5050
```

On first startup the app creates the Postgres schema and bootstraps an admin user from `PANEL_ADMIN_USER` / `PANEL_ADMIN_PASSWORD`. If no password is set, a random one is printed to the terminal.

## Environment

Copy `.env.example` to `.env` before running locally.

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | **Required.** Neon Postgres URL (no SQLite fallback) |
| `PANEL_SECRET_KEY` | Flask session signing |
| `PANEL_ADMIN_USER` / `PANEL_ADMIN_PASSWORD` | Bootstrap admin on first run |
| `PANEL_SCRAPE_ENABLED` | Set to `0` on Render free tier (512 MB RAM) |
| `PANEL_DATA_DIR` | Local data dir for `custom_cities.json` (default: `data/`) |
| `PANEL_ALLOW_REGISTER` | Allow self-service registration after first user |

For local dev, a local Postgres instance is faster than remote Neon (~150 ms/query). See comments in `.env.example`.

## Usage

### Web panel

```bash
python3 scripts/panel_server.py
# or: python3 -m relocation_jobs.panel_server
```

Sign in with the admin credentials. Select a single country, then use **Fetch new jobs** to scrape. Per-company fetch, skip-filled, visa-only filter, and search are available in the toolbar and company cards.

Tracking (applied, not-for-me, company-level applied) is stored per user in Postgres. Re-scrapes merge jobs by URL — existing `fetched` dates and tracking state are preserved; jobs removed from an ATS stay in the catalog as orphans and reappear if you have tracking for them.

### Build company lists

Discovers careers URLs from relocate.me and company homepages, then writes to the Postgres catalog.

```bash
python3 scripts/build_companies.py netherlands
python3 scripts/build_companies.py uk "Monzo"          # single company
python3 scripts/build_companies.py netherlands --sort-only
```

Sort order: city (A–Z) → company size (smallest first) → name (A–Z).

### Scrape jobs

```bash
python3 scripts/scrape_jobs.py --country uk
python3 scripts/scrape_jobs.py --country uk "Monzo"              # single company
python3 scripts/scrape_jobs.py --country netherlands --skip-filled
python3 scripts/scrape_jobs.py --country germany --workers 16   # async (default 16)
python3 scripts/scrape_jobs.py --country uk --serial            # one company at a time
python3 scripts/scrape_jobs.py --all                            # all supported countries
```

On the first run per company, ATS type and API URL are detected and cached in Postgres. Later runs call the ATS REST API directly.

### Reset password

```bash
python3 scripts/reset_password.py <username>
```

## Architecture

### Data flow

```
relocate.me (country page)
    ↓
build_companies.py       ← careers URL discovery → Postgres catalog
    ↓
scrape_jobs.py           ← ATS detection + job fetch → Postgres catalog
    ↓
panel_server.py          ← Flask API (catalog + per-user tracking)
```

### Data stores

| Store | Contents |
|-------|----------|
| **Neon Postgres** (`DATABASE_URL`) | Catalog (companies, jobs), users, per-user tracking, fetch run history |
| `companies/*.json` | Git archive only — not read at runtime |
| `data/custom_cities.json` | User-added cities for the location picker (`PANEL_DATA_DIR`) |

On server startup, `init_db()` creates or migrates the Postgres schema. Populate the catalog with `build_companies.py` and `scrape_jobs.py`.

### Package layout

```
relocation_jobs/
├── panel_server.py     # Entry-point shim
├── web/                # Flask app, routes/, scrape_runner.py
├── catalog_db.py       # Shim → catalog/
├── catalog/            # Postgres catalog (schema, reads, writes, stats)
├── scrape_jobs.py      # Shim → scrape/
├── scrape/             # ATS dispatch, runner, enrich, IPC
├── build_companies.py  # Careers URL discovery CLI
├── core/               # db, auth, paths, ats_detection, ats_constants, job_identity
├── schemas/            # Pydantic models for JSON columns + API contracts
├── db/                 # User/tracking repo
└── services/           # Business logic (catalog, company, job, admin)
```

Import graph: `panel_server → web → services → (catalog_db, db/) → core/db → psycopg`. `scrape_jobs → catalog_db + scrape/ + core/ats_detection`.

### ATS detection (first run per company)

```
careers_url
  → 1. KNOWN_ATS override (core/ats_constants.py)?
  → 2. detect_ats_static() — HTTP + HTML regex
  → 3. detect_ats_via_playwright() — headless Chromium, XHR interception
  → 4. generic fallback — Playwright DOM parse for job links
```

Detected `ats_type` and `ats_url` are written to Postgres. Subsequent scrapes use the cached API endpoint.

### Supported ATS platforms

| ATS | Scraping |
|-----|----------|
| Greenhouse (US/EU) | REST API `boards-api[.eu].greenhouse.io/v1/boards/{slug}/jobs` |
| Lever (US/EU) | REST API `api.lever.co` / `jobs.eu.lever.co` |
| Ashby | REST API `api.ashbyhq.com/posting-api/job-board/{slug}` |
| Personio | XML feed `{base}/xml` |
| Workable | REST API `apply.workable.com/api/v2/accounts/{slug}/jobs` |
| Recruitee | REST API `{slug}.recruitee.com/api/offers/` |
| SmartRecruiters | REST API `api.smartrecruiters.com/v1/companies/{id}/postings` |
| TeamTailor | REST API with intercepted API key |
| Generic | Playwright DOM parse |

### Job filtering

Jobs match when the title contains an **include** keyword and no **exclude** keyword (case-insensitive). Rules live in `relocation_jobs/core/ats_constants.py` (`INCLUDE_KEYWORDS`, `EXCLUDE_KEYWORDS`). Implementation: `relocation_jobs/scrape/relevance.py`.

## Testing

```bash
pytest                                   # business tier (default; excludes @scrape)
pytest -m scrape                         # scraper + build_companies
pytest --cov --cov-report=term-missing   # coverage (90% gate on business modules)
```

Tests use an in-memory Postgres mock (`tests/helpers/postgres_mock.py`) — no live ATS or Neon in CI. Business rules are documented in `tests/BUSINESS_RULES.md`.

## Deployment (Render)

`render.yaml` targets Render's **free** web tier. Scraping is disabled in production (`PANEL_SCRAPE_ENABLED=0`) because of the 512 MB RAM limit.

**Workflow:** scrape locally → push to GitHub → Render redeploys. All runtime state lives in Neon Postgres.

### One-time setup

1. Create a [Neon](https://neon.tech) project and copy the Postgres connection string.
2. Push this repo to GitHub.
3. In [Render](https://render.com): **New → Blueprint** → connect the repo.
4. Set env vars: `DATABASE_URL`, `PANEL_ADMIN_PASSWORD`.
5. Deploy and sign in at `https://<your-service>.onrender.com`.

### Local Docker smoke test

```bash
docker build -t relocation-jobs .
docker run --rm -p 8080:10000 \
  -e PORT=10000 \
  -e PANEL_ADMIN_PASSWORD=changeme123 \
  -e DATABASE_URL="postgresql://..." \
  relocation-jobs
```

## Development

Contributor-oriented docs (commands, fixtures, refactor status):

- [`CLAUDE.md`](CLAUDE.md) — architecture, test tiers, deployment notes
- [`tests/BUSINESS_RULES.md`](tests/BUSINESS_RULES.md) — panel job-state rules
- [`.claude/REFACTOR_HANDOFF.md`](.claude/REFACTOR_HANDOFF.md) — active structural refactor checklist

## Troubleshooting

**Company returns 0 jobs but has openings**

1. Clear cached ATS in the catalog (or delete `ats_type` / `ats_url` for that company) and re-scrape.
2. Inspect the careers page in DevTools (Network tab) for the ATS API call.
3. Add a manual override to `KNOWN_ATS` in `relocation_jobs/core/ats_constants.py`.

**Playwright detection hangs**

Timeout is ~25 s plus a short settle wait. Pages behind login or heavy cookie banners may need a `KNOWN_ATS` entry.

**ATS returns 401 / 403**

Try US vs EU Greenhouse/Lever variants. Recruitee sometimes proxies through `careers-analytics.recruitee.com` — the real slug is required.

**Wrong careers URL from auto-discovery**

Open the company site in a browser, follow the careers CTA, copy the URL, and update the company in the panel or re-run `build_companies.py` for that employer.
