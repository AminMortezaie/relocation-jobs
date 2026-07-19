# MCP application assistant (v0)

**Last updated:** 2026-07-08

Plan and reference for the `relocation_jobs/mcp/` domain: MCP tools that prepare tailored resume PDFs for jobs on the panel. v0 does **not** submit applications automatically and does **not** use the Claude API — Claude (or Cursor) does the resume reframing in chat; this app supplies data, validation, PDF rendering, and board state updates.

**Private data is stored in Postgres per user — nothing sensitive is committed to git.**

Transports:

- **Remote (production):** Streamable HTTP + OAuth at `https://mcp.kuchup.com/mcp` — Claude custom connectors (including mobile) and Cursor.
- **Local stdio:** `scripts/mcp_server.py` with `MCP_USERNAME` / `MCP_USER_ID` for Claude Desktop on a laptop.

Use the panel **Application data** page at `/apply` to edit profile, pipeline prompts, masters, and **Connect MCP** (URL + optional API tokens).

Related: [architecture.md](architecture.md), [business-rules.md](business-rules.md), [contributing.md](../contributing.md).

**Claude skill:** [`.claude/skills/mcp-resume-reframe/SKILL.md`](../../.claude/skills/mcp-resume-reframe/SKILL.md) — **interactive** gated reframe (one phase per turn, user approval), **additive** JD-mirror bullets on the full master CV (never remove responsibilities without permission), `save_tailored_tex` after final sign-off; PDF render on the panel.

---

## Goals (v0)

| In scope | Out of scope (later) |
|----------|----------------------|
| MCP tools for job context, queue, multi-master resumes | Headless Claude API orchestration |
| Master `.tex` + tailored `.tex` per job in DB | Browser auto-submit (Playwright) |
| Project masters (LaTeX evidence bank for reframe) | Auto-insert full project essays into tailored CV |
| Deterministic validation before PDF render | ATS-specific form fillers |
| Local LaTeX → PDF (`tectonic` / `pdflatex`) | Batch unattended apply |
| `mark_applied` via existing `positions` service | Keyword scoring / auto-fetch JD in chat |

---

## Architecture

```text
Claude / Cursor (remote)          Claude Desktop (local)
        ▼                                    ▼
scripts/mcp_http_server.py          scripts/mcp_server.py
  (Streamable HTTP + OAuth)           (stdio + MCP_USERNAME)
        ▼                                    ▼
relocation_jobs/mcp/
  server.py / http_app.py   MCP tools + HTTP wiring
  oauth_provider.py         OAuth AS (panel login)
  oauth_repo.py             Clients, codes, tokens, API tokens
  service.py                Orchestration (no SQL)
  repo.py                   Postgres application data
  validate.py / render.py   Structure checks + LaTeX
        │
        ├── catalog/repo
        ├── positions/service
        └── users/repo
```

---

## Database schema

Migrations: `mcp_tables_v1`, `mcp_master_resumes_v2`, `mcp_project_masters_v1`.

### `mcp_master_resumes`

| Column | Purpose |
|--------|---------|
| `user_id` + `slug` | PK — e.g. `go`, `java`, `fullstack` |
| `label` | Display name |
| `content` | Master `.tex` |

### `mcp_project_masters`

| Column | Purpose |
|--------|---------|
| `user_id` + `slug` | PK — e.g. `relocation-jobs` |
| `label` | Display name |
| `content` | LaTeX fragment (reframe evidence bank; insert-ready for a Projects block) |

Project masters are **not** employment history and are **not** validated as employers/years. Agents load them during reframe for JD-aligned facts; dumping the full fragment into tailored `.tex` requires explicit user approval. The `/apply` Projects tab can **Re-render PDF** (fragments are wrapped in a minimal `\documentclass` for preview).

### `mcp_user_documents`

Profile (`profile_json`), including optional `pipeline` — up to 5 ordered prompt strings run before resume reframing.

### `mcp_applications`

