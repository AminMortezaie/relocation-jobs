# MCP application assistant (v0)

**Last updated:** 2026-06-29

Plan and reference for the `relocation_jobs/mcp/` domain: a local MCP server for **Claude Desktop** that prepares tailored resume PDFs for jobs on the panel. v0 does **not** submit applications automatically and does **not** use the Claude API — Claude Desktop (subscription) does the resume reframing in chat; this app supplies data, validation, PDF rendering, and board state updates.

Related: [architecture.md](architecture.md), [business-rules.md](business-rules.md), [contributing.md](../contributing.md).

---

## Goals (v0)

| In scope | Out of scope (later) |
|----------|----------------------|
| MCP tools for job context, queue, resume files | Headless Claude API orchestration |
| Master `.tex` template + tailored `.tex` per job | Browser auto-submit (Playwright) |
| Deterministic validation before PDF render | ATS-specific form fillers |
| Local LaTeX → PDF (`tectonic` / `pdflatex`) | Batch unattended apply |
| `mark_applied` via existing `positions` service | New HTTP routes on the panel |

---

## Architecture

```text
Claude Desktop (subscription LLM)
        │  natural language: "Prepare application for Acme — Backend Engineer"
        ▼
MCP stdio server  (scripts/mcp_server.py)
        │
        ▼
relocation_jobs/mcp/
  server.py     MCP tool definitions (thin)
  service.py    Job context, queue, mark applied (no SQL)
  repo.py       Files under PANEL_DATA_DIR/mcp/ (no SQL)
  validate.py   Tex structure + fact checks vs master resume
  render.py     subprocess LaTeX compile
  paths.py      Directory layout
  types.py      Pydantic boundary models
        │
        ├── catalog/repo     job + company reads
        ├── positions/service mark applied / looking-to-apply
        └── users/repo       tracking overlay for queue
```

Claude Desktop is the **client**. It starts the MCP server and calls tools. The server reads the same Postgres catalog and tracking as the panel (`DATABASE_URL` in `.env`).

---

## Data layout

All MCP artifacts live under `PANEL_DATA_DIR` (default: `data/`), in `mcp/`:

```text
data/mcp/
  master_resume.tex       canonical resume (you edit; not overwritten by tools)
  profile.json            static application fields (name, email, LinkedIn, …)
  applications/
    <idempotency_key>/
      resume.tex          tailored draft (written by save_tailored_tex)
      resume.pdf          output of render_pdf
      meta.json           job key, timestamps, validation snapshot
```

Shipped templates (copied on first `ensure_data_layout()` if missing):

- `relocation_jobs/mcp/assets/master_resume.tex`
- `relocation_jobs/mcp/assets/profile.example.json` → `profile.json`

`data/` is gitignored; templates in the repo are the source of truth for first-run bootstrap.

---

## MCP tools (v0)

| Tool | Purpose |
|------|---------|
| `get_job_context` | Country, company, URL → title, ATS type, tracking flags, idempotency key, application dir |
| `list_application_queue` | Pinned + `looking_to_apply` jobs for the configured user |
| `get_master_resume` | Read `master_resume.tex` |
| `get_application_profile` | Read `profile.json` |
| `save_tailored_tex` | Write `applications/<key>/resume.tex` |
| `validate_tex` | Structure + fact checks vs master (optional path; defaults to latest saved tailored tex) |
| `render_pdf` | Compile tailored tex → PDF; returns path or compiler log on failure |
| `mark_applied` | Call `positions.set_job_applied` for the configured user |

### Intended Claude Desktop workflow

1. User pins a job or marks **looking to apply** on the panel.
2. In Claude Desktop: *"Prepare application for [company] — [title]"*.
3. Claude calls `get_job_context` (or picks from `list_application_queue`).
4. Claude calls `get_master_resume` + `get_application_profile`.
5. Claude produces tailored `.tex` (in chat) and calls `save_tailored_tex`.
6. Claude calls `validate_tex`; fix and re-save if errors.
7. Claude calls `render_pdf`; user uploads PDF to the employer site.
8. After manual submit: *"Mark applied"* → `mark_applied`.

