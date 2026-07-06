#!/usr/bin/env python3
"""Re-fetch stored job descriptions from ATS APIs (fixes noisy SmartRecruiters page scrapes)."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from relocation_jobs.catalog.repo import update_job_description_text
from relocation_jobs.core.db import db_read
from relocation_jobs.core.paths import SUPPORTED_COUNTRIES
from relocation_jobs.scrape.descriptions import (
    needs_ashby_refetch,
    needs_getyourguide_refetch,
    needs_recruitee_refetch,
    needs_smartrecruiters_refetch,
)
from relocation_jobs.scrape.job_text import _JOB_DETAIL_FETCHERS, fetch_job_description

API_ATS_TYPES = frozenset(_JOB_DETAIL_FETCHERS)
_BRANDED_CAREERS_URL_MARKERS = (
    "smartrecruiters.com",
    "getyourguide.careers",
    "ashbyhq.com",
)


def _ats_type_for_job(job: dict) -> str:
    ats_type = (job.get("ats_type") or "").strip().lower()
    url = (job.get("url") or "").lower()
    if "smartrecruiters.com" in url:
        return "smartrecruiters"
    if "getyourguide.careers" in url:
        return "greenhouse"
    if "ashbyhq.com" in url:
        return "ashby"
    return ats_type


def _is_api_backed_job(job: dict) -> bool:
    url = (job.get("url") or "").lower()
    ats_type = _ats_type_for_job(job)
    if ats_type in API_ATS_TYPES:
        return True
    return any(marker in url for marker in _BRANDED_CAREERS_URL_MARKERS)


def needs_description_refetch(job: dict) -> bool:
    if not _is_api_backed_job(job):
        return False
    ats_type = _ats_type_for_job(job)
    text = (job.get("description_text") or "").strip()
    url = (job.get("url") or "").lower()
    if "getyourguide.careers" in url or (
        ats_type == "greenhouse" and "getyourguide" in url
    ):
        return needs_getyourguide_refetch(text)
    if ats_type == "ashby" or "ashbyhq.com" in url:
        return needs_ashby_refetch(text)
    if ats_type == "smartrecruiters" or "smartrecruiters.com" in url:
        return needs_smartrecruiters_refetch(text)
    if ats_type == "recruitee" or "recruitee.com" in url:
        return needs_recruitee_refetch(text)
    if ats_type in API_ATS_TYPES:
        return not text
    return False


def list_jobs(*, country: str | None = None, ats_type: str | None = None) -> list[dict]:
    clauses = [
        "("
        "c.ats_type = ANY(%s)"
        " OR j.url ILIKE '%%smartrecruiters%%'"
        " OR j.url ILIKE '%%getyourguide.careers%%'"
        " OR j.url ILIKE '%%ashbyhq%%'"
        ")",
    ]
    params: list[object] = [list(API_ATS_TYPES)]
    if country:
        clauses.append("c.country = %s")
        params.append(country)
    if ats_type:
        if ats_type == "greenhouse":
            clauses.append(
                "(c.ats_type = %s OR j.url ILIKE '%%getyourguide.careers%%')"
            )
        elif ats_type == "smartrecruiters":
            clauses.append("(c.ats_type = %s OR j.url ILIKE '%%smartrecruiters%%')")
        elif ats_type == "ashby":
            clauses.append("(c.ats_type = %s OR j.url ILIKE '%%ashbyhq%%')")
        else:
            clauses.append("c.ats_type = %s")
        params.append(ats_type)
    sql = f"""
        SELECT
            j.idempotency_key,
            j.url,
            j.title,
            j.description_text,
            c.name AS company_name,
            c.country,
            c.ats_type
        FROM matching_jobs j
        JOIN companies c ON c.id = j.company_id
        WHERE {" AND ".join(clauses)}
        ORDER BY c.country, c.name, j.title
    """
    with db_read() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def refetch_job_description(job: dict) -> tuple[str, str]:
    key = (job.get("idempotency_key") or "").strip()
    url = (job.get("url") or "").strip()
    ats_type = _ats_type_for_job(job)
    if not key or not url:
        return "fail", "missing idempotency_key or url"
    if not _is_api_backed_job(job):
        return "skip", f"unsupported ats_type={ats_type or 'unknown'}"
    text = fetch_job_description(url, ats_type).strip()
    if not text:
        return "fail", "empty API response"
    if not update_job_description_text(key, text):
        return "fail", "database update failed"
    return "ok", f"{len(text)} chars"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--country", help="Limit to one country key (e.g. germany)")
    parser.add_argument(
        "--ats",
        choices=sorted(API_ATS_TYPES),
        help="Limit to one ATS type (e.g. smartrecruiters)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Refetch every API-backed job, not only missing/noisy descriptions",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List jobs that would be refetched without calling the API",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.25,
        help="Seconds to wait between API calls (default: 0.25)",
    )
    args = parser.parse_args(argv)

    if args.country and args.country not in SUPPORTED_COUNTRIES:
        print(f"Unknown country: {args.country}", file=sys.stderr)
        return 1

    jobs = list_jobs(country=args.country, ats_type=args.ats)
    to_refetch = [
        job for job in jobs
        if args.force or needs_description_refetch(job)
    ]
    print(f"API-backed catalog jobs: {len(jobs)} ({len(to_refetch)} to refetch)")

    ok = skip = fail = 0
    for job in jobs:
        if not args.force and not needs_description_refetch(job):
            skip += 1
            continue

        label = (
            f"[{job['country']}] {job['company_name']} — "
            f"{(job.get('title') or '')[:60]}"
        )
        if args.dry_run:
            print(f"would refetch: {label}")
            ok += 1
            continue

        status, detail = refetch_job_description(job)
        if status == "ok":
            ok += 1
            print(f"ok: {label} ({detail})")
        elif status == "skip":
            skip += 1
        else:
            fail += 1
            print(f"fail: {label} ({detail})", file=sys.stderr)
        if args.delay > 0:
            time.sleep(args.delay)

    verb = "would refetch" if args.dry_run else "refetched"
    print(f"Done — {ok} {verb}, {skip} skipped, {fail} failed.")
    return 1 if fail and not ok else 0


if __name__ == "__main__":
    raise SystemExit(main())