| Column | Purpose |
|--------|---------|
| `master_resume_slug` | Variant used for this application |
| `tailored_tex`, `pdf_bytes`, `meta_json` | Resume application artifacts |
| `cover_letter_tex`, `cover_letter_pdf_bytes` | Cover letter artifacts (parallel to resume) |
| `cover_letter_tex_updated_at`, `cover_letter_pdf_updated_at` | Cover letter timestamps |

Migration: `mcp_cover_letter_v1`.

---

## MCP tools

| Tool | Purpose |
|------|---------|
| `get_job_context` | Job + tracking + `description_text` (JD), `has_description` / `needs_fetch`, `master_resume_slug`, `has_tailored_tex` / `has_pdf`, `has_cover_letter_tex` / `has_cover_letter_pdf`, `can_save_tailored_tex` |
| `list_application_queue` | Pinned + looking-to-apply jobs (discovery only — not required to save) |
| `list_master_resumes` | All master variants |
| `get_master_resume` / `save_master_resume` | Read/write master tex by slug |
| `list_project_masters` | All project master variants (LaTeX evidence) |
| `get_project_master` / `save_project_master` | Read/write project LaTeX by slug |
| `get_mcp_status` | Debug: MCP user + profile/resume/project presence + `pipeline_prompt_count` |
| `get_application_profile` / `save_application_profile` | Profile fields; `pipeline` array on profile |
| `get_reframe_pipeline` | Ordered pipeline prompts only (alias of profile.pipeline) |
| `save_tailored_tex` | Requires `master_resume_slug`; overwrites prior tailored tex; queue membership not required |
| `validate_tex` | Structure + fact checks vs master |
| `render_pdf` | Compile → store PDF bytes |
| `save_cover_letter_tex` | Freeform cover letter LaTeX; overwrites prior; no master slug; queue membership not required |
| `render_cover_letter_pdf` | Compile cover letter → store PDF bytes (prefer panel Re-render) |
| `mark_applied` | Panel tracking |
| `list_supported_countries` | Country keys for `add_company` (germany, netherlands, uk, portugal) |
| `list_ats_types` | ATS ids for `add_company` (`auto` detects from careers URL) |
| `add_company` | Add employer to catalog — same flow as panel **Add company** (name, careers URL, optional country/ATS/locations) |
| `add_position` | Add a role to an **existing** company — stores JD in catalog (required for LinkedIn) |
| `save_position_description` | Store or append JD for an existing position (`overwrite=true` replaces) |
| `update_position` | Overwrite title, url, location, and/or JD on an existing position |

### Panel integration (company workspace)

MCP writes artifacts to Postgres; the panel reads them via HTTP (same user session as `/apply`).

| Panel surface | Purpose |
|---------------|---------|
| `/apply` | Profile, pipeline prompts, master resumes, project masters (setup) |
| `/company/<country>/<company-slug>` | Per-company workspace: positions, CV / cover letter tex, PDF preview — see [company-workspace.md](company-workspace.md) |
| Job board (phase 3) | CV/PDF and cover-letter badges; company name → workspace |

Web API (login required): `GET /api/mcp/companies/<country>/<company>/applications`, `GET/POST /api/mcp/applications/<idempotency_key>/…` (resume), `…/cover-letter/…` — documented in [company-workspace.md](company-workspace.md).

Claude Desktop owns reframing (`save_tailored_tex` after user approval); optional `save_cover_letter_tex` afterward. The panel **renders PDF** (Re-render PDF, CV or Cover letter tab) to save tokens in chat.

### End-to-end flow (position → pipeline → reframe)

One job from queue to tailored PDF. Claude runs **one pipeline prompt per turn** with a user checkpoint; MCP supplies job, profile, prompts, and master tex.

