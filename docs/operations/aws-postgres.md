# Postgres migration: Neon → AWS handoff

**Date:** 2026-06-24  
**Status:** **Complete** (Scenario A — EC2 + Docker Postgres, `eu-central-1`)  
**Goal:** Move `DATABASE_URL` from Neon to AWS Postgres for more stable parallel scrapes, while keeping cost near $0 where possible.

**Ops script:** `scripts/aws_postgres_migrate.sh` (`sync-sg`, `ensure-eip`, `status`)  
**State file:** `aws-postgres.env` (gitignored) — Elastic IP, instance ID, password  
**Onboarding:** [`docs/contributing.md`](../contributing.md)

---

## Context

### Current stack

| Component | Where | Notes |
|-----------|--------|--------|
| **Postgres** | Neon `eu-central-1` (pooler hostname) | `DATABASE_URL` in `.env` + Render dashboard |
| **Panel (prod)** | Render free tier, **Frankfurt** | `render.yaml`; `PANEL_SCRAPE_ENABLED=0` |
| **Panel + scrape (dev)** | Local, v2 on **5051** | `PANEL_SCRAPE_ENABLED=1` |
| **v1 panel** | Local **5050** | Same DB, same static UI |

### Why migrate

Country fetch at **16 workers** hit Neon connection drops:

```text
[FETCH] Error: consuming input failed: could not receive data from server: Operation timed out
SSL SYSCALL error: Operation timed out
```

Example: Netherlands fetch — **36/47** companies done, then DB timeout during LeaseWeb enrichment (~4 min in).

Root cause is **burst parallel DB connections** (one per worker thread in `relocation_jobs/core/db.py`) + live `fetch_runs` writes + long enrichment — not necessarily “Neon is bad,” but serverless/pooler is fragile under this load.

### App DB usage (no schema fork)

- Single env var: **`DATABASE_URL`** (required; no SQLite fallback in prod).
- Schema: `init_db()` + `relocation_jobs/core/migrations.py` on startup.
- Driver: `psycopg` in `relocation_jobs/core/db.py`.
- Neon-specific today: `prepare_threshold=None` (pooler), keepalive tuning, idle ping every ~4.5 min.
- Existing dump/migrate script: `scripts/migrate_sqlite_to_neon.py` — works with **any** Postgres URL despite the name.

**No code changes required for cutover** — only connection string + infra. Optional doc/README updates after success.

---

## Choose a scenario

### Scenario A — **Near-free year 1** (recommended if cost matters)

**EC2 `t3.micro` / `t4g.micro` + Docker Postgres** in `eu-central-1` (Frankfurt).

| | |
|--|--|
| **Cost** | ~**$0** months 1–12 (new AWS account free tier); then ~**$8–10/mo** (EC2 + EBS) |
| **Pros** | Cheapest AWS path; always-on; full control |
| **Cons** | You manage Postgres (Docker), backups, patches; micro instance weak under 16 workers |

### Scenario B — **Managed, still cheap year 1**

**RDS PostgreSQL `db.t3.micro` / `db.t4g.micro`** in `eu-central-1`.

| | |
|--|--|
| **Cost** | ~**$0** year 1 (750 hrs/mo free tier); then ~**$15–20+/mo** |
| **Pros** | Automated backups, less ops |
| **Cons** | More expensive after free tier than EC2; still need network access from Render + laptop |

### Scenario C — **Hybrid (lowest ongoing $0)**

Keep **Neon** for Render panel; use **local Postgres** or **on-demand EC2** only for heavy scrapes.

| | |
|--|--|
| **Cost** | **$0** ongoing for panel |
| **Cons** | Two databases or manual sync; Render and scraper don’t share one DB unless you replicate |

### Scenario D — **Don’t migrate yet**

Stay on Neon; reduce scrape **`concurrency` to 8** and retry. Cheapest if scrapes are occasional.

**User intent:** migrate to AWS → implement **Scenario A or B**. Default recommendation: **A for near-free**, **B if user prefers managed**.

---

## Target architecture

```text
Render (Frankfurt) ──────┐
                         ├──► AWS Postgres (eu-central-1)
Local panel :5051 ───────┤      (EC2 Docker or RDS)
Local country scrape ────┘
```

**Region:** `eu-central-1` — same as Neon today and Render Frankfurt.

---

## Pre-migration checklist

