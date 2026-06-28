# Panel statistics

**Last updated:** 2026-06-28

How admin/user stats are computed. Implementation: `panel/stats.py`, `static/js/stats-dashboard.js`.

> Stats are not yet a dedicated domain module — they are derived at read time from flattened catalog + tracking + `fetch_runs`. A future `stats/` package should own these queries.

---

## Admin dashboard (`GET /api/admin/panel-stats`)

Per-user totals over the **full catalog** (not the current board page). Uses `flatten_companies()` + `compute_stats()`.

| Stat | Meaning |
|------|---------|
| **Open roles** | Main-board jobs you can still act on: in the `jobs` bucket, **not applied**. Excludes not-for-me, rejected, and applied. |
| **Companies** | Companies with at least one open role. |
| **New today** | Sum of `fetch_runs.new_jobs` for your account finished **today** (browser timezone). True new discoveries only — not jobs re-enriched on an existing fetch. |

**Job dates:** `fetched` = first time the job entered the catalog; `last_seen` = last ATS scrape. Post-fetch visa enrich must **never** overwrite `fetched` (see `scrape/enrich.py`). If many cards show today's date incorrectly, run `python scripts/repair_job_fetched_dates.py --dry-run` then without `--dry-run`.
| **Last fetch** | Latest company activity timestamp in scope. |
| **Applied today / total** | From `job_tracking` + status history. |
| **Rejections** | Jobs in the `rejected_jobs` bucket. |
| **Visa / relocation** | Open roles with `visa_sponsorship=true`. |
| **Fetch issues** | Companies with `fetch_problem` in catalog. |

**Not shown:** hidden/not-for-me count (removed from UI — those roles are not open).

---

## Overview block (admin dashboard top row)

Separate from panel stats. **Catalog roles** = raw `matching_jobs` row count in Postgres (all users, no tracking overlay). Use panel stats for your actionable numbers.

---

## Board header chip

`GET /api/board` returns lightweight `user_stats`; `latest_fetch_new_jobs` uses the same **New today** logic via `fetch_runs`.

---

## Legacy field

`country_meta.last_fetch_new_jobs` is updated only on country-wide fetch completion. **Do not use** for UI stats — kept for catalog metadata only.
