# Panel board — pagination, sort, and activity timestamps

**Last updated:** 2026-07-02

How the main company board loads, paginates, and sorts by “newest”. Read before changing `panel/`, `static/js/board*.js`, `static/js/render.js`, or `GET /api/board`.

Related: [business-rules.md](business-rules.md) (job buckets), [architecture.md](architecture.md) (panel read path).

---

## Board load path

```
GET /api/board
  → panel/board.load_catalog_board_page()
  → panel/service.flatten_companies_page()
      → catalog/repo.load_catalog_companies_page()   # DB batch, ORDER BY country, name
      → panel/flatten.flatten_company()              # per-user merge + filters
  → web/routes/board.py                              # meta + user_stats
```

Client:

```
board.js (fetch page)
  → board-view.js syncBoardView()
  → render.js getDisplayCompanies()
      → applyPanelFilters()
      → sortCompaniesList()                          # client sort (see below)
  → React company cards (frontend/)
```

Toolbar layout: **pagination → search → sort/filters → company cards**.

---

## “Newest first” sort

Default sort is **Newest first** (`index.html` `#sortSelect`, mirrored by hidden `#sortNewestFetch`). Preference persists in `localStorage` (`panel_sort_newest`).

| Layer | Behavior |
|-------|----------|
| **Server** | When `sort=newest` (default), flattens all filter-visible companies, sorts by activity timestamp, then paginates. |
| **Client** | Sends `sort=newest|name`; for newest, re-sorts the current page by `newest_job_fetched` (frozen during an active fetch). |

Sort key: **max `job.fetched`** per company (`newest_job_fetched`). `company.updated` is not used for sort order.

During an active per-company fetch:

- Order is **frozen** (`freezeCompanyOrder`) so cards do not reshuffle as timestamps update.
- The company being fetched is pinned to the top with an optimistic `updated` / `newest_job_fetched` (`touchFetchingCompanyTimestamp`).

Alternative sort: **Company A–Z** (country label, then name).

### Pagination note

`sort=newest` scans and flattens the full visible catalog for the current scope/filters on each page request, then sorts before slicing. This is correct but heavier than `sort=name` (streaming catalog order). Cursor-based pagination remains a future optimization.

---

## Activity timestamp flow

What “newest” means for a company: **the latest `job.fetched` among open-board roles** (`jobs` bucket). Excludes not-for-me, rejected, and other non-main buckets.

```mermaid
flowchart TD
    C[Scrape jobs merge] --> D{Job new?}
    D -->|yes| E["job.fetched = seen_at"]
    D -->|no, still on board| F["job.fetched preserved; last_seen updated"]
    E --> G["newest_job_fetched = max(job.fetched)"]
    F --> G
    G --> K[API row + server sort]
```

### `company_newest_job_fetched` (server)

`shared/timestamps.py` — used when flattening each company row:

1. **max** of `job.fetched` over the main `jobs` bucket (after per-user partition).
2. Else **`company.added`** when the company has no open roles left.

### Job timestamps (scrape merge)

`scrape/merge.py` on each fetch:

| Field | Meaning |
|-------|---------|
| `fetched` | First time this job was discovered |
| `last_seen` | Last scrape that still saw the job on the ATS |

- **New job:** both set to `seen_at`.
- **Existing job seen again:** `fetched` preserved; `last_seen` updated to `seen_at`.
- **Stale job** (not on ATS this run): kept in catalog; timestamps unchanged.

### API row fields

`panel/flatten.py` `_build_company_row`:

| Field | Source |
|-------|--------|
| `newest_job_fetched` | `max(job.fetched)` over main-board `jobs` only |
| `latest_fetched` | Same as `newest_job_fetched` |
| `updated` | Raw `company.updated` from catalog (fetch metadata only; not used for newest sort) |

After a fetch, a company rises in sort order only when it has a **new or updated `job.fetched`** (typically a newly discovered role).

### When timestamps are written

| Event | What gets set |
|-------|----------------|
| Add company (panel) | `added`, `updated` = today |
| Per-company / country fetch completes | `company.updated` = ISO now |
| Country fetch finishes | `country_meta.last_fetch_new_jobs` = count of new jobs |
| Scrape merge | per-job `fetched` / `last_seen` |

`last_fetch_new_jobs` / `meta.latest_fetch_new_jobs` is a **stats counter** (“new jobs in last country fetch”). It is **not** used for company sort order.

---

## Pagination (visible offset)

`flatten_companies_page` scans the scoped catalog in DB order, applies flatten + panel filters, counts **visible** companies, skips `visible_offset`, returns up to `limit` rows.

- Filters and search affect which companies count toward pages.
- `meta.total_companies` / `total_pages` reflect visible count (computed on page 1).
- Catalog SQL order: `catalog/repo.py` → `ORDER BY c.country, c.name`.

---

## Key files

| Area | File |
|------|------|
| API | `web/routes/board.py` |
| Pagination + flatten | `panel/service.py`, `panel/flatten.py` |
| Timestamps | `shared/timestamps.py` |
| Scrape merge | `scrape/merge.py` |
| Client load | `static/js/board.js` |
| Client sort | `static/js/render.js` |
| Sort UI | `static/js/filters.js`, `static/js/storage.js` |

---

## MCP application flags on jobs

When a user is logged in, `GET /api/board` merges per-position MCP state from `mcp_applications` into each job row:

| Field | Meaning |
|-------|---------|
| `has_tailored_tex` | Tailored LaTeX saved for this position |
| `has_pdf` | Compiled PDF stored |
| `master_resume_slug` | Master variant used (e.g. `go`, `java`) |

Company name on the board links to the application workspace at `/company/<country>/<company-slug>`. See [company-workspace.md](company-workspace.md).
