from __future__ import annotations


def normalize_ts_for_sort(ts: str) -> str:
    ts = (ts or "").strip()
    if not ts:
        return "0000-00-00T00:00:00"
    if len(ts) == 10 and ts[4] == "-" and ts[7] == "-":
        return f"{ts}T00:00:00"
    return ts.replace("Z", "+00:00")


def job_activity_ts(job: dict) -> str:
    return (job.get("fetched") or job.get("last_seen") or "").strip()


def company_activity_ts(company: dict, stored_jobs: list[dict]) -> str:
    updated = (company.get("updated") or "").strip()
    if updated:
        return updated
    job_ts = [job_activity_ts(j) for j in stored_jobs if job_activity_ts(j)]
    if job_ts:
        return max(job_ts, key=normalize_ts_for_sort)
    return (company.get("added") or "").strip()
