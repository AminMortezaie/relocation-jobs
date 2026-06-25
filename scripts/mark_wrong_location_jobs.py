#!/usr/bin/env python3
"""One-shot: persist wrong-location catalog jobs as not_for_me in job_tracking."""

from __future__ import annotations

import argparse
import sys

from relocation_jobs.catalog.repo import load_country_catalog
from relocation_jobs.core.db import get_connection
from relocation_jobs.core.location_tags import job_fails_office_location_gate, sync_company_location_fields
from relocation_jobs.core.paths import SUPPORTED_COUNTRIES
from relocation_jobs.panel.tracking import resolve_track
from relocation_jobs.positions import repo as positions_repo
from relocation_jobs.positions.types import TrackingFlags
from relocation_jobs.users.repo import load_job_tracking


def _catalog_url(job: dict) -> str:
    return (job.get("url") or "").strip()


def _should_mark(track: dict | None) -> bool:
    flags = TrackingFlags.from_row(track)
    if flags.not_for_me and flags.not_for_me_reason == "wrong_location":
        return False
    if flags.not_for_me and flags.not_for_me_reason not in ("", "wrong_location"):
        return False
    return True


def find_wrong_location_jobs(*, country_key: str | None = None) -> list[dict]:
    countries = [country_key] if country_key else list(SUPPORTED_COUNTRIES)
    hits: list[dict] = []
    for country in countries:
        data = load_country_catalog(country)
        if not data:
            continue
        for company in data.get("companies") or []:
            sync_company_location_fields(company, catalog_country=country)
            company_name = (company.get("name") or "").strip()
            if not company_name:
                continue
            for job in company.get("matching_jobs") or []:
                fails, reason = job_fails_office_location_gate(
                    job, company, catalog_country=country,
                )
                if not fails:
                    continue
                url = _catalog_url(job)
                if not url:
                    continue
                hits.append({
                    "country": country,
                    "company_name": company_name,
                    "job_url": url,
                    "title": (job.get("title") or "").strip(),
                    "reason": reason or "location mismatch",
                })
    return hits


def list_user_ids() -> list[int]:
    rows = get_connection().execute("SELECT id FROM users ORDER BY id").fetchall()
    return [int(row["id"]) for row in rows]


def mark_for_user(user_id: int, hits: list[dict], *, dry_run: bool) -> list[dict]:
    job_tracking = load_job_tracking(user_id)
    marked: list[dict] = []
    for hit in hits:
        track = resolve_track(
            job_tracking,
            country=hit["country"],
            company_name=hit["company_name"],
            job={"url": hit["job_url"]},
        )
        if not _should_mark(track or None):
            continue
        if dry_run:
            marked.append({**hit, "user_id": user_id})
            continue
        positions_repo.set_not_for_me(
            user_id,
            hit["country"],
            hit["company_name"],
            hit["job_url"],
            not_for_me=True,
            reason="wrong_location",
        )
        marked.append({**hit, "user_id": user_id})
    return marked


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--country", help="Limit to one country key (e.g. germany)")
    parser.add_argument("--user-id", type=int, help="Limit to one user id (default: all users)")
    parser.add_argument("--dry-run", action="store_true", help="List matches without writing")
    args = parser.parse_args(argv)

    if args.country and args.country not in SUPPORTED_COUNTRIES:
        print(f"Unknown country: {args.country}", file=sys.stderr)
        return 1

    hits = find_wrong_location_jobs(country_key=args.country)
    print(f"Catalog wrong-location jobs: {len(hits)}")
    for hit in hits[:20]:
        print(f"  [{hit['country']}] {hit['company_name']} — {hit['title'][:60]}")
    if len(hits) > 20:
        print(f"  … and {len(hits) - 20} more")

    user_ids = [args.user_id] if args.user_id else list_user_ids()
    if not user_ids:
        print("No users in database.", file=sys.stderr)
        return 1

    total_marked = 0
    for user_id in user_ids:
        marked = mark_for_user(user_id, hits, dry_run=args.dry_run)
        total_marked += len(marked)
        verb = "would mark" if args.dry_run else "marked"
        print(f"User {user_id}: {verb} {len(marked)} position(s)")

    print(f"Done — {total_marked} tracking row(s) {'would be ' if args.dry_run else ''}updated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
