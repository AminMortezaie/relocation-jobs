---
name: write-app-tests
description: >-
  Writes pytest coverage for every user-visible or business scenario added to
  the relocation_jobs app. Use when implementing features, bug fixes, API
  routes, panel data rules, scrape filters, location tags, or any app behavior
  change — and before marking the task done.
---

# Write App Tests

Every app change ships with tests. **Do not finish a feature until each new scenario has a test and pytest passes.**

## When this applies

Treat each of these as a **scenario** that needs at least one test:

- New or changed API route (success, validation error, auth)
- New or changed business rule (filter, merge, state transition)
- New persistence (file, DB column, catalog field)
- Edge case you handled in code (empty input, duplicate, unsupported country)
- Regression you fixed

Skip tests only when the user explicitly says not to, or the change is docs/comments-only.

## Workflow

Copy and track:

```
Test progress:
- [ ] List scenarios introduced by this change
- [ ] Pick test file(s) per mapping below
- [ ] Add unit tests for pure logic
- [ ] Add integration tests for API/DB paths
- [ ] Run targeted pytest, then fix failures
- [ ] Update tests/BUSINESS_RULES.md if a numbered rule changed
```

### 1. Enumerate scenarios

From the diff, write a short list before coding tests. Example for `POST /api/locations`:

| Scenario | Expected |
|----------|----------|
| Valid custom city | 200, persisted, appears in picker |
| Duplicate city | 200, idempotent, no duplicate entry |
| Invalid country | 400 |
| Empty city | 400 |

### 2. Choose test file(s)

| Layer | File | Use for |
|-------|------|---------|
| Pure helpers | `tests/test_<module>_full.py` or `tests/test_<module>.py` | `location_tags`, parsers, filters |
| Panel data / CRUD | `tests/test_panel_data_full.py` | catalog writes, `list_*`, company CRUD |
| Flask API | `tests/test_panel_api_full.py` | routes, status codes, JSON shape |
| DB tracking | `tests/test_db_full.py`, `tests/test_db_tracking.py` | applied/rejected/history |
| Job state rules | `tests/test_job_state_rules.py` | read overlay, buckets, orphans |
| End-to-end rules | `tests/test_business_rules_coverage.py` | rules 1–16 in `tests/BUSINESS_RULES.md` |
| Scrapers | `tests/test_scrape_*.py` | relevance, location gate, ATS |

Prefer extending an existing file over creating a new one unless the area has no file yet.

### 3. Use project fixtures

From `tests/conftest.py`:

| Fixture | Purpose |
|---------|---------|
| `tmp_data_dir` | Isolated `PANEL_DATA_DIR` + `PANEL_DB_PATH` |
| `db` | Init SQLite schema (includes `tmp_data_dir`) |
| `seeded_catalog` / `rich_catalog` | UK catalog seed for panel tests |
| `test_user` | User row for tracking tests |
| `auth_client` | Logged-in Flask test client |
| `app_client` | Unauthenticated client |

**Panel API tests:** `@pytest.mark.integration`, use `auth_client`, add `tmp_data_dir` when writing files under `data/`.

**Never** rely on the developer's real `data/panel.db` or live HTTP to ATS sites.

### 4. Write tests

**Naming:** `test_<behavior>_<condition>` — e.g. `test_locations_add_custom_city`, `test_job_matches_unsupported_and_outside_country`.

**Structure:**

```python
@pytest.mark.integration
def test_feature_happy_path(auth_client, tmp_data_dir):
    resp = auth_client.post("/api/...", json={...})
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True


def test_feature_rejects_invalid_country():
    with pytest.raises(ValueError):
        some_pure_function("invalid", "X")
```

**Cover per scenario:**

- Happy path (assert outputs, not just status code)
- Validation / error path (400, 404, `ValueError`)
- Idempotency or dedupe when relevant
- Persistence round-trip when data is saved to disk/DB

**Markers:** `@pytest.mark.integration` for DB+API; `@pytest.mark.network` only when mocking HTTP (see `pytest.ini`).

### 5. Run tests

Use the project venv:

```bash
.venv/bin/python -m pytest tests/test_location_tags_full.py::test_custom_cities_persist -q
.venv/bin/python -m pytest tests/test_panel_api_full.py::test_locations_add_custom_city -q
```

Run all tests touched by the change before finishing. For rule changes:

```bash
.venv/bin/python -m pytest tests/test_job_state_rules.py tests/test_business_rules_coverage.py -v
```

### 6. Update business rules (when applicable)

If behavior maps to `tests/BUSINESS_RULES.md`, update the rule text and the **Test mapping** table at the bottom of that file.

## Definition of done

A feature is **not complete** unless:

1. Every new scenario has a named test
2. Targeted pytest passes
3. No existing tests broken in the same area
4. `BUSINESS_RULES.md` updated when product rules changed

## Backend data preservation

When changing scrape, merge, enrich, or API read paths:

- **Preserve all job/company fields** already stored or scraped (`location`, `locations`, titles, dates, flags, etc.) unless the user explicitly says a field does not need to be kept.
- Do not drop listing metadata in `merge_matching_jobs`, catalog writes, or `_job_dict` — only omit fields the user asked to exclude.
- Surface preserved listing fields in the API (`location`, `job_city`, …) before adding UI that reads them.
- If a field was missing because merge dropped it, fix the backend first; do not fake it in the frontend alone.

## Anti-patterns

- UI-only verification with no backend test when logic lives in Python
- One vague test that doesn't map to a specific scenario
- Tests that depend on production data or network
- Leaving `TODO: test` for behavior added in the same task

## Examples

See [examples.md](examples.md) for patterns copied from this repo (custom cities, location gate, API errors).
