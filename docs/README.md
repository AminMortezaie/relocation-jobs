# Documentation

**Last updated:** 2026-07-13

All project docs live under `docs/`. [README](../README.md) at the repo root covers product setup and usage only.

---

## Quick paths

| I want to… | Read |
|------------|------|
| Install and run the panel | [README](../README.md) |
| Set up for development | [contributing.md](contributing.md) |
| Understand code layout & data flow | [reference/architecture.md](reference/architecture.md) |
| Change Python in `relocation_jobs/` | [reference/rules.md](reference/rules.md) |
| Change job apply / reject / hide behavior | [reference/business-rules.md](reference/business-rules.md) |
| Work on board sort, pagination, newest | [reference/board.md](reference/board.md) |
| Board performance / read-model design (proposal) | [reference/board-read-model-proposal.md](reference/board-read-model-proposal.md) |
| Fetch pipeline queue / Kafka placement (proposal) | [reference/kafka-fetch-pipeline-proposal.md](reference/kafka-fetch-pipeline-proposal.md) |
| Multi-user scaling — SQS broker, DB pool, board projection (proposal) | [reference/multi-user-scaling-proposal.md](reference/multi-user-scaling-proposal.md) |
| Full SPA UI modernization (proposal) | [reference/full-spa-ui-modernization-proposal.md](reference/full-spa-ui-modernization-proposal.md) |
| Single-company fetch modal session (why it felt flaky) | [reference/fetch-panel-session.md](reference/fetch-panel-session.md) |
| Catalog vs per-user tracking (design) | [reference/catalog-pattern.md](reference/catalog-pattern.md) |
| Panel / admin statistics | [reference/stats.md](reference/stats.md) |
| Test failures / catalog seed in tests | [reference/catalog-seed-test-failure.md](reference/catalog-seed-test-failure.md) |
| Board hung / slow load (2026-07 postmortem) | [reference/board-load-performance-incident.md](reference/board-load-performance-incident.md) |
| Country cache Redis hot-path regression (2026-07 postmortem) | [reference/country-cache-redis-hotpath-incident.md](reference/country-cache-redis-hotpath-incident.md) |
| Fetch scheduler hung / timeouts (2026-07) | [reference/fetch-scheduler-timeout-practices.md](reference/fetch-scheduler-timeout-practices.md) |
| Secrets / no real IPs in public docs | [reference/rules.md](reference/rules.md#secrets-and-documentation) · `.env` / `aws-postgres.env` gitignored |
| MCP apply assistant (Claude Desktop, v0) | [reference/mcp-application.md](reference/mcp-application.md) |
| Company workspace (CV/PDF on panel) | [reference/company-workspace.md](reference/company-workspace.md) |
| **Production panel (EC2, kuchup.com)** | [operations/ec2-panel.md](operations/ec2-panel.md) |
| Agent commands cheat sheet | [CLAUDE.md](../CLAUDE.md) |

---

## Layout

```
docs/
  README.md                 ← this index
  contributing.md           dev setup, tests, where to code
  backlog.md                  planned work
  reference/
    architecture.md           data flow, package layout, panel read path
    board.md                  pagination, “newest first” sort, timestamps
    board-read-model-proposal.md  board performance: projection table, cursors (proposal)
    kafka-fetch-pipeline-proposal.md  fetch/scrape work queue, Kafka placement (proposal)
    multi-user-scaling-proposal.md  SQS job queue, DB pool, board projection for many users (proposal)
    full-spa-ui-modernization-proposal.md  React SPA, design system, dark/light, mobile (proposal)
    fetch-panel-session.md    single-company fetch modal: session ownership + settle-once UX
    stats.md                  admin/user stats definitions
    business-rules.md         job buckets, orphans, apply/reject/not-for-me
    rules.md                  v2 coding standards (SQL in repo.py)
    schemas.md                Pydantic models, catalog shape
    parity.md                 v1 vs v2 checklist (complete)
    catalog-pattern.md        shared catalog + per-user overlay (design)
    catalog-seed-test-failure.md  post-mortem: pytest pollution after board sort tests
    country-cache-redis-hotpath-incident.md  post-mortem: Redis I/O in country-label hot path
    mcp-application.md          Claude Desktop MCP: resume tex → PDF, apply prep (v0)
    company-workspace.md        Panel company page: tailored CV + PDF preview
  operations/
    aws-postgres.md           AWS EC2 Postgres
    ec2-panel.md              Panel on EC2, kuchup.com, Caddy
  archive/                    historical handoffs — read only if debugging old work
    v2-bugfix-handoff.md
    v2-coding-verdict.md
    refactor-handoff.md
```

---

## By topic

### Development

| Doc | Purpose |
|-----|---------|
| [contributing.md](contributing.md) | First 15 minutes, domains, tests, database, fetch |
| [reference/architecture.md](reference/architecture.md) | Data flow, v2 layout, panel read path, client patterns |
| [reference/rules.md](reference/rules.md) | Layer boundaries, naming, scrape/fetch, tests |
| [.cursor/rules/v2-coding.mdc](../.cursor/rules/v2-coding.mdc) | Cursor summary of rules |

Agent skills: `.claude/skills/` (`getting-started` → `collaboration-style` → `engineering-standards` → …)

### Panel behavior

| Doc | Purpose |
|-----|---------|
| [reference/board.md](reference/board.md) | Board API, pagination, newest sort (mermaid) |
| [reference/fetch-panel-session.md](reference/fetch-panel-session.md) | Single-company fetch modal session (stale UI / double board update) |
| [reference/stats.md](reference/stats.md) | Admin/user stats definitions |
| [reference/business-rules.md](reference/business-rules.md) | Job state contracts — read before tracking changes |

### Data

| Doc | Purpose |
|-----|---------|
| [reference/schemas.md](reference/schemas.md) | Pydantic models and catalog envelope |
| [reference/catalog-pattern.md](reference/catalog-pattern.md) | Shared catalog vs per-user overlay |
| [reference/parity.md](reference/parity.md) | v1 removal / cutover status |

### Operations

| Doc | Purpose |
|-----|---------|
| [operations/aws-postgres.md](operations/aws-postgres.md) | AWS Postgres migration and day-to-day ops |
| [operations/ec2-panel.md](operations/ec2-panel.md) | EC2 deploy, kuchup.com, Caddy, Cloudflare lock-down |
| `scripts/ec2_app_deploy.sh` | Panel deploy to EC2 |
| `scripts/ec2_redis.sh` | Redis on EC2 |

### Backlog & archive

| Doc | Purpose |
|-----|---------|
| [backlog.md](backlog.md) | Living backlog |
| [archive/v2-bugfix-handoff.md](archive/v2-bugfix-handoff.md) | Recent bugfix context |
| [archive/v2-coding-verdict.md](archive/v2-coding-verdict.md) | Known v2 violations backlog |
| [archive/refactor-handoff.md](archive/refactor-handoff.md) | **Historical** v1 Phase A–C |

---

## Root entry points (tools)

| File | Role |
|------|------|
| [README.md](../README.md) | Product + quick start |
| [AGENTS.md](../AGENTS.md) | Agent pointer → this index |
| [CLAUDE.md](../CLAUDE.md) | Commands + current focus |

**Do not commit** unless explicitly asked.
