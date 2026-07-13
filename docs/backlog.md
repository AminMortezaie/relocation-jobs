# Application bucket list

Living backlog of planned work. Add items as we discover them; check off when shipped.

---

## Not-for-me soft delete (wrong location + user hides)

**Status:** in progress (expired hide reason shipped 2026-07-03)  
**Priority:** medium  
**Context:** Rule 16 routes known wrong-location roles to the not-for-me bucket at panel read time. User-initiated “not for me” writes `job_tracking.not_for_me`. Wrong-location hides were read-time only until the one-shot `scripts/mark_wrong_location_jobs.py` backfill.

**Shipped (2026-07-03):** **Expired** added as a user-chosen hide reason (`not_for_me_reason='expired'`) in the board hide picker — human review when a posting is closed; same tracking bucket and restore flow as other not-for-me reasons. Automatic expiry during fetch is still out of scope.

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
     - Skip rows already `not_for_me` with a user-chosen reason (`not_for_me`, `expired`, `no_relocation`, etc.).
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
   - Document in `docs/README.md` commands section when shipped.

### Out of scope (for later buckets)

- Hard-deleting catalog `matching_jobs` rows for wrong location (scrape merge already excludes new ones; stale rows kept by design).
- Changing orphan reinjection for wrong-location applied jobs (product decision — see [business-rules.md](reference/business-rules.md) “Not specified”).
- Per-user vs global wrong-location policy (today: per-user tracking, shared catalog).

---

## Board read model (fast pagination + mutation refresh)

**Status:** planned (proposal written)  
**Priority:** high  
**Context:** `GET /api/board` rescans/flattens the catalog on many requests (~2s). Mutations (not-for-me on newest job, hide-empty, sort) require a **correct global board refresh** with pagination — client cache or ES are poor fits. See [reference/board-read-model-proposal.md](reference/board-read-model-proposal.md).

### Problem / goal

- Sub-second, authoritative board update after state changes (one round trip).
- Millisecond-scale paginated reads at scale.
- Postgres remains sole source of truth; `flatten.py` remains merge spec.

### Approach (summary)

1. **Phase 0:** mutation responses return board page + stats; cut extra round trips.
2. **Phase 1:** `user_board_company` Postgres projection, synchronous write-through via `flatten_company()` (Option F).
3. **Phase 2:** keyset cursor pagination on `(sort_ts, company_id)`.
4. **Phase 4 (optional):** Redis ZSET + HASH read path (Option G) — [proposal](reference/board-read-model-proposal.md#g-redis-derived-board-zset-rank--row-cache--viable-read-accelerator).

### Decision pending

- **F only** vs **F + G** (Postgres truth + Redis board reads)
- **Reject:** Redis-first UI with async Postgres writes

### Done when

- [ ] Proposal approved (open decisions in doc resolved)
- [ ] Parity tests: projection vs legacy flatten
- [ ] p95 targets in proposal met on realistic data

---

## Multi-user scaling (DB pool, SQS job queue, board projection)

**Status:** planned (proposal written)
**Priority:** high (blocks going beyond a single real user)
**Context:** App has one real user today. Scaling to many concurrent users exposes: a single shared Postgres connection serializing all HTTP threads, per-request board re-flattening, and per-user job submission (company fetch, PDF compile) with no queue — one user's fetch/PDF request blocks another's via a global mutex. See [reference/multi-user-scaling-proposal.md](reference/multi-user-scaling-proposal.md).

### Problem / goal

- Concurrent users must not serialize on one DB connection or one global fetch mutex.
- Per-user fetch/PDF job submission needs a durable queue with retry/DLQ, without adding memory load to the `t4g.micro` box.
- Board reads must not degrade as user count grows (ties into the board read model item below).

### Approach (summary)

1. **Phase 0:** real Postgres connection pool (`core/db.py`) + gunicorn workers 1→2 — no new infra.
2. **Phase 1:** Amazon SQS queues for company-fetch requests, country-fetch requests, and PDF render requests — chosen over Redis Streams/Celery/RabbitMQ (all add RAM load to the box) and Kafka/MSK (no free tier, ~$460+/mo). SQS is fully managed and has a permanent 1M req/mo free tier.
3. **Phase 2:** board read model projection (`user_board_company`) — see item below, tracked independently.
4. **Framework:** stay on sync Flask; do not adopt Quart (stagnant since Dec 2024); only consider FastAPI later if load-test profiling shows the sync request cycle itself is the ceiling.

### Decision made

- **Broker: SQS** (supersedes the Redis Streams / Kafka options considered in the fetch-pipeline-queue item below, for the specific case of per-user job submission).
- **Framework: sync Flask**, FastAPI conditional on profiling data, Quart rejected.

### Done when

- [ ] Phase 0 shipped: connection pool, gunicorn workers=2, tests green
- [ ] Phase 1 shipped: SQS queues + DLQs provisioned, fetch/PDF routes enqueue instead of blocking, worker script(s) deployed
- [ ] Load test informs whether FastAPI (Phase 3) is warranted

---

## Fetch pipeline queue (Kafka / Postgres / Redis Streams)

**Status:** planned (proposal written)  
**Priority:** low (until fetch scale or reliability bites)  
**Context:** Fetch/scrape is the only async workload. Today it uses in-process threads, a global `fetch_runs` mutex, and sequential countries in the EC2 scheduler. No message broker. See [reference/kafka-fetch-pipeline-proposal.md](reference/kafka-fetch-pipeline-proposal.md).

### Problem / goal

- Durable per-company work units with retry (survive worker crash).
- Optional scale-out beyond one `t4g.micro` worker.
- Decouple scheduler enqueue from execute without blocking on global `running` row.
- **Not** a goal: async board, MCP, or user tracking.

### Approach (summary)

1. **Default:** stay on status quo until measured pain.
2. **First queue step:** Postgres `fetch_jobs` + `FOR UPDATE SKIP LOCKED` (same EC2, no new service).
3. **Optional:** Redis Streams for progress fan-out (Redis already on host).
4. **Kafka:** only if multiple consumer types or many worker replicas are required.
5. **Code layout if events:** `core/kafka_client.py` + `events/` domain; producers at `fetch/scheduler` + `web/routes/fetch`; consumers in `scripts/*_worker.py`; keep `fetch_runs` audit.

### Decision pending

- **A** status quo vs **B** Postgres queue vs **C** Redis Streams vs **D** Kafka

### Done when

- [ ] Proposal approved (broker choice in doc resolved)
- [ ] Baseline metrics: cycle duration, busy skips, orphan reaps
- [ ] If implemented: fetch tests + EC2 deploy runbook updated

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
