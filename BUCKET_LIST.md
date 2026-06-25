# Application bucket list

Living backlog of planned work. Add items as we discover them; check off when shipped.

---

## Not-for-me soft delete (wrong location + user hides)

**Status:** planned  
**Priority:** medium  
**Context:** Rule 16 routes known wrong-location roles to the not-for-me bucket at panel read time. User-initiated “not for me” writes `job_tracking.not_for_me`. Wrong-location hides were read-time only until the one-shot `scripts/mark_wrong_location_jobs.py` backfill.

### Problem today

| Path | Persisted? | Where it lives |
|------|------------|----------------|
| User clicks “Not for me” / hide reason | Yes | `job_tracking.not_for_me`, `not_for_me_reason`, `not_for_me_date` |
| Wrong location (office tag mismatch) | Read-time only (pre-backfill) | `partition_stored_jobs` + `job_fails_office_location_gate` |
| Catalog scrape exclusion | Catalog row only | `tag_wrong_location_jobs` on merge (not per-user) |

Soft delete means every hide that affects the board should have a durable `job_tracking` row so:

- Re-reads do not depend on recomputing location gates.
- `reconcile_wrong_location_hides` can restore rows when office tags change.
- Local board updates (`job-board.js`) and full reloads stay consistent.
- Orphan reinjection rules stay correct (not-for-me orphans are skipped).

### Refactor scenario (target design)

1. **Write path — persist on hide**
   - `set_job_not_for_me` (already correct for user actions).
   - New `apply_wrong_location_hides(user_id, *, country_key=None)` in `positions/service.py`:
     - Scan catalog jobs (all countries or scoped).
     - Use same gate as panel: `job_fails_office_location_gate`.
     - Skip rows already `not_for_me` with a user-chosen reason (`not_for_me`, `no_relocation`, etc.).
     - `INSERT … ON CONFLICT` with `not_for_me=1`, `not_for_me_reason='wrong_location'`.
   - Inverse already exists: `reconcile_wrong_location_hides` clears wrong-location hides when tags expand.

2. **Read path — tracking wins**
   - Keep `derive_bucket`: `not_for_me` **or** computed `wrong_location` → `not_for_me_jobs`.
   - After backfill, computed `wrong_location` becomes a safety net for jobs not yet scanned.
   - Optional later: drop read-time `wrong_location` flag once apply runs on every catalog change.

3. **When to run apply**
   - After country fetch completes (per country, per active user or lazy on next board load).
   - After `update_company_city` / location tag edits (pair with existing `reconcile_wrong_location_hides`).
   - Admin action: “Re-scan wrong locations” (whole DB).
   - **Not** on every `GET /api/board` page — too heavy over remote Postgres.

4. **Client**
   - `markWrongLocation` API already calls `setNotForMe(…, "wrong_location")` — no change.
   - `patchJobOnBoard` should move job to `not_for_me_jobs` with reason (already does for manual hide).

5. **Tests to add**
   - `apply_wrong_location_hides` marks failing jobs, skips user hides with other reasons.
   - `reconcile_wrong_location_hides` still restores when city added.
   - Board flatten: persisted wrong-location row lands in `not_for_me_jobs`, not `jobs`.
   - Idempotent: second apply is a no-op.

6. **Migration / ops**
   - One-shot: `python scripts/mark_wrong_location_jobs.py` (all users).
   - Dry run: `python scripts/mark_wrong_location_jobs.py --dry-run`.
   - Document in `CLAUDE.md` commands section when shipped.

### Out of scope (for later buckets)

- Hard-deleting catalog `matching_jobs` rows for wrong location (scrape merge already excludes new ones; stale rows kept by design).
- Changing orphan reinjection for wrong-location applied jobs (product decision — see `tests/BUSINESS_RULES.md` “Not specified”).
- Per-user vs global wrong-location policy (today: per-user tracking, shared catalog).

---

## Template for new items

```markdown
## Title

**Status:** planned | in progress | done  
**Priority:** low | medium | high  
**Context:** one paragraph

### Problem / goal

### Approach

### Done when
```
