from __future__ import annotations

from datetime import date, datetime


def normalize_ts_for_sort(ts: str) -> str:
    ts = (ts or "").strip()
    if not ts:
        return "0000-00-00T00:00:00"
    if len(ts) == 10 and ts[4] == "-" and ts[7] == "-":
        return f"{ts}T00:00:00"
    return ts.replace("Z", "+00:00")


def normalize_posted_at(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        raise ValueError("posted_at is required")
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        date.fromisoformat(text)
        return text
    normalized = text.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(
            f"posted_at must be YYYY-MM-DD or ISO datetime (got {raw!r})"
        ) from exc
    if (
        dt.hour == 0
        and dt.minute == 0
        and dt.second == 0
        and dt.microsecond == 0
    ):
        return dt.date().isoformat()
    return dt.isoformat()


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
