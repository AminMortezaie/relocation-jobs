# Job Scraper — Multi-Country Backend Job Search

Scrapes jobs from tech companies across multiple countries that offer visa/relocation sponsorship. Sources company lists from [relocate.me](https://relocate.me), auto-detects each company's ATS (Applicant Tracking System), and filters for backend/software engineering roles.

---

## Architecture Overview

```
relocate.me (country page)
    ↓
build_companies.py         ← Step 1: build {country}_companies.json
    ↓  visits each company's website, finds careers URL
{country}_companies.json   ← cached: name, city, size, careers_url, ats_type, ats_url
    ↓
scrape_jobs.py             ← Step 2: detect ATS, scrape jobs
    ↓  on first run: auto-detects ATS via Playwright XHR interception
    ↓  on subsequent runs: uses cached ats_type + ats_url (fast REST API)
{country}_companies.json   ← output: matching_jobs appended per company
```

### ATS Detection Flow (per company, first run only)

```
careers_url
    ↓
1. KNOWN_ATS override?        → use hardcoded slug (companies that block bots or use unusual embeds)
    ↓ no
2. detect_ats_static()        → fast HTTP fetch, regex search HTML for known ATS patterns
    ↓ no match
3. detect_ats_via_playwright() → headless browser, intercept XHR/fetch calls
    ↓ no match
4. "generic" fallback          → parse page HTML / Playwright DOM for job links
```

Detected `ats_type` and `ats_url` are written back to the JSON — subsequent runs skip detection entirely.

### Supported ATS Platforms

| ATS | Detection | Scraping |
|-----|-----------|----------|
| Greenhouse (US) | XHR + HTML `boards.greenhouse.io` | REST API `boards-api.greenhouse.io/v1/boards/{slug}/jobs` |
| Greenhouse (EU) | XHR + HTML `boards.eu.greenhouse.io` | REST API `boards-api.eu.greenhouse.io/v1/boards/{slug}/jobs` |
| Lever (US) | XHR `api.lever.co` | REST API `api.lever.co/v0/postings/{slug}?mode=json` |
| Lever (EU) | XHR `jobs.eu.lever.co` | REST API `jobs.eu.lever.co/v0/postings/{slug}?mode=json` |
| Ashby | XHR `api.ashbyhq.com` | REST API `api.ashbyhq.com/posting-api/job-board/{slug}` |
| Personio | XHR `*.jobs.personio.de` | XML feed `{base}/xml` |
| Workable | XHR `apply.workable.com` | REST API `apply.workable.com/api/v2/accounts/{slug}/jobs` |
| Recruitee | XHR `*.recruitee.com` | REST API `{slug}.recruitee.com/api/offers/` |
| SmartRecruiters | XHR `api.smartrecruiters.com` | REST API `api.smartrecruiters.com/v1/companies/{id}/postings` |
| TeamTailor | XHR `api.teamtailor.com` (captures API key) | REST API with intercepted key |
| Generic | — | Playwright DOM parse for job links |

---

## Project layout

```
resume/
├── companies/              # Git-tracked company + job JSON (deploy bundle)
├── data/                   # Local runtime cache + panel.db (gitignored)
├── relocation_jobs/        # Python package (panel, scraper, auth, DB)
│   ├── panel_server.py
│   ├── panel_data.py
│   ├── scrape_jobs.py
│   ├── build_companies.py
│   ├── paths.py
│   └── static/             # Panel UI (HTML, CSS, JS modules)
├── scripts/                # Thin CLI entry points
│   ├── panel_server.py
│   ├── scrape_jobs.py
│   ├── build_companies.py
│   └── reset_password.py
├── Dockerfile
├── render.yaml
└── requirements.txt
```

Run commands from the repo root (either form works):

```bash
python3 scripts/panel_server.py
# or: python3 -m relocation_jobs.panel_server
```

---

## Setup

```bash
pip install -r requirements.txt   # includes httpx for async scraping
python3 -m playwright install chromium
```

---

## Job panel (web UI)

View cached matching jobs (newest first) and trigger a new scrape from the browser.

```bash
python3 scripts/panel_server.py
# open http://127.0.0.1:5050
```

**Authentication:** the panel requires sign-in. On first run, an admin user is created from `PANEL_ADMIN_USER` / `PANEL_ADMIN_PASSWORD` (see `.env.example`). If no password is set, a random one is printed to the terminal.

**Storage split:**
- `companies/{country}_companies.json` — scrape cache in git (companies, careers URLs, matching jobs). At runtime the panel reads/writes under `data/` (or `PANEL_DATA_DIR` on Render); bundled copies in `companies/` are seeded on first start.
- `data/panel.db` (SQLite) — users and per-user tracking (`applied`, `not_for_me`, company applied)

Tracking is stored in the database per user. The panel also mirrors tracking fields into JSON so re-scrapes keep stale applied/hidden jobs.

---

## Deploy on Render (free plan)

`render.yaml` targets Render’s **free** web tier — no paid disk required.

### How data persists on free

| Data | Where it lives |
|------|----------------|
| Login + applied / not-for-me | **Neon Postgres** (`DATABASE_URL`) — free tier |
| Job listings JSON | **Git repo** → baked into each deploy |

Render free has **no persistent disk** and **512MB RAM**, so in-browser scraping is **disabled** (`PANEL_SCRAPE_ENABLED=0`). Scrape on your Mac, commit the JSON files, push to GitHub, and Render redeploys with the updated jobs.

### Setup (one time)

1. **[Neon](https://neon.tech)** → create project → copy the Postgres connection string.
2. Push this repo to **GitHub**.
3. **[Render](https://render.com)** → **New** → **Blueprint** → connect the repo.
4. In Render env vars, set:
   - **`DATABASE_URL`** — Neon connection string (required on free)
   - **`PANEL_ADMIN_PASSWORD`** — your login password
5. Deploy → open `https://<your-service>.onrender.com`.

Sign in with `admin` + your password. Free URL included (`*.onrender.com`).

### Day-to-day workflow

```bash
# On your Mac — update jobs
python3 scripts/scrape_jobs.py --file uk_companies.json
git add companies/*.json && git commit -m "update jobs" && git push
# Render auto-redeploys (or trigger manual deploy)
```

Applied / not-for-me marks are stored in Neon and survive restarts.

### Env vars

| Variable | Free-plan value |
|----------|-----------------|
| `DATABASE_URL` | Neon Postgres URL (**required**) |
| `PANEL_DATA_DIR` | `/tmp/panel-data` (ephemeral; set by `render.yaml`) |
| `PANEL_SCRAPE_ENABLED` | `0` |
| `PANEL_ADMIN_PASSWORD` | your password |
| `PANEL_SECRET_KEY` | auto-generated |

To enable scraping on a paid Render plan with more RAM, set `PANEL_SCRAPE_ENABLED=1` and add a persistent disk.

### Local Docker test

```bash
docker build -t relocation-jobs .
docker run --rm -p 8080:10000 \
  -e PORT=10000 \
  -e PANEL_ADMIN_PASSWORD=changeme123 \
  -e DATABASE_URL="postgresql://..." \
  relocation-jobs
```

---

- **Country filter** — Netherlands, Germany, UK, Portugal, or all
- **Fetch new jobs** — runs `scrape_jobs.py --file {country}_companies.json --workers N` (asyncio, default 16 parallel companies); adjust **Parallel** in the toolbar; live log at the bottom
- **Fetch jobs** (per company) — on each company card, scrapes only that employer (`scrape_jobs.py --file … "Company Name"`); one fetch at a time
- **Skip companies that already have jobs** — passes `--skip-filled` to the scraper
- **Add company** — enter name + careers page URL; country is **auto-detected** (relocate.me office locations, then URL region e.g. `.de` / `.co.uk`) and the company is saved to the matching `{country}_companies.json`. Override country in the form if detection fails. ATS, city, and size are filled automatically.
- **Grouped by company** — one card per employer; all matching roles listed underneath.
- **Applied to company** — company-level checkbox; saved per user in the database (mirrored to JSON for scrape merge). Counted in **Applied companies** stat. **Hide applied companies** removes those employers from the list (all roles hidden).
- **This position** — per-job checkbox; saved per user in the database (`applied` / `applied_date`). Shown in **Positions marked** stat; independent of company-level applied.
- **Not for me** — per-job button; saved per user in the database (`not_for_me` / `not_for_me_date`) and hides the role permanently (survives re-fetch).

**Re-fetch preserves your tracking:** when you run the scraper again (panel or CLI), existing jobs are **merged** by URL — not replaced wholesale. For jobs already in the JSON:
- `fetched` date is kept (not reset to today)
- `applied` / `applied_date` are kept
- `not_for_me` / `not_for_me_date` are kept (hidden roles stay hidden)
- Jobs you marked applied but that left the careers page stay in the list (“off-board kept”)
- Only genuinely new postings get a new `fetched` date

Use `--skip-filled` to skip entire companies that already have jobs (no scrape at all for that company).
- **Visa / relocation only** — show jobs where `visa_sponsorship` is true
- **Search** — filter by title or company name

Select a single country before fetching (not “All countries”). Use **Refresh** to reload JSON without re-scraping.

---

## Files

| Path | Purpose |
|------|---------|
| `relocation_jobs/panel_server.py` | Web dashboard — list jobs + start scrapes |
| `relocation_jobs/panel_data.py` | Loads companies + nested jobs from country JSON files |
| `relocation_jobs/auth.py` | Session login, registration, bootstrap admin |
| `relocation_jobs/db.py` | SQLite / Postgres — users + per-user tracking |
| `relocation_jobs/static/` | Dashboard UI (HTML, CSS, JS modules) |
| `relocation_jobs/scrape_jobs.py` | Main scraper — ATS detection + job fetching |
| `relocation_jobs/build_companies.py` | Builds & sorts company lists — discovers careers URLs |
| `companies/*.json` | Country company lists (cached ATS data + matching jobs) |
| `scripts/` | CLI wrappers (`panel_server`, `scrape_jobs`, `build_companies`, `reset_password`) |

---

## Step-by-Step: Adding a New Country

### Step 1 — Build the company list

This visits each company's website to find their careers page URL, then sorts the list and writes back to the JSON file.

```bash
python3 scripts/build_companies.py netherlands
python3 scripts/build_companies.py uk

# Single company only
python3 scripts/build_companies.py uk "Monzo"

# Skip careers discovery, just re-sort an existing file
python3 scripts/build_companies.py netherlands --sort-only
```

What it does per company:
1. Fetches the relocate.me company page — if it links directly to a jobs subdomain (e.g. `jobs.blablacar.com`), that wins.
2. Fetches the company's homepage, scans nav/footer links for text matching `career|job|vacanc|opening|hiring|join|karriere|stellen`.
3. Probes common paths: `/careers`, `/jobs`, `/careers/`, `/jobs/`, `/work-with-us`, `/join-us`, `/en/careers`, `/karriere`, `/vacancies`.
4. Prefers ATS hosts: `greenhouse.io`, `lever.co`, `ashbyhq`, `personio`, `workable.com`, `recruitee`, `smartrecruiters`, `teamtailor`.
5. Falls back to Playwright for JS-rendered homepages — the headless browser also clicks CTA buttons such as **"Open positions"**, **"View jobs"**, **"See all roles"**, **"Browse jobs"**, **"Current openings"** and captures whatever page they lead to.
6. Writes the highest-scoring URL back to `{country}_companies.json`.

#### Sort order

After discovery, every company list is re-sorted with this order:

1. **City** (A–Z) — companies in the same city stay together.
2. **Company size** — smallest range first, using the lower bound: `2–10` → `11–50` → `51–200` → `201–500` → `501–1,000` → `1,001–5,000` → `10,001+`.
3. **Company name** (A–Z) — for ties on city + size.

> Example: in **London**, `bloop` (`11–50`) comes before `BlaBlaCar` (`501–1,000`), even though they share the same city — smaller bucket first.

Output: `netherlands_companies.json` / `uk_companies.json` with `careers_url` filled in and the list sorted.

#### When auto-discovery picks the wrong URL

Some careers pages can only be reached through a click-through on the company's main site:

- The homepage has a CTA button such as **"Open positions"**, **"See open roles"**, **"View jobs"**, or **"Join us"** that opens the real careers page (often on a different domain or an ATS embed).
- Other companies hide the careers page behind a `/about` or `/company` section, then route through another button on that page.
- A few companies have been acquired and their careers now live on the acquirer's site (e.g. **Mobica** → Cognizant, **Inverid** → Signicat, **Textkernel** → Bullhorn).
- Some `/careers` paths redirect to the homepage when the bot's User-Agent is rejected (e.g. **Catawiki**, **Creative Fabrica**). Confirm with a real browser, then patch the JSON manually.

If the discovered URL is clearly wrong, open the company's homepage in a real browser, follow the **Open positions** / **Careers** button to the real listing page, copy that URL, and either:

- Edit `careers_url` directly in `{country}_companies.json`, then re-run `python3 scripts/build_companies.py <country> --sort-only`, or
- Add a manual override to `KNOWN_ATS` in `scrape_jobs.py` if the page uses a non-obvious ATS embed.

### Step 2 — Scrape jobs

```bash
# Full run — all companies in the country file
python3 scripts/scrape_jobs.py --file netherlands_companies.json

# Single company
python3 scripts/scrape_jobs.py --file netherlands_companies.json "Adyen"

# Skip companies that already have jobs cached
python3 scripts/scrape_jobs.py --file netherlands_companies.json --skip-filled
```

On first run: Playwright launches for each company without a cached ATS, detects it, writes `ats_type` + `ats_url` to JSON.
On subsequent runs: skips detection, calls the ATS REST API directly (fast, no browser needed).

**Concurrent scraping** (default): uses an **asyncio event loop** + **httpx** for I/O-bound ATS API calls (not multiprocessing or a thread per company). Companies run in parallel up to `--workers 16` (meaning concurrent tasks, not OS threads). Playwright (ATS detection / generic fallback) still runs in a small thread pool because the sync Playwright API blocks. Visa enrichment runs concurrently on the same loop.

```bash
pip install httpx   # required for async mode
python3 scripts/scrape_jobs.py --file netherlands_companies.json --workers 16
python3 scripts/scrape_jobs.py --file netherlands_companies.json --serial   # one company at a time
```

### Step 3 — Fix companies that returned 0 jobs

If a company shows 0 jobs but their careers page clearly has openings:

1. **Delete the cached ATS** from the JSON and re-run:
   ```bash
   # Edit the JSON: remove "ats_type" and "ats_url" for that company
   python3 scripts/scrape_jobs.py --file netherlands_companies.json "CompanyName"
   ```

2. **Add to `KNOWN_ATS`** if auto-detection keeps failing (bot blocks, unusual embed):
   ```python
   # In scrape_jobs.py, add to KNOWN_ATS dict:
   KNOWN_ATS: dict[str, tuple[str, str]] = {
       ...
       "CompanyName": ("greenhouse", "https://boards.greenhouse.io/companyslug"),
   }
   ```
   Common reasons to use KNOWN_ATS:
   - Careers page returns 403 for bots (e.g., HelloFresh)
   - Uses Lever WP plugin with no API calls (e.g., adjoe → parent company slug)
   - Recruitee routes through `careers-analytics.recruitee.com` proxy (returns real API slug needed)
   - Greenhouse embed uses `?for=slug` parameter hard to intercept (e.g., Talon.One)
   - Ashby widget rendered server-side by Next.js (no interceptable API calls)

---

## Job Filtering

Jobs are included if the title matches an **include keyword** AND does not match any **exclude keyword** (case-insensitive).

### Include Keywords
```
backend, back-end, back end
software engineer, software developer
platform engineer, platform developer
infrastructure engineer
golang, go engineer, go developer, go backend
java, kotlin, spring boot
microservice, distributed
fullstack, full-stack, full stack
senior engineer
```

### Exclude Keywords
```
frontend, front-end, android, ios, mobile
designer, design, marketing, sales
account manager, account executive
data scientist, data analyst, machine learning engineer
product manager, product owner
recruiter, hr, human resource, talent acquisition
accounting, legal, customer success/support/service
office manager, executive assistant, content, copywriter, seo
game designer, game artist, level designer, 3d artist, animator, concept artist
vp of, head of, director of, chief
internship, intern, staff, lead
engineering manager, principal
junior, devops, dev ops, site reliability, sre
```

To adjust filtering, edit `INCLUDE_KEYWORDS` / `EXCLUDE_KEYWORDS` in `scrape_jobs.py`.

---

## Company Lists

### Germany (74 companies)
Source: https://relocate.me/companies-hiring/germany
File: `germany_companies.json`

ATS breakdown (approximate after full run):
- Greenhouse/Greenhouse EU: ~20 companies
- Lever/Lever EU: ~15 companies
- Personio: ~10 companies
- Ashby: ~8 companies
- Workable: ~5 companies
- Recruitee: ~5 companies
- SmartRecruiters: ~3 companies
- TeamTailor: ~3 companies
- Generic: rest

Known manual corrections (`KNOWN_ATS`):
| Company | ATS | Reason |
|---------|-----|--------|
| SimScale | greenhouse | embed page doesn't make API calls |
| HelloFresh | greenhouse | careers.hellofresh.com blocks bots |
| Talon.One | greenhouse_eu | `?for=talonone` embed, hard to intercept |
| adjoe | lever | Lever WP plugin, real slug is parent company `applike` |
| Instapro Group | recruitee | routes through `careers-analytics` proxy |
| Limehome | recruitee | routes through `careers-analytics` proxy |

Known issues:
- **Taxfix**: Uses Ashby but widget is SSR-rendered by Next.js — no API calls interceptable. Org slug unknown. Currently falls through to generic scraper.

### Netherlands (44 companies)
Source: https://relocate.me/companies-hiring/netherlands
File: `netherlands_companies.json`

Sorted by city → size → name (see *Sort order* above).

| Company | City | Size | Careers URL |
|---------|------|------|-------------|
| C Teleport | Amsterdam | 11-50 | https://cteleport.com/careers/ |
| Ravecruitment | Amsterdam | 11-50 | https://www.ravecruitment.com |
| ZooStation | Amsterdam | 11-50 | https://yourexpats.nl/over-ons/#vacancies |
| Creative Fabrica | Amsterdam | 51-200 | https://careers.creativefabrica.com/ |
| Fashion Cloud | Amsterdam | 51-200 | https://www.fashion.cloud/career/work-with-us |
| GreenFlux | Amsterdam | 51-200 | https://www.greenflux.eu/jobs |
| Insify | Amsterdam | 51-200 | https://careers.insify.nl/ |
| Inverid | Amsterdam | 51-200 | https://www.signicat.com/about/careers |
| Online Payment Platform | Amsterdam | 51-200 | https://jobs.onlinepaymentplatform.com/ |
| Quin | Amsterdam | 51-200 | https://www.quin.md |
| Realworks | Amsterdam | 51-200 | https://jobs.realworks.nl/ |
| Recharge | Amsterdam | 51-200 | https://getrecharge.com/careers/ |
| Sam Media | Amsterdam | 51-200 | https://www.sammedia.com |
| SkillLab | Amsterdam | 51-200 | https://skilllab.io/en-us/company/jobs |
| Stream | Amsterdam | 51-200 | https://getstream.io/team/ |
| Textkernel | Amsterdam | 51-200 | https://careers.bullhorn.com/ |
| Vio.com | Amsterdam | 51-200 | https://www.vio.com/careers |
| Guerrilla | Amsterdam | 201-500 | https://www.guerrilla-games.com/join |
| LeaseWeb | Amsterdam | 201-500 | https://www.leaseweb.com/en/about-us/career |
| Storyteq | Amsterdam | 201-500 | https://apply.workable.com/storyteq/ |
| Swisscom | Amsterdam | 201-500 | https://www.swisscom.ch/jobs/ |
| Tiqets | Amsterdam | 201-500 | https://jobs.tiqets.work/ |
| Catawiki | Amsterdam | 501-1,000 | https://www.catawiki.com |
| Crytek | Amsterdam | 501-1,000 | https://www.crytek.com/career |
| Mollie | Amsterdam | 501-1,000 | https://jobs.mollie.com |
| Optiver | Amsterdam | 501-1,000 | https://optiver.com/working-at-optiver/career-hub/ |
| Reaktor | Amsterdam | 501-1,000 | https://www.reaktor.com/careers |
| Adyen | Amsterdam | 1,001-5,000 | https://careers.adyen.com |
| Personio | Amsterdam | 1,001-5,000 | https://www.personio.com/about-personio/careers/ |
| Picnic | Amsterdam | 1,001-5,000 | https://jobs.picnic.app/nl/ |
| TomTom | Amsterdam | 1,001-5,000 | https://www.tomtom.com/careers/ |
| Booking.com | Amsterdam | 10,001+ | https://careers.booking.com |
| EPAM | Amsterdam | 10,001+ | https://careers.epam.com/ |
| The Exploration Company | Bordeaux/Amsterdam | 51-200 | https://www.exploration.space/careers |
| Profitap | Eindhoven | 11-50 | https://jobs.profitap.com/ |
| TOPIC Embedded Systems | Eindhoven | 51-200 | https://werkenbijtopic.nl/ |
| Topic Software Development | Eindhoven | 51-200 | https://werkenbijtopic.nl/ |
| NXP | Eindhoven | 10,001+ | https://nxp.wd3.myworkdayjobs.com/careers |
| Protolabs | Rhône-Alpes | 1,001-5,000 | https://www.protolabs.com/about-us/careers/ |
| Housing Anywhere | Rotterdam | 51-200 | https://housinganywhere.com/careers |
| Coolblue | Rotterdam | 1,001-5,000 | https://www.coolblue.nl/en/vacancies |
| bol | Utrecht | 1,001-5,000 | https://careers.bol.com/nl/ |
| LINKIT | Veenendaal | 51-200 | https://careers.linkit.nl |
| Jumbo | Veghel | 10,001+ | https://nl.jobs.jumbo.com/en/jumbo-as-an-employer/ |

Manual fixes applied after auto-discovery:
- **bol** → `careers.bol.com/nl/` (homepage doesn't link to careers)
- **Catawiki**, **Creative Fabrica**, **Sam Media** → bot-blocked, kept best discovered URL
- **Inverid** → acquired by **Signicat**; careers go through `signicat.com/about/careers`
- **NXP** → uses Workday at `nxp.wd3.myworkdayjobs.com`
- **Personio** → reach via **Open positions** on the careers landing page
- **Textkernel** → acquired by **Bullhorn**; careers live at `careers.bullhorn.com`
- **TOPIC Embedded Systems** / **Topic Software Development** → reach via *Werken bij TOPIC* button → `werkenbijtopic.nl`
- **The Exploration Company** → uses `exploration.space` domain, not `theexplorationcompany.space`
- **ZooStation** → hiring handled by **YourExpats**, careers anchor at `yourexpats.nl/over-ons/#vacancies`

### United Kingdom (20 companies)
Source: https://relocate.me/companies-hiring/united-kingdom
File: `uk_companies.json`

Sorted by city → size → name (see *Sort order* above).

| Company | City | Size | Careers URL |
|---------|------|------|-------------|
| Splash Damage | Bromley | 201-500 | https://careers.splashdamage.com/ |
| Frontier Developments | Cambridge | 201-500 | https://www.frontier.co.uk/careers |
| Orbex | Forres | 11-50 | https://orbex.space/careers/ |
| Creative Assembly | Horsham | 501-1,000 | https://www.creative-assembly.com/jobs |
| bloop | London | 11-50 | https://bloop.ai |
| GetGround | London | 51-200 | https://www.getground.co.uk/jobs |
| LIQUiDITY Group | London | 51-200 | https://www.liquidity.com/careers |
| Noon | London | 51-200 | https://careers.learnatnoon.com/ |
| Wayve | London | 51-200 | https://wayve.ai/careers/ |
| Wintermute | London | 51-200 | https://www.wintermute.com/company/careers |
| Grand Parade | London | 201-500 | https://grandparade.co.uk/ |
| BlaBlaCar | London | 501-1,000 | https://jobs.blablacar.com/ |
| Deliveroo | London | 1,001-5,000 | https://careers.deliveroo.co.uk |
| Monzo | London | 1,001-5,000 | https://monzo.com/careers |
| Personio | London | 1,001-5,000 | https://www.personio.com/about-personio/careers/ |
| SumUp | London | 1,001-5,000 | https://www.sumup.com/careers/ |
| Wise | London | 1,001-5,000 | https://wise.jobs/ |
| SKA Observatory | Macclesfield | 51-200 | https://www.skao.int/en/opportunities/careers-opportunities |
| Mobica | Manchester | 1,001-5,000 | https://careers.cognizant.com/emea-en |
| Oxa | Oxford | 201-500 | https://oxa.tech/careers/ |

Manual fixes applied after auto-discovery:
- **bloop** → no public careers page; homepage `bloop.ai` is the canonical link
- **Grand Parade** → real domain is `grandparade.co.uk` (not .com); careers are reached from the homepage CTA
- **LIQUiDITY Group** → rebranded to `liquidity.com`, careers at `/careers`
- **Mobica** → acquired by **Cognizant**; hiring goes through `careers.cognizant.com/emea-en`
- **Noon** → real domain is `learnatnoon.com`; careers at `careers.learnatnoon.com`
- **Oxa** → real domain is `oxa.tech` (the relocate.me listing's `oxa.ai` is outdated)
- **Personio** → reach via **Open positions** on the careers landing page

---

## Troubleshooting

### Company returns 0 jobs but has openings

1. Check the `ats_type` and `ats_url` in the JSON — they may point to a wrong slug.
2. Visit the careers URL manually and look at Network tab in DevTools to find the ATS API call.
3. Add to `KNOWN_ATS` with the correct slug.

### Playwright detection hangs or times out

- Some pages load very slowly. The timeout is 25 seconds with an extra 3.5 second wait.
- If a company's careers page requires login/cookie consent, detection may fail — add to `KNOWN_ATS` manually.

### ATS returns 401 / 403

- The ATS endpoint requires auth or has bot protection.
- For Greenhouse, try both US and EU variants.
- For Recruitee, check if it routes through `careers-analytics.recruitee.com` (proxy) — the real slug is needed.

### New company added to relocate.me

Just add an entry to the JSON with `name`, `city`, `careers_url` and no `ats_type`. Run:
```bash
python3 scripts/scrape_jobs.py --file {country}_companies.json "New Company Name"
```
ATS will be auto-detected and cached.

---

## Running Everything

```bash
# Germany (already set up, just re-scrape)
python3 scripts/scrape_jobs.py

# Netherlands — first time
python3 scripts/build_companies.py netherlands
python3 scripts/scrape_jobs.py --file netherlands_companies.json

# UK — first time
python3 scripts/build_companies.py uk
python3 scripts/scrape_jobs.py --file uk_companies.json

# Single company across any file
python3 scripts/scrape_jobs.py --file netherlands_companies.json "Adyen"
python3 scripts/scrape_jobs.py --file uk_companies.json "Monzo"

# Skip companies already scraped (useful for re-runs after partial failures)
python3 scripts/scrape_jobs.py --file netherlands_companies.json --skip-filled
```