Put rules in a Claude Desktop **Project** (system instructions): only rewrite content; never invent employers or dates; always `validate_tex` before `render_pdf`.

---

## Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `MCP_USERNAME` | `admin` | Panel user for tracking reads/writes |
| `MCP_USER_ID` | (unset) | Override user id; wins over `MCP_USERNAME` |
| `MCP_LATEX_CMD` | `tectonic` | LaTeX compiler binary (`pdflatex`, `xelatex`, …) |
| `DATABASE_URL` | (required) | Same as panel |
| `PANEL_DATA_DIR` | `data` | Root for `mcp/` subtree |

---

## Validation rules (v0)

`validate_tex` runs before PDF render:

1. **Structure** — balanced `\begin{document}` / `\end{document}`; `\begin`/`\end` counts match.
2. **Facts** — extract year tokens (`19xx`/`20xx`) and employer-like lines from master; fail if tailored tex introduces years or employer strings not present in master (heuristic, not perfect).
3. **Size** — max line count guard (default 400 lines).

Failures return a list of machine-readable issues for Claude to fix.

---

## PDF rendering

`render.py` runs the compiler in the application directory:

- **Recommended:** [Tectonic](https://tectonic-typesetting.github.io/) — single binary, auto-fetches packages.
- **Alternative:** TeX Live `pdflatex` / `xelatex` (set `MCP_LATEX_CMD`).

Security: no `--shell-escape`; compile only files under `data/mcp/applications/`.

---

## Layer rules

Follow [rules.md](rules.md):

- **SQL only in existing repos** — `mcp/repo.py` is filesystem-only.
- **service.py** orchestrates `catalog`, `positions`, `users`; no HTTP, no SQL.
- **server.py** is a thin MCP adapter.

---

## Claude Desktop setup

Add to `claude_desktop_config.json` (macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "relocation-jobs": {
      "command": "python3",
      "args": ["/absolute/path/to/resume/scripts/mcp_server.py"],
      "env": {
        "DATABASE_URL": "postgresql://…",
        "MCP_USERNAME": "admin",
        "MCP_LATEX_CMD": "tectonic"
      }
    }
  }
}
```

Use the project venv’s `python3` if dependencies are installed there. Restart Claude Desktop after config changes.

---

## Run locally (development)

```bash
pip install -r requirements-dev.txt   # includes mcp
# Install tectonic: brew install tectonic  (macOS)

cp .env.example .env                  # DATABASE_URL, admin user
PANEL_SCRAPE_ENABLED=1 python3 scripts/panel_server.py   # optional: panel on :5051

python3 scripts/mcp_server.py         # stdio — for manual smoke test, or use Desktop
```

Tests:

```bash
pytest tests/mcp -o addopts=
```

---

## Rollout phases

| Phase | Deliverable |
|-------|-------------|
| **v0 (this doc)** | MCP tools, tex validate/render, mark applied |
| **v1** | Richer validation (keyword coverage vs JD), JD fetch helper tool |
| **v2** | Greenhouse/Lever Playwright submitter behind same application dirs |
| **v3** | Optional Claude API runner for unattended queue (separate from Desktop) |

---

## Test mapping

| Area | Test file |
|------|-----------|
| Tex validation | `tests/mcp/test_validate.py` |
| PDF render (mocked compiler) | `tests/mcp/test_render.py` |
| Job context + queue | `tests/mcp/test_service.py` |

---

## Files added

```text
relocation_jobs/mcp/
  __init__.py
  types.py
  paths.py
  repo.py
  validate.py
  render.py
  service.py
  server.py
  assets/
    master_resume.tex
    profile.example.json

scripts/mcp_server.py
tests/mcp/
  test_validate.py
  test_render.py
  test_service.py
```