- [ ] AWS account (new account = free tier year 1).
- [ ] `pg_dump` / `pg_restore` available locally (`brew install libpq` or Postgres.app).
- [ ] Neon **direct** (non-pooler) connection string for dump — pooler can break `pg_dump`.
- [ ] Stop active fetches; avoid writes during final cutover window.
- [ ] Note current `DATABASE_URL` somewhere safe (rollback).
- [ ] Render dashboard access to update `DATABASE_URL`.

---

## Scenario A — EC2 + Docker Postgres (step-by-step)

### A1. Launch EC2

- **Region:** eu-central-1  
- **AMI:** Ubuntu 24.04 LTS  
- **Instance:** `t4g.micro` (or `t3.micro`)  
- **Storage:** 20 GB gp3 (within free tier)  
- **Elastic IP:** allocate and associate (stable endpoint for `DATABASE_URL`)  
- **Security group inbound:**
  - SSH 22 — your IP only  
  - Postgres 5432 — your IP (scrape) + see **Render access** below  

### A2. Install Docker on EC2

```bash
sudo apt update && sudo apt install -y docker.io
sudo usermod -aG docker ubuntu
# re-login, then:
```

### A3. Run Postgres 16

```bash
docker run -d --name pg --restart unless-stopped \
  -e POSTGRES_USER=relocation \
  -e POSTGRES_PASSWORD='<long-random-password>' \
  -e POSTGRES_DB=relocation_jobs \
  -v pgdata:/var/lib/postgresql/data \
  -p 5432:5432 \
  postgres:16
```

Use a strong password; store in password manager.

### A4. Dump Neon

From local machine (repo root, `.env` loaded):

```bash
# Prefer non-pooler Neon host for pg_dump
pg_dump "$DATABASE_URL" \
  --no-owner --no-acl \
  --format=custom \
  -f /tmp/relocation_jobs.dump
```

If `DATABASE_URL` uses `-pooler`, swap to direct endpoint in Neon console for this step only.

### A5. Restore to EC2

```bash
export RDS_URL="postgresql://relocation:PASSWORD@<ELASTIC_IP>:5432/relocation_jobs?sslmode=prefer"

# Create empty DB is done by POSTGRES_DB above; restore:
pg_restore -d "$RDS_URL" \
  --no-owner --no-acl \
  --clean --if-exists \
  /tmp/relocation_jobs.dump
```

Ignore benign errors about extensions/roles if objects already exist. Verify row counts after restore.

### A6. Cut over

1. **Local `.env`:**

   ```bash
   DATABASE_URL=postgresql://relocation:PASSWORD@<ELASTIC_IP>:5432/relocation_jobs?sslmode=prefer
   ```

2. **Render:** Dashboard → `relocation-jobs` → Environment → `DATABASE_URL` → same URL → redeploy.

3. Restart local v2 server (`5051`).

### A7. Backups (minimal)

Cron on EC2 (daily):

```bash
docker exec pg pg_dump -U relocation relocation_jobs | gzip > /home/ubuntu/backups/$(date +%F).sql.gz
```

Optional: sync to S3 (free tier 5 GB).

---

## Scenario B — RDS PostgreSQL (step-by-step)

### B1. Create RDS instance

- Engine: **PostgreSQL 16**  
- Template: Free tier (if eligible) or Dev/Test  
- Instance: `db.t4g.micro`  
- Storage: 20 GB gp3, autoscaling off for cost control  
- **Public access:** Yes (simplest for Render + local scrape)  
- VPC security group: 5432 from your IP  
- DB name: `relocation_jobs`  
- Master username/password: save securely  

### B2–B6

Same as A4–A7 but use RDS endpoint instead of Elastic IP:

```text
your-instance.xxxxx.eu-central-1.rds.amazonaws.com:5432
```

Use `sslmode=require` in `DATABASE_URL` for RDS.

---

## Render + local scraper network access

Render **free tier** has **no fixed outbound IPs**. Options:

| Approach | Security | Effort |
|----------|----------|--------|
| **5432 open to `0.0.0.0/0`** + strong password + SSL | Weak; ok solo dev | Low |
| **Your IP only** on 5432 | Render panel **breaks** unless DB also reachable | — |
| **Keep Neon for Render**, AWS only for local scrape | Split brain | Medium |
| **Cloudflare Tunnel / Tailscale** on EC2 | Better | Higher |
| **Paid Render static egress** | Good prod pattern | $$ |

**For solo use:** public RDS/EC2 Postgres with strict password + `sslmode=require` + security group allowing `0.0.0.0/0` on 5432 is common; upgrade later.

