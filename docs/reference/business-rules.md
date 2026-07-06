# Core business rules

Plain-language contracts extracted from the code (`catalog_service`, `db`, `catalog_db`, `scrape_jobs`, `location_tags`). Use these for tests, refactors, and bug investigations — not as marketing copy.

## Data ownership

1. **Catalog vs tracking** — Company/job listings live in the catalog DB. Per-user state (applied, rejected, not-for-me, etc.) lives in the user DB. The panel merges both at read time when a user is logged in; the catalog alone is used when no `user_id` is passed.

2. **Scrape never deletes roles** — A re-scrape merges by job idempotency key: new roles are added, existing roles keep their first `fetched` date and title/visa updates, and roles missing from the latest scrape stay in the catalog. Scraping adds; it does not remove. Listing location metadata is still copied from the latest ATS board onto every cached role (including stale kept and location-gate exclusions).

3. **Tracking survives re-scrape** — User flags are stored in the DB, not in the catalog JSON. Updating catalog job titles via scrape must not clear applied/rejected/etc. on the panel; read path overlays DB state onto catalog jobs.

## Job identity

4. **One role, one key** — The same posting is identified by an idempotency key (hash of normalized URL). Tracking matches across URL variants (e.g. `www`, extra query params) when resolving state for a catalog job.

## Position state (writes)

5. **Apply** — Marking a job applied sets DB `applied`, clears `looking_to_apply`, appends an apply event to history, syncs company-level `company_applied` from any applied position at that company, and sets company `awaiting_response` (keeping an existing awaiting date if already set). **Applied today** counts distinct apply events whose `created_at` falls in the user's local calendar day (browser timezone); touching an already-applied row (seen, ATS score, etc.) does not increment the stat.

6. **Unapply** — Clearing applied on a job updates DB and re-syncs `company_applied` (false when no positions at that company remain applied). It does not automatically clear `awaiting_response`.

7. **Reject and reapply** — Rejecting moves a job to the `rejected_jobs` list on read; it does not clear applied. Reapply clears rejection only and returns the job to the main `jobs` list.

8. **Not for me** — Marks the job hidden from main and rejected reinjection paths; it appears only under `not_for_me_jobs`. Orphan reinjection skips not-for-me rows. Hide reasons stored on `job_tracking.not_for_me_reason` include `not_for_me`, `expired` (posting closed — human review), `wrong_location`, and `no_relocation`.

9. **Waiting for referral** — Requires a LinkedIn URL when enabled; stored on the tracking row. Independent of applied/rejected buckets unless filters say otherwise.

## Position state (reads / panel layout)

10. **Three job buckets** — On read, each role lands in exactly one primary bucket: `jobs` (active board), `rejected_jobs`, or `not_for_me_jobs`. Rejected catalog jobs never appear in `jobs` even if other flags are set.

11. **Orphan tracked roles** — If a job disappears from the catalog but the user still has applied, rejected, or looking-to-apply tracking, the panel reinjects it from the DB (into `jobs` or `rejected_jobs`). Not-for-me orphans are not reinjected.

12. **Company applied is derived** — On panel read, `company_applied` is derived from applied **positions** in job tracking (including orphans not currently in the catalog). Manual `set_company_applied` writes company_tracking but does not flip `company_applied` on read until at least one position is marked applied.

## Filters (panel)

13. **Company vs position filters** — `hide_applied` drops entire companies that have any applied activity (derived from positions). `hide_position_applied` hides only applied rows in the main `jobs` list. `position_rejected_only` shows companies that have rejected jobs (main `jobs` may be empty). Rejected rows are routed to `rejected_jobs` before position filters, so `hide_position_rejected` does not empty that bucket.

14. **Other list filters** — `visa_only` drops jobs without `visa_sponsorship === true`. `hide_empty` drops companies with no open roles in the main `jobs` list (not-for-me and rejected buckets do not keep a company visible unless `position_rejected_only` is active). `not_applied_only` drops companies already applied at company level or with no visible jobs.

## Scrape / relevance (what enters the catalog)

15. **Backend relevance** — Scrapers only keep titles that pass keyword include/exclude rules (e.g. backend/software engineer in, CTO/marketing-manager-style roles out). This gate applies before jobs are stored as `matching_jobs`.

16. **Location gate** — When a company has tagged locations, scraped listings must match those countries/cities (or valid remote rules) or they are excluded from merge into new board rows. Listings with **no usable location metadata** stay on the main board (benefit of the doubt). On panel read, roles with a **known wrong** location are routed to **Not for me** with reason **Wrong location**.

---

**Not specified in code (investigate before changing UX):** interactions like applied + rejected simultaneously, not-for-me then apply, and whether unapply should clear `awaiting_response`. Current behavior follows DB writes + read overlay above; product intent for edge combos is implicit.

---

## Test mapping

| Rules | Test file |
|-------|-----------|
| 1–14, state workflows | `tests/test_job_state_rules.py` |
| 1–16 + API round-trip | `tests/test_business_rules_coverage.py` |
| DB writes / history | `tests/test_db_full.py`, `tests/test_applied_today.py` |
| Panel API | `tests/test_panel_api_full.py` |
| Panel data / CRUD | `tests/test_catalog_service.py` |
| Scrapers / relevance | `tests/test_scrape_*.py` (run `pytest -m scrape`) |
| Location gate | `tests/test_location_tags*.py` |
| Custom picker cities (`POST /api/locations`, `data/custom_cities.json`) | `tests/test_location_tags_full.py`, `tests/test_catalog_service.py`, `tests/test_panel_api_full.py` |

Run business-rule tests only:

```bash
pytest tests/test_job_state_rules.py tests/test_business_rules_coverage.py -v
```

Run scraper tests (not included in default `pytest`):

```bash
pytest -m scrape -v
```
