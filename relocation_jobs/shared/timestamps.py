from __future__ import annotations


def normalize_ts_for_sort(ts: str) -> str:
    ts = (ts or "").strip()
    if not ts:
        return "0000-00-00T00:00:00"
    if len(ts) == 10 and ts[4] == "-" and ts[7] == "-":
        return f"{ts}T00:00:00"
    return ts.replace("Z", "+00:00")


def job_fetched_ts(job: dict) -> str:
    return (job.get("fetched") or "").strip()


def job_activity_ts(job: dict) -> str:
    return job_fetched_ts(job) or (job.get("last_seen") or "").strip()


def company_newest_job_fetched(board_jobs: list[dict], company: dict | None = None) -> str:
    """Newest-first board sort: max job.fetched over open-board roles only."""
    job_ts = [job_fetched_ts(j) for j in board_jobs if job_fetched_ts(j)]
    if job_ts:
        return max(job_ts, key=normalize_ts_for_sort)
    if company is not None:
        return (company.get("added") or "").strip()
    return ""


def company_activity_ts(company: dict, stored_jobs: list[dict]) -> str:
    """Catalog-wide max job.fetched (ignores per-user buckets). Prefer company_newest_job_fetched for board sort."""
    return company_newest_job_fetched(stored_jobs, company)
