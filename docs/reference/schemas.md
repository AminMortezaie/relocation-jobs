# Schema architecture

Pydantic models live in `relocation_jobs/schemas/`. Postgres JSON/JSONB columns and API contracts are validated through these types at the repository and service boundaries.

## Layout

| Module | Purpose |
|--------|---------|
| `common.py` | `BaseSchema`, shared JSON helpers |
| `location.py` | `Location` — country + city |
| `job.py` | `MatchingJob`, `JobLocation` — catalog job rows |
| `company.py` | `Company`, `CompanyInDB`, `CompanyCreateInput`, `CompanyResponse` |
| `country.py` | `CountryCatalog`, `CountryMeta` — per-country catalog envelope |
| `job_response.py` | `JobStatusUpdate` — panel mutation responses |

## Data stores

| Store | Tables / files | Schema usage |
|-------|----------------|--------------|
| Catalog (Postgres) | `companies`, `matching_jobs`, `country_meta` | `CompanyInDB`, `MatchingJob`, `Location` on read/write in `catalog/` |
| User tracking (Postgres) | `job_tracking`, `company_tracking`, `users`, `fetch_runs` | SQL in `users/repo.py`, `positions/`; panel overlay at read time |
| Custom cities (disk) | `data/custom_cities.json` via `PANEL_DATA_DIR` | `Location`-shaped dicts in `location_tags.py` |

## Catalog read path

`catalog/repo.load_country_catalog(country_key)` returns a dict matching `CountryCatalog` shape:

```text
{
  "source", "fetched", "updated", "jobs_fetched", "total", "last_fetch_new_jobs",
  "companies": [ { ...Company fields..., "matching_jobs": [ ...MatchingJob... ] } ]
}
```

`panel/flatten.py` merges catalog jobs with per-user tracking and routes each job into exactly one bucket: `jobs`, `rejected_jobs`, or `not_for_me_jobs`.

## Service inputs

- `CompanyCreateInput` — validated in `companies/service.add_company()` and related mutations
- `CompanyResponse` — return type for company CRUD operations

## Naming note

Country keys (`uk`, `germany`, …) are defined in `core/paths.SUPPORTED_COUNTRIES`. Legacy git-archive filenames (`uk_companies.json`, …) are `COUNTRY_ARCHIVE_FILENAMES` only — not read at runtime.
