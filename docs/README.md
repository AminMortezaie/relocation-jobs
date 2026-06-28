# Documentation

**Last updated:** 2026-06-28

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
| Catalog vs per-user tracking (design) | [reference/catalog-pattern.md](reference/catalog-pattern.md) |
| Panel / admin statistics | [reference/stats.md](reference/stats.md) |
| Test failures / catalog seed in tests | [reference/catalog-seed-test-failure.md](reference/catalog-seed-test-failure.md) |
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
    stats.md                  admin/user stats definitions
    business-rules.md         job buckets, orphans, apply/reject/not-for-me
    rules.md                  v2 coding standards (SQL in repo.py)
    schemas.md                Pydantic models, catalog shape
    parity.md                 v1 vs v2 checklist (complete)
    catalog-pattern.md        shared catalog + per-user overlay (design)
    catalog-seed-test-failure.md  post-mortem: pytest pollution after board sort tests
  operations/
    aws-postgres.md           AWS EC2 Postgres, Render DATABASE_URL
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
| `scripts/aws_postgres_migrate.sh` | `sync-sg`, status, backup |

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
