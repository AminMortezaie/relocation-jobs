# Relocation Jobs

A job-search tool for backend and software engineering roles at tech companies that offer visa or relocation sponsorship. Company lists are sourced from [relocate.me](https://relocate.me); each employer's ATS (Applicant Tracking System) is auto-detected and jobs are scraped into a shared catalog. A Flask web panel lets you track applications per user and prepare tailored resume PDFs per position.

**Supported countries:** Germany, Netherlands, UK, Portugal.

> **Contributors:** [`docs/contributing.md`](docs/contributing.md) · [`docs/`](docs/README.md)

## Features

- **ATS auto-detection** — Greenhouse, Lever, Ashby, Personio, Workable, Recruitee, SmartRecruiters, TeamTailor, and a generic Playwright fallback
- **Relevance filtering** — include/exclude keyword rules for backend and software roles
- **Web panel** — paginated company board (25 per page), filters and search, mark applied / not-for-me, trigger scrapes, add companies
- **Per-user tracking** — applied state and rejections stored in Postgres, merged with the catalog at read time
- **Application assistant** — per-position tailored LaTeX + PDF (Claude Desktop MCP), profile and master resumes on `/apply`, company workspace at `/company/<country>/<slug>` with live PDF preview
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
PANEL_SCRAPE_ENABLED=1 python3 scripts/panel_server.py
# → http://127.0.0.1:5051
```

On first startup the app creates the Postgres schema and bootstraps an admin user from `PANEL_ADMIN_USER` / `PANEL_ADMIN_PASSWORD`. If no password is set, a random one is printed to the terminal.

## Environment

Copy `.env.example` to `.env` before running locally.

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | **Required.** Postgres URL — AWS EC2 (see `.env.example`) or local instance |
| `PANEL_SECRET_KEY` | Flask session signing |
| `PANEL_ADMIN_USER` / `PANEL_ADMIN_PASSWORD` | Bootstrap admin on first run |
| `PANEL_SCRAPE_ENABLED` | Set to `0` on Render free tier (512 MB RAM); `1` locally for fetch |
| `PANEL_DATA_DIR` | Local data dir for `custom_cities.json` (default: `data/`) |
| `PANEL_ALLOW_REGISTER` | Allow self-service registration after first user |
| `MCP_USERNAME` / `MCP_USER_ID` | Panel user for Claude Desktop MCP (default `admin`) |
| `MCP_LATEX_CMD` | LaTeX compiler for PDF render (default `tectonic`) |

Application assistant docs: [mcp-application.md](docs/reference/mcp-application.md) · [company-workspace.md](docs/reference/company-workspace.md).

AWS Postgres ops: `./scripts/aws_postgres_migrate.sh sync-sg` after your public IP changes. See [docs index § Operations](docs/README.md#5-operations).

For local dev, a local Postgres instance is faster than remote AWS (~150 ms/query). See comments in `.env.example`.

## Usage

### Web panel

```bash
PANEL_SCRAPE_ENABLED=1 python3 scripts/panel_server.py
# → http://127.0.0.1:5051
```

Sign in with the admin credentials. Select a single country, then use **Fetch** (admin) to scrape. The main board loads one page at a time via `GET /api/board` (default 25 companies per page, filter-aware). Toolbar order: **pagination → search → sort/filters**. Per-company fetch, skip-filled, and visa-only are in the toolbar and company cards.

Your aggregate stats (applied counts, fetch summary) live on the **admin** page (`GET /api/admin/panel-stats`), not on the main board — the board response only includes lightweight `user_stats` for the header chip.

After changing React UI (`frontend/`), run `cd frontend && npm run build` (outputs `relocation_jobs/static/dist/board.js`). Hard refresh after JS/CSS changes (`Cmd+Shift+R`).

Tracking (applied, not-for-me, company-level applied) is stored per user in Postgres. Re-scrapes merge jobs by URL — existing `fetched` dates and tracking state are preserved; jobs removed from an ATS stay in the catalog as orphans and reappear if you have tracking for them.

**Application data** (`/apply`) — edit profile, pipeline prompts, and master resume `.tex` variants (per logged-in user).

**Company workspace** (`/company/<country>/<company-slug>`) — open from a company name on the board to see all positions, tailored LaTeX, PDF preview, and re-render. CV/PDF badges appear on the board when MCP has prepared artifacts for a role.

**Claude Desktop MCP** — `python3 scripts/mcp_server.py` exposes tools to tailor resumes per job, validate, render PDF, mark applied, and **add companies** (same flow as the panel Add company dialog). See [docs/reference/mcp-application.md](docs/reference/mcp-application.md).

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
v2 fetch / scrape_jobs   ← ATS detection + job fetch → Postgres catalog
    ↓
web/server.py         ← Flask API (catalog + per-user tracking)
```

### Data stores

| Store | Contents |
|-------|----------|
| **Postgres** (`DATABASE_URL`) | Catalog, users, tracking, fetch runs — AWS EC2 in production |
| `companies/*.json` | Git archive only — not read at runtime |
| `data/custom_cities.json` | User-added cities (`PANEL_DATA_DIR`) |

### Package layout

```
relocation_jobs/
├── catalog/      # Postgres catalog repo + writes
├── positions/    # Job tracking (apply, reject, not-for-me)
├── panel/        # flatten_companies, paginated board, stats, filters
├── mcp/          # Application assistant: tailored tex, PDF render, MCP tools
├── fetch/        # In-process country + company fetch
├── scrape/       # ATS boards, merge, enrich
├── web/          # Flask server + routes
├── companies/    # Company CRUD orchestration
├── users/        # Per-user repo, history
├── admin/        # Dashboard aggregates
├── core/         # db helpers, auth, ATS constants, paths
├── db/           # User tracking, fetch runs, migrations
├── schemas/      # Pydantic contracts
├── static/       # UI (JS, CSS; `dist/board.js` from `frontend/`)
└── build_companies.py  # Careers URL discovery CLI
```

Rules: [`docs/reference/rules.md`](docs/reference/rules.md).

### Panel board API

`GET /api/board` returns one page of companies plus metadata. Query params: `page`, `page_size` (max 100, default 25), `country`, `q` (company name search), and the same filter flags as the toolbar (`visa_only`, `hide_applied`, `fetch_problem_only`, etc.). Response includes `companies`, `meta` (`page`, `total_companies`, `total_pages`, `has_more`, …), and lightweight `user_stats`. Pagination is **visible-offset**: the server scans the scoped country catalog, applies flatten + panel filters, skips to the page offset, then fills up to `page_size` rows — so filters affect which companies appear on each page.

**Sort (“Newest first”)** is applied **client-side on the current page only**; the server returns catalog DB order (`country`, `name`). Full flow: [`docs/reference/board.md`](docs/reference/board.md).

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
pytest tests -o addopts=                 # full suite (~166 tests)
pytest tests/mcp tests/web/test_mcp_company_workspace.py -o addopts=   # application assistant
pytest tests/test_route_manifest.py -o addopts=   # fast route check
pytest --cov --cov-report=term-missing   # coverage (90% gate on business modules)
```

Tests use an in-memory Postgres mock — no live ATS or Postgres in CI. Business rules: [`docs/reference/business-rules.md`](docs/reference/business-rules.md).

## Deployment (Render)

`render.yaml` targets Render's **free** web tier. Scraping is disabled in production (`PANEL_SCRAPE_ENABLED=0`).

**Workflow:** scrape locally → push to GitHub → Render redeploys. Runtime state lives in Postgres (AWS EC2).

### One-time setup

1. Ensure AWS Postgres is running and `DATABASE_URL` points to the Elastic IP.
2. Run `./scripts/aws_postgres_migrate.sh sync-sg` so Render can reach port 5432.
3. Push repo to GitHub; in Render: **New → Blueprint** → connect the repo.
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

All contributor docs: **[`docs/README.md`](docs/README.md)**

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