Document chosen approach in `.env.example` comments when done.

---

## Verification after cutover

### Panel

- [ ] `GET /api/auth/status` — login works (Render + local `:5051`).
- [ ] `GET /api/jobs?country=netherlands` — companies/jobs load.
- [ ] Tracking: apply / reject / not-for-me on one job.

### Scrape (local v2, `PANEL_SCRAPE_ENABLED=1`)

- [ ] Single-company fetch — review modal shows included/filtered.
- [ ] Country fetch **concurrency 8** first — full run completes without SSL timeout.
- [ ] Then try 16 if desired; watch EC2/RDS CPU and connections.

### DB sanity

```sql
SELECT COUNT(*) FROM companies;
SELECT COUNT(*) FROM jobs;
SELECT COUNT(*) FROM users;
SELECT id, country, status, started_at FROM fetch_runs ORDER BY id DESC LIMIT 5;
```

### Logs

Watch for:

```text
SSL SYSCALL error: Operation timed out
consuming input failed
```

If they persist at 16 workers → lower concurrency or upsize instance.

---

## Rollback

1. Revert `DATABASE_URL` in Render + local `.env` to Neon pooler URL.  
2. Redeploy Render.  
3. Restart local server.  

Neon data is stale after cutover unless you re-dump from AWS back to Neon. Take Neon snapshot / final dump before decommissioning.

---

## Post-migration repo updates (optional, separate PR)

| File | Change |
|------|--------|
| `.env.example` | AWS RDS/EC2 examples; de-emphasize Neon pooler note or keep both |
| `README.md` / `CLAUDE.md` | “Postgres on AWS” instead of “Neon required” |
| `render.yaml` comment | `DATABASE_URL → AWS RDS` |
| `relocation_jobs/core/db.py` | Comment only: `prepare_threshold=None` still fine on direct RDS |
| `scripts/migrate_sqlite_to_neon.py` | Optional rename to `migrate_sqlite_to_postgres.py` (low priority) |

**Do not commit secrets.** Never commit `.env`.

---

## Scrape tuning (do even after migration)

| Setting | Recommendation |
|---------|----------------|
| Country fetch workers | Start **8**; increase to 16 only if stable |
| EC2 `t4g.micro` | ~1 GB RAM — 16 parallel Playwright + httpx is heavy |
| DB connections | 16 workers ≈ 16 thread-local connections + main thread — watch `max_connections` |
| Neon idle ping | `_IDLE_PING_THRESHOLD_S = 270` in `db.py` — harmless on always-on AWS |

Longer-term code improvement (not part of infra migration): single writer queue for catalog persists instead of per-thread connections.

---

## Cost summary

| Phase | Scenario A (EC2) | Scenario B (RDS) | Stay on Neon |
|-------|------------------|------------------|--------------|
| Year 1 | ~$0 | ~$0 (free tier) | $0 |
| After | ~$8–10/mo | ~$15–20+/mo | $0 |
| Scrape stability | Better (always-on) | Better | Timeouts at 16 workers |

---

## Execution order (single cutover window)

1. Provision AWS (A or B).  
2. `pg_dump` from Neon (direct URL).  
3. `pg_restore` to AWS.  
4. Smoke test AWS with **local** `.env` only (Render still on Neon).  
5. Switch Render `DATABASE_URL`.  
6. Smoke test prod panel.  
7. Run one country fetch at concurrency 8.  
8. Enable daily backup.  
9. After 3–7 days, delete Neon project.  

---

## Related project docs

- [`CLAUDE.md`](../CLAUDE.md) — env vars, architecture  
- [`.env.example`](../.env.example) — `DATABASE_URL` format  
- [`render.yaml`](../render.yaml) — Render Frankfurt, `DATABASE_URL` sync false  
- [`relocation_jobs/core/db.py`](../relocation_jobs/core/db.py) — connection + thread-local pool  
- [v2-bugfix-handoff.md](../archive/v2-bugfix-handoff.md) — v2 fetch/review work (separate from DB migration)

---

## Open questions for user (resolve in migration chat)

1. **Scenario A vs B** — near-free EC2 vs managed RDS?  
2. **Render access** — accept `0.0.0.0/0:5432` temporarily or split Neon/AWS?  
3. **Decommission Neon** immediately or keep as read-only backup for a week?  
4. **Instance size** after free tier — stay micro or plan `t4g.small` if scrapes are daily?
