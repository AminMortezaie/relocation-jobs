from __future__ import annotations

import json
from pathlib import Path

from relocation_jobs.core.db import db_transaction
from relocation_jobs.core.job_identity import job_idempotency_key, stamp_job_identity


def seed_country(country_key: str, fixture_path: Path) -> dict:
    data = json.loads(fixture_path.read_text(encoding="utf-8"))
    companies = data.get("companies") or []
    with db_transaction() as conn:
        conn.execute(
            """
            INSERT INTO country_meta (country, source, fetched, updated, jobs_fetched, total, last_fetch_new_jobs)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (country) DO UPDATE SET
                source = EXCLUDED.source,
                fetched = EXCLUDED.fetched,
                updated = EXCLUDED.updated,
                jobs_fetched = EXCLUDED.jobs_fetched,
                total = EXCLUDED.total,
                last_fetch_new_jobs = EXCLUDED.last_fetch_new_jobs
            """,
            (
                country_key,
                data.get("source") or "",
                data.get("fetched") or "",
                data.get("updated") or "",
                data.get("jobs_fetched") or "",
                data.get("total") or len(companies),
                int(data.get("last_fetch_new_jobs") or 0),
            ),
        )
        for company in companies:
            name = (company.get("name") or "").strip()
            if not name:
                continue
            row = conn.execute(
                """
                INSERT INTO companies (
                    country, name, city, size, careers_url, ats_type, ats_url, updated
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (country, name) DO UPDATE SET
                    city = EXCLUDED.city,
                    size = EXCLUDED.size,
                    careers_url = EXCLUDED.careers_url,
                    ats_type = EXCLUDED.ats_type,
                    ats_url = EXCLUDED.ats_url,
                    updated = EXCLUDED.updated
                RETURNING id
                """,
                (
                    country_key,
                    name,
                    company.get("city") or "",
                    company.get("size") or "",
                    company.get("careers_url") or "",
                    company.get("ats_type") or "",
                    company.get("ats_url") or "",
                    company.get("updated") or data.get("updated") or "",
                ),
            ).fetchone()
            company_id = int(row["id"])
            conn.execute("DELETE FROM matching_jobs WHERE company_id = %s", (company_id,))
            for job in company.get("matching_jobs") or []:
                stamp_job_identity(job)
                conn.execute(
                    """
                    INSERT INTO matching_jobs (
                        company_id, title, url, idempotency_key, fetched, last_seen
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        company_id,
                        job.get("title") or "",
                        job.get("url") or "",
                        job.get("idempotency_key") or job_idempotency_key(job.get("url", "")),
                        job.get("fetched") or "",
                        job.get("last_seen") or "",
                    ),
                )
    return data