```mermaid
flowchart TD
  A[Panel: pin job or mark looking to apply] --> B[list_application_queue]
  B --> C[Pick one job]
  C --> D[get_job_context]
  D --> E[get_reframe_pipeline]
  E --> F[Phase 1: JD + ATS lens — markdown]
  F --> G{User: go ahead?}
  G -->|edit| F
  G -->|yes| H[Phase 2: master + mirror pick]
  H --> I{User: go ahead?}
  I -->|edit| H
  I -->|yes| J[Phase 3: add 1–2 mirror bullets]
  J --> K{User: go ahead?}
  K -->|edit| J
  K -->|yes| L[Phase 4: full CV draft markdown]
  L --> M{Final acceptance?}
  M -->|edit| L
  M -->|yes| N[get_master_resume + LaTeX]
  N --> O[save_tailored_tex]
  O --> P[Panel: Re-render PDF]
  P --> Q[Upload PDF manually]
  Q --> R[mark_applied]
```

#### 0. One-time setup (`/apply`)

1. Save **master resume(s)** (e.g. `go`, `java`, `fullstack`).
2. Save **project master(s)** (LaTeX fragments, e.g. `relocation-jobs`) — evidence bank for reframe, not CV employment rows.
3. Save **application profile** (name, email, …).
4. Add **five pipeline prompts** (one phase each) from [`.claude/skills/mcp-resume-reframe/pipeline-prompts.md`](../../.claude/skills/mcp-resume-reframe/pipeline-prompts.md). Each slot ends with a **go ahead?** checkpoint — do not use a single consolidated auto-run prompt.

#### 1. Pick a position

**Option A — from queue**

```text
list_application_queue(country="uk")   # optional country filter
```

Returns pinned and looking-to-apply jobs with `country`, `company`, `url`, `title`.

**Option B — you already know the job**

Use `country`, `company`, and `url` from the panel board.

#### 2. Load job context

```text
get_job_context(country, company, url)
```

Use `title`, `ats_url`, flags (`looking_to_apply`, `pinned`, `in_application_queue`), `can_save_tailored_tex`, and whether tailored tex/PDF already exist.

**Job description:** use `description_text` from this response as the JD for all pipeline phases — do **not** open or scrape the posting URL in chat. When `has_description` is false (`needs_fetch` is true), ask the user to open the company workspace for this position and click **Fetch job description** (or re-run catalog enrich locally), then call `get_job_context` again before phase 1.

`can_save_tailored_tex` is true whenever the job is in the catalog. **Re-runs and overwrites do not require** pinned or looking-to-apply — call `save_tailored_tex` with the `url` / `country` / `company` from this response.

#### 3. Load profile and pipeline prompts

```text
get_reframe_pipeline()
```

or

```text
get_application_profile()   # pipeline is a field on the response
```

**There is no `run_pipeline` tool.** Pipeline prompts are stored in Postgres and returned by the tools above. Claude must run each string in `pipeline[]` **in order in chat** before reframing `.tex`.

Example `get_reframe_pipeline()` response:

```json
{
  "pipeline": [
    "List the top 5 skills this role needs.",
    "Map my experience to those skills.",
    "Reframe the resume emphasizing matches without new facts."
  ],
  "count": 3,
  "run_in_order": true
}
```

Quick sanity check: `get_mcp_status()` → `pipeline_prompt_count` (count only, not text).

#### 4. Run the pipeline (in Claude chat) — one phase per turn

For each string in `pipeline[0]`, `pipeline[1]`, … **in order**:

1. Run **only that phase** for this job (use `get_job_context.description_text` as the JD + masters / project masters as needed).
2. Output **markdown** (not LaTeX) until the final phase.
3. End with **go ahead?** and **wait** for the user before the next phase.
4. **Mirror additions (phase 3):** add **1–2 new bullets** to one real role for ATS/JD similarity — prefer facts from a matching **project master**; **all master bullets kept**. User approves new bullets in phase 2–3. Never remove or shorten master content without explicit user approval. Do not dump the full project narrative into the CV.
5. **Final acceptance** on the full markdown draft (master + additions) before any `.tex` work.

