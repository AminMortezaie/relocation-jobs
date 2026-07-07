#!/usr/bin/env python3
"""Hide catalog jobs on the board that should have been excluded (location + title gates)."""

from __future__ import annotations

import argparse
import sys

from relocation_jobs.catalog.repo import load_country_catalog
from relocation_jobs.core.db import get_connection
from relocation_jobs.core.location_tags import job_fails_office_location_gate, sync_company_location_fields
from relocation_jobs.core.paths import supported_countries
from relocation_jobs.panel.tracking import resolve_track
from relocation_jobs.positions import repo as positions_repo
from relocation_jobs.positions.types import TrackingFlags
from relocation_jobs.scrape.relevance import explain_title_filter, is_relevant
from relocation_jobs.users.repo import load_job_tracking

USER_CHOSEN_REASONS = frozenset({"not_for_me", "no_relocation", "expired"})


def _catalog_url(job: dict) -> str:
    return (job.get("url") or "").strip()


def _exclusion_for_job(
    job: dict,
    company: dict,
    *,
    country_key: str,
) -> tuple[str, str] | None:
    fails_location, location_reason = job_fails_office_location_gate(
        job, company, catalog_country=country_key,
    )
    if fails_location:
        return "wrong_location", location_reason or "location mismatch"

    title = (job.get("title") or "").strip()
    if title and not is_relevant(title):
        return "not_for_me", explain_title_filter(title)

    return None


def find_excludable_jobs(*, country_key: str | None = None) -> list[dict]:
    countries = [country_key] if country_key else sorted(supported_countries())
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
                url = _catalog_url(job)
                if not url:
                    continue
                exclusion = _exclusion_for_job(job, company, country_key=country)
                if exclusion is None:
                    continue
                hide_reason, detail = exclusion
                hits.append({
                    "country": country,
                    "company_name": company_name,
                    "job_url": url,
                    "title": (job.get("title") or "").strip(),
                    "hide_reason": hide_reason,
                    "detail": detail,
                })
    return hits


def _should_mark(track: dict | None, hide_reason: str) -> bool:
    flags = TrackingFlags.from_row(track)
    if not flags.not_for_me:
        return True
    if flags.not_for_me_reason == hide_reason:
        return False
    if flags.not_for_me_reason == "wrong_location" and hide_reason == "not_for_me":
        return False
    if flags.not_for_me_reason in USER_CHOSEN_REASONS:
        return False
    if flags.not_for_me_reason in ("", "wrong_location", "not_for_me"):
        return flags.not_for_me_reason != hide_reason
    return False


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
        if not _should_mark(track or None, hit["hide_reason"]):
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
            reason=hit["hide_reason"],
        )
        marked.append({**hit, "user_id": user_id})
    return marked


def _summarize_hits(hits: list[dict]) -> None:
    by_reason: dict[str, int] = {}
    for hit in hits:
        by_reason[hit["hide_reason"]] = by_reason.get(hit["hide_reason"], 0) + 1
    parts = [f"{reason}={count}" for reason, count in sorted(by_reason.items())]
    print(f"Excludable catalog jobs: {len(hits)} ({', '.join(parts)})")
    for hit in hits[:25]:
        print(
            f"  [{hit['country']}] {hit['company_name']} — {hit['title'][:52]} "
            f"({hit['hide_reason']}: {hit['detail'][:50]})",
        )
    if len(hits) > 25:
        print(f"  … and {len(hits) - 25} more")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--country", help="Limit to one country key (e.g. germany)")
    parser.add_argument("--user-id", type=int, help="Limit to one user id (default: all users)")
    parser.add_argument("--dry-run", action="store_true", help="List matches without writing")
    args = parser.parse_args(argv)

    if args.country and args.country not in supported_countries():
        print(f"Unknown country: {args.country}", file=sys.stderr)
        return 1

    hits = find_excludable_jobs(country_key=args.country)
    _summarize_hits(hits)

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
