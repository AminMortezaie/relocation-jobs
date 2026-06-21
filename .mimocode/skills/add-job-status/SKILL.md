---
name: add-job-status
description: Add a new job status/tag (like "seen", "applied", "rejected") across the full stack: DB, API, and frontend.
---

# Add Job Status Column

When the user wants to add a new status tag to jobs (e.g. "seen", "looking_to_apply"), edit these files in order:

## 1. `relocation_jobs/db.py`

### Add column to schema (in `_ensure_schema`)

```python
conn.execute(
    "ALTER TABLE job_tracking ADD COLUMN IF NOT EXISTS {status} INTEGER DEFAULT 0"
)
conn.execute(
    "ALTER TABLE job_tracking ADD COLUMN IF NOT EXISTS {status}_date TEXT"
)
```

### Add setter function

```python
def set_job_{status}_db(
    user_id: int,
    country: str,
    company_name: str,
    job_url: str,
    value: bool,
) -> None:
    with get_conn() as conn:
        col = "{status}"
        date_col = "{status}_date"
        _ensure_schema(conn)
        conn.execute(
            f"UPDATE job_tracking SET {col} = ?, {date_col} = CASE WHEN ? = 1 THEN date('now') ELSE NULL END "
            "WHERE user_id = ? AND country = ? AND company_name = ? AND job_url = ?",
            (int(value), int(value), user_id, country, company_name, job_url),
        )
```

## 2. `relocation_jobs/panel_data.py`

### Add to `_job_dict` return

```python
"{status}": bool(track.get("{status}", 0)) if track else False,
"{status}_date": track.get("{status}_date") if track else None,
```

### Add public function

```python
def set_job_{status}(
    country_key: str,
    company_name: str,
    job_url: str,
    value: bool,
    *,
    user_id: int,
) -> None:
    set_job_{status}_db(user_id, country_key, company_name, job_url, value)
```

### Update imports

Add `set_job_{status}_db` to the import from `.db`.

## 3. `relocation_jobs/panel_server.py`

### Add API endpoint

```python
@app.post("/api/jobs/{status}")
@login_required
def api_jobs_{status}():
    ...
```

### Update imports

Add `set_job_{status}` to the import from `.panel_data`.

## 4. `relocation_jobs/static/js/api.js`

```javascript
export async function markJob{Status}(country, company, url) {
  const res = await apiFetch("/api/jobs/{status}", {
    method: "POST",
    body: JSON.stringify({ country, company_name: company, job_url: url }),
  });
  return res;
}
```

## 5. `relocation_jobs/static/js/render.js`

### Add badge to statusBadges array

```javascript
j.{status} ? `<span class="badge {status}">{Status}${j.{status}_date ? ` · ${escapeHtml(j.{status}_date)}` : ""}</span>` : "",
```

### Add position card class

```javascript
j.{status} ? " position-{status}" : "",
```

## 6. `relocation_jobs/static/js/events.js`

### Import the new API function

```javascript
import { markJob{Status} } from "./api.js";
```

### Add click handler

```javascript
const jobTitleLink = e.target.closest(".job-title");
if (jobTitleLink) {
  // ... existing logic
}
```

## 7. `relocation_jobs/static/styles.css`

### Badge style

```css
.badge.{status} { background: var(--{status}-soft); color: #COLOR; border-color: rgba(R, G, B, 0.2); }
```

### Position card style

```css
.position-card.position-{status} {
  border-color: color-mix(in srgb, var(--{status}) 30%, var(--border));
}
```

## 8. Run tests

```bash
python3 -m pytest tests/ -x
```