There is no `run_pipeline` MCP tool. Use `get_reframe_pipeline` or `get_application_profile().pipeline`.

#### 5. LaTeX + save (after final acceptance)

```text
get_master_resume("<slug>")    # chosen in phase 2
save_tailored_tex(country, company, url, content, master_resume_slug="java")
validate_tex(...)              # optional in chat; fix blocking issues
```

Use the chosen master's LaTeX structure (preamble, macros, sections). Employers and dates stay fixed. **Copy all master content**; apply only approved additions (new mirror bullets, optional summary tweak, skills reorder).

#### 6. Render PDF on the panel

Do **not** call `render_pdf` in Claude by default — open the company workspace and **Re-render PDF** (saves tokens). Call `render_pdf` in chat only if you explicitly want it.

#### 7. After applying

Upload the PDF to the ATS manually, then:

```text
mark_applied(country, company, url, applied=true)
```

#### Add a company (panel parity)

Same inputs as the panel **Add company** dialog:

```text
list_supported_countries()          # optional — country hints
list_ats_types()                    # optional — or use ats="auto"
add_company(
  name="Example GmbH",
  careers_url="https://boards.greenhouse.io/example",
  country="germany",                # or "auto" / omit to detect
  ats="auto",                       # or greenhouse, lever, ashby, …
  locations_json='[{"country":"germany","city":"Berlin"}]'  # optional
)
```

Returns `workspace_path` (e.g. `/company/germany/example-gmbh`) for the panel company workspace. After adding, run a **Fetch** on the panel (or `scrape_jobs.py`) to load open roles.

#### Add a position (manual / LinkedIn-only)

When a company is already in the catalog but a role only appears elsewhere (e.g. LinkedIn), **add the role and its JD in one step**. The JD is stored in Postgres and returned by `get_job_context` — same as a panel-fetched description.

```text
add_position(
  country="uk",
  company="brightpattern",           # name or slug
  title="Senior Backend Engineer",
  url="https://www.linkedin.com/jobs/view/1234567890",
  location="London, UK",             # optional
  description_text="Full JD paste…",  # required for LinkedIn / Indeed / Glassdoor
  posted_at="2025-06-15"             # required for LinkedIn / Indeed / Glassdoor (listing date)
)
```

**Flow**

```mermaid
flowchart LR
  A[User shares LinkedIn role + JD in chat] --> B[add_position with description_text]
  B --> C[get_job_context — has_description true]
  C --> D[Reframe pipeline phases]
```

- **LinkedIn / Indeed / Glassdoor:** `description_text` and **`posted_at`** are **required**. Paste the full posting text and the **date shown on the listing** (`YYYY-MM-DD` or ISO datetime) — not today's date. Stored as `fetched` / `last_seen` for board sort.
- **Direct ATS URL:** `description_text` optional — omit only if you will **Fetch job description** on the panel or call `save_position_description` before phase 1.
- **Duplicate URL:** idempotent add; fuller JD replaces or appends to an existing description.
- **Follow-up JD in chat:** `save_position_description(country, company, url, description_text)` merges into the catalog row.
- **Fix mistakes:** `update_position(...)` overwrites title, `new_url`, location, and/or `description_text`; `save_position_description(..., overwrite=true)` replaces the JD only.

Returns `has_description`, `needs_description`, `needs_fetch`, `description_saved`, `posted_at`, canonical `url`, and `workspace_path`. Then `get_job_context` / `save_tailored_tex` use the returned `url`.

#### Fix / overwrite catalog data

```text
update_position(
  country="armenia",
  company="bright-pattern",
  url="<current posting url from get_job_context>",
  title="Corrected title",              # optional
  new_url="https://…",                  # optional — fixes wrong link
  location="Yerevan, Armenia",           # optional
  description_text="Full corrected JD…",  # optional — replaces, does not merge
  posted_at="2025-06-15",                # optional — fix posting date
  clear_description=false                 # true to wipe JD
)

save_position_description(country, company, url, description_text, overwrite=true)
```

