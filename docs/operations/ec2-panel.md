# EC2 panel production (kuchup.com)

**Domain:** [kuchup.com](https://kuchup.com) (Cloudflare)  
**Server:** same EC2 instance as Postgres + Redis (`aws-postgres.env` → `ELASTIC_IP`)  
**Status:** panel + fetch worker + Caddy on EC2; Render optional legacy until cutover

---

## Stack on EC2

| Service | Container | Port |
|---------|-----------|------|
| Postgres | `pg` | 5432 |
| Redis | `relocation-redis` | 6379 |
| Panel (gunicorn) | `relocation-panel` | 127.0.0.1:10000 |
| Fetch worker (scheduler) | `relocation-fetch-worker` | — |
| Caddy (TLS + reverse proxy) | `relocation-caddy` | 80, 443 |

Panel talks to Postgres/Redis via Docker bridge gateway `172.17.0.1` (localhost on the host). The fetch worker only needs Postgres; it runs country scrapes every **6 hours** (sequential countries, concurrency **4**).

---

## Deploy / update

From repo root (SSH key `~/Downloads/relocation.pem`, `aws-postgres.env` present):

```bash
./scripts/ec2_app_deploy.sh deploy        # rsync + build panel + worker + Caddy
./scripts/ec2_app_deploy.sh status        # containers + health check + worker logs
./scripts/ec2_app_deploy.sh worker-logs   # follow fetch scheduler logs
```

`deploy` also opens security group ports **80** and **443**.

| Image | Dockerfile | Role |
|-------|------------|------|
| `relocation-panel:ec2` | `Dockerfile.ec2` | Slim panel — no Playwright; includes **tectonic** for PDF render; `PANEL_SCRAPE_ENABLED=0`, `PANEL_COMPANY_FETCH_ENABLED=1` |
| `relocation-fetch-worker:ec2` | `Dockerfile.ec2-worker` | Playwright + 6h scheduler; writes to shared Postgres (no TeX) |

**PDF render:** the panel image installs pinned tectonic and warms its package cache at build time. After deploy, smoke with `docker exec relocation-panel tectonic --version`, then **Re-render PDF** on a master or company workspace on [kuchup.com](https://kuchup.com).

Manual country scrape from your laptop still works (`PANEL_SCRAPE_ENABLED=1`); the worker skips a cycle if another fetch is already running (`fetch_runs.status = running`).

**Panel company fetch:** `POST /api/companies/fetch` (board **Fetch jobs**) runs in the panel process when `PANEL_COMPANY_FETCH_ENABLED=1`. Country-wide `/api/fetch` stays off on the slim panel. Playwright-only ATS boards still need the worker or a local scrape.

**Worker env (set by deploy):** `FETCH_SCHEDULE_ENABLED=1`, `FETCH_SCHEDULE_INTERVAL_HOURS=6`, `FETCH_SCHEDULE_CONCURRENCY=4`. Optional override: `FETCH_SCHEDULE_COUNTRIES=uk,netherlands`.

On `t4g.micro`, if the worker OOMs during fetch, lower concurrency to `2` or upsize the instance.

**Scheduler stuck?** If `worker-logs` shows no new lines for 2+ hours while the container is Up, a Playwright scrape may have hung. Restart: `docker restart relocation-fetch-worker`. See [fetch-scheduler-timeout-practices.md](../reference/fetch-scheduler-timeout-practices.md) for layered timeout rules and the implementation plan.

---

## Cloudflare DNS

Point the domain at the Elastic IP from `aws-postgres.env`:

| Type | Name | Content | Proxy |
|------|------|---------|-------|
| A | `@` | `<ELASTIC_IP>` | start grey; orange when locking origin (below) |
| A | `www` | `<ELASTIC_IP>` | same |

Caddy in `deploy/ec2/Caddyfile` requests Let's Encrypt certs for `kuchup.com` and `www.kuchup.com`. The panel is **not** served on the raw Elastic IP — use the domain only.

**First cutover (simplest):** grey cloud (DNS only) until `https://kuchup.com` works.

**Cloudflare SSL (orange cloud):** **SSL/TLS** → **Full** or **Full (strict)** (never **Flexible**).

Verify:

```bash
dig +short kuchup.com A
curl -I https://kuchup.com
```

---

## Lock down origin (domain only, hide IP)

Goal: users reach the panel via `https://kuchup.com` only; casual access to `http://<ELASTIC_IP>` is blocked.

| Layer | What it does |
|-------|----------------|
| **Caddy** | Explicit 404 on the Elastic IP — only `kuchup.com` / `www` proxy to the panel |
| **Cloudflare proxy** | Orange cloud hides origin IP from public DNS (`dig` shows Cloudflare IPs) |
| **AWS security group** | Ports 80/443 accept traffic **only from Cloudflare**, not `0.0.0.0/0` |

The origin IP can still be discovered (old DNS, scans, leaks). Treat this as **not advertising** the IP, not making it impossible to find.

### 1. Caddy (done in repo)

`deploy/ec2/Caddyfile` returns **404** for `http://<ELASTIC_IP>`; only the domain proxies to the panel. After changing it:

```bash
./scripts/ec2_app_deploy.sh sync
ssh -i ~/Downloads/relocation.pem ec2-user@<ELASTIC_IP> 'docker restart relocation-caddy'
```

### 2. Cloudflare — enable proxy

**DNS → Records:** set `@` and `www` to **Proxied** (orange cloud).

**SSL/TLS → Overview:** **Full** or **Full (strict)**.

### 3. AWS — restrict 80/443 to Cloudflare

In **EC2 → Security Groups** (panel instance), for inbound **HTTP (80)** and **HTTPS (443)**:

1. Remove rules with source `0.0.0.0/0`.
2. Add rules with source = [Cloudflare IPv4 ranges](https://www.cloudflare.com/ips-v4) (and [IPv6](https://www.cloudflare.com/ips-v6) if you use AAAA).

**Do not** open 80/443 to the world again. `./scripts/ec2_app_deploy.sh open-sg` adds `0.0.0.0/0` — skip that step after lock-down, or remove those rules manually.

**Keep separate (your IP only, never `0.0.0.0/0`):**

- SSH **22**
- Postgres **5432** (local dev / Render if still used)
- Redis **6379** (if accessed off-box)

Example (replace `sg-…` and region; IPv4 list changes — fetch current ranges from Cloudflare):

```bash
# Remove public web (if present)
aws ec2 revoke-security-group-ingress --region eu-central-1 --group-id sg-XXXXXXXX \
  --ip-permissions 'IpProtocol=tcp,FromPort=80,ToPort=80,IpRanges=[{CidrIp=0.0.0.0/0}]'
aws ec2 revoke-security-group-ingress --region eu-central-1 --group-id sg-XXXXXXXX \
  --ip-permissions 'IpProtocol=tcp,FromPort=443,ToPort=443,IpRanges=[{CidrIp=0.0.0.0/0}]'

# Allow Cloudflare (repeat per CIDR from https://www.cloudflare.com/ips-v4)
aws ec2 authorize-security-group-ingress --region eu-central-1 --group-id sg-XXXXXXXX \
  --ip-permissions 'IpProtocol=tcp,FromPort=80,ToPort=80,IpRanges=[{CidrIp=173.245.48.0/20,Description=cloudflare}]'
# …same for 443 and remaining Cloudflare CIDRs
```

### 4. Verify lock-down

```bash
curl -I https://kuchup.com                    # 200 / redirect — OK
curl -I http://<ELASTIC_IP> --max-time 5    # timeout or refused — OK
dig +short kuchup.com A                     # Cloudflare IPs when proxied
```

Health checks after lock-down: use the domain, not the Elastic IP:

```bash
curl -sf https://kuchup.com/api/auth/status
```

---

## Environment on server

Set via `ec2_app_deploy.sh` (from local `.env` / `aws-postgres.env`):

- `DATABASE_URL` → `172.17.0.1:5432`
- `REDIS_URL` → `172.17.0.1:6379`
- `PANEL_SECRET_KEY`, `PANEL_ADMIN_PASSWORD`

Do not commit production secrets. Rotate `PANEL_SECRET_KEY` to a long random value in `.env` before deploy if still using the placeholder.

---

## SSH

```bash
cd ~/Downloads
ssh -i relocation.pem ec2-user@<ELASTIC_IP>
docker ps
docker logs relocation-panel --tail 50
docker logs relocation-fetch-worker --tail 50
docker logs relocation-caddy --tail 50
```

---

## Related

- [aws-postgres.md](aws-postgres.md) — Postgres on EC2
- `scripts/ec2_redis.sh` — Redis on EC2
- [board-read-model-proposal.md](../reference/board-read-model-proposal.md) — board performance (still the main latency fix)