#### Paste into Claude Desktop

```text
Apply using the mcp-resume-reframe skill to the first job in my UK queue:
1. list_application_queue(country="uk") and pick one job
2. get_job_context + get_reframe_pipeline — use description_text as the JD
3. If has_description is false, ask me to fetch the JD on the panel before phase 1
4. Run pipeline phase 1 only — markdown, then ask me to go ahead
5. Continue one phase per turn until I accept the full draft
6. save_tailored_tex after final acceptance — do not render_pdf; I'll render on the panel
```

### Workflow (short)

1. Setup on `/apply`: master resumes + profile + **five** gated pipeline prompts.
2. Pin job or mark **looking to apply** on the panel.
3. Claude: bootstrap MCP → **one phase per turn** → user checkpoints → **add** mirror bullets to master (never trim without permission).
4. After final acceptance: `save_tailored_tex` → optional `validate_tex`.
5. Panel: **Re-render PDF** → upload manually → `mark_applied`.

---

## Validation

1. **Structure** — document env, balanced `\begin`/`\end`, max 400 lines.
2. **Facts** — no new years or employers vs the chosen master resume.

---

## Remote MCP (Claude / Cursor, OAuth)

Production endpoint: `https://mcp.kuchup.com/mcp` (Streamable HTTP + MCP OAuth). Each user signs in with their **panel username/password** on our login page; tokens are scoped to that `user_id`.

**Claude (web → mobile)**

1. Panel → `/apply` → **Connect MCP** → copy the MCP URL.
2. [Customize → Connectors](https://claude.ai/customize/connectors) → Add custom connector → paste URL only → Connect.
3. Complete login/consent on `mcp.kuchup.com`.
4. On the phone: chat **+** → Connectors → enable (no URL paste on mobile).

**Cursor**

```json
{
  "mcpServers": {
    "kuchup": {
      "url": "https://mcp.kuchup.com/mcp"
    }
  }
}
```

Settings → MCP → **Connect** → same Kuchup login page.

**Optional API tokens** on `/apply` → Connect MCP are for scripts only (`Authorization: Bearer kch_…`). Do not paste them into Claude when using OAuth.

Local HTTP for development:

```bash
MCP_PUBLIC_BASE_URL=http://127.0.0.1:10001 MCP_HTTP_PORT=10001 python3 scripts/mcp_http_server.py
```

Local **stdio** Claude Desktop (`scripts/mcp_server.py` + `MCP_USERNAME`) remains supported.

## Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `MCP_USERNAME` | `admin` | Panel user (stdio only) |
| `MCP_USER_ID` | (unset) | Override user id (stdio only) |
| `MCP_LATEX_CMD` | `tectonic` | LaTeX binary |
| `DATABASE_URL` | (required) | Same as panel |
| `MCP_PUBLIC_BASE_URL` | `http://127.0.0.1:10001` | Public origin for OAuth redirects / metadata |
| `MCP_HTTP_HOST` | `0.0.0.0` | HTTP bind host |
| `MCP_HTTP_PORT` | `10001` | HTTP bind port |

### Troubleshooting

**Profile or resumes look empty / null in Claude**

1. Call `get_mcp_status` — shows which panel user MCP reads (`user_id`, `username`) and whether profile / master resumes exist.
2. MCP defaults to `MCP_USERNAME=admin`. Data saved on `/apply` is per **logged-in panel user**. If you sign in as a different account, set `MCP_USERNAME` (or `MCP_USER_ID`) in Claude Desktop’s MCP server `env` to match.
3. Ensure Claude Desktop’s MCP config includes the same `DATABASE_URL` as the panel (`.env` is loaded from the repo root by `scripts/mcp_server.py`, but explicit `env` in the config is clearer).

**Claude says there is no pipeline tool**

Correct: there is no `run_pipeline` tool. Prompts are **data**, not an executable tool.

1. Call **`get_reframe_pipeline`** (or **`get_application_profile`** and read the `pipeline` field).
2. Run each string in `pipeline[]` **in order in chat** before `get_master_resume` / reframing.
3. Restart Claude Desktop (or reload MCP) after server updates so `get_reframe_pipeline` appears in the tool list.

**`get_job_context` shows `null` for `visa_sponsorship` or `ats_score`**

Normal when the catalog or your tracking has no value for those fields.

**`description_text` is empty / `needs_fetch` is true**

The JD is not stored in the catalog yet. On the panel, open `/company/<country>/<company-slug>`, select the position, click **Fetch job description**, then call `get_job_context` again. Do not scrape the ATS URL in Claude chat. After a local enrich run, `description_text` is filled automatically for newly fetched jobs.

**Tailored CV not visible on company workspace**

1. Confirm MCP and panel use the **same user** (`get_mcp_status` → `username` must match your panel login; set `MCP_USERNAME` in Claude Desktop config if not `admin`).
2. Country keys are stored **lowercase** (`germany`, not `Germany`). Older rows are fixed by migration `mcp_applications_country_lower_v1`; new saves normalize automatically.
3. Open `/company/<country>/<company-slug>` (e.g. `/company/germany/talon.one`) and select the **exact position** Claude tailored — CV badge appears per role, not per company.
4. `has_tailored_tex` joins on `idempotency_key` from the catalog job URL. If Claude used a different URL for the same role, call `get_job_context` and use the `url` it returns for `save_tailored_tex`.

**Claude refuses to save / says job is not in the application queue**

`save_tailored_tex` does **not** require pinned or looking-to-apply. Restart Claude Desktop after MCP updates so tool descriptions refresh. Then:

1. Call `get_job_context(country, company, url)` — confirm `can_save_tailored_tex` is true.
2. Call `save_tailored_tex` with the **exact** `country`, `company`, and `url` from that response (overwrites prior tailored tex).
3. Queue membership (`list_application_queue`) is only for **discovering** jobs, not for gating save.

**PDF render fails or returns almost no log**

`tectonic` (default via `MCP_LATEX_CMD`) cannot load `fontawesome5` — it aborts before a useful error. Compile **strips fontawesome packages, `\\fa…` icons, and unicode em-dashes** in a temp copy only (Postgres `.tex` unchanged).

1. Set **`MCP_LATEX_CMD`** to tectonic’s **full path** in Claude Desktop MCP `env` (e.g. `/opt/homebrew/bin/tectonic`) — the GUI app often has no Homebrew on `PATH`. See `claude_desktop_config.json.example`. Production EC2 panel already ships tectonic in `Dockerfile.ec2` (no Homebrew path needed there; see [ec2-panel.md](../operations/ec2-panel.md)).
2. Restart Claude Desktop after MCP server code changes.
3. Panel **Re-render PDF** on the company workspace shows a progress overlay while compiling (~10s).
4. If render still fails, read `validate_tex` first, then the error text from **Re-render PDF** or `render_pdf` log.

**`save_tailored_tex` fails: missing `pdf_bytes` column (or other schema error)**

The MCP server runs `init_db()` migrations on startup (`scripts/mcp_server.py`). If Claude Desktop was connected before you pulled MCP changes, restart Claude Desktop so the MCP process restarts and applies `mcp_master_resumes_pdf_v1` (adds `pdf_bytes` / `pdf_updated_at` on `mcp_master_resumes`). Alternatively start the panel once (`python3 scripts/panel_server.py`) — it also runs migrations on startup.

---

## Tests

```bash
pytest tests/mcp -o addopts=
```

---

## Package layout

```text
relocation_jobs/mcp/
  repo.py
  service.py
  server.py
  http_app.py
  oauth_provider.py
  oauth_repo.py
  oauth_pages.py
  context.py
  validate.py
  render.py
  types.py

scripts/mcp_server.py
scripts/mcp_http_server.py
tests/mcp/
```
