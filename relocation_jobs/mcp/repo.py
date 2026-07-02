from __future__ import annotations

import json
import re

from relocation_jobs.core.db import _utc_now, db_read, db_transaction
from relocation_jobs.mcp.types import ApplicationProfile, MasterResumeSummary

_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _row(row) -> dict:
    return dict(row) if row else {}


def normalize_master_resume_slug(slug: str) -> str:
    raw = (slug or "").strip().lower()
    if not raw:
        raise ValueError("master resume slug is required")
    cleaned = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")
    if not cleaned or not _SLUG_RE.match(cleaned):
        raise ValueError(f"invalid master resume slug: {slug!r}")
    return cleaned


def company_slug(name: str) -> str:
    raw = (name or "").strip().lower()
    cleaned = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")
    return cleaned


def resolve_company_name_by_slug(country_key: str, slug: str) -> str | None:
    target = company_slug(slug)
    if not target:
        return None
    with db_read() as conn:
        rows = conn.execute(
            "SELECT name FROM companies WHERE country = %s",
            (country_key.strip().lower(),),
        ).fetchall()
    for row in rows:
        name = (row["name"] or "").strip()
        if company_slug(name) == target:
            return name
    return None


def get_user_documents(user_id: int) -> dict | None:
    with db_read() as conn:
        row = conn.execute(
            """
            SELECT profile_json, updated_at
            FROM mcp_user_documents
            WHERE user_id = %s
            """,
            (user_id,),
        ).fetchone()
    return _row(row) if row else None


def list_master_resumes(user_id: int) -> list[MasterResumeSummary]:
    with db_read() as conn:
        rows = conn.execute(
            """
            SELECT slug, label, updated_at
            FROM mcp_master_resumes
            WHERE user_id = %s
            ORDER BY slug
            """,
            (user_id,),
        ).fetchall()
    return [
        MasterResumeSummary(
            slug=row["slug"],
            label=(row.get("label") or "").strip(),
            updated_at=(row.get("updated_at") or "").strip(),
        )
        for row in rows
    ]


def read_master_resume(user_id: int, slug: str) -> str:
    key = normalize_master_resume_slug(slug)
    with db_read() as conn:
        row = conn.execute(
            """
            SELECT content
            FROM mcp_master_resumes
            WHERE user_id = %s AND slug = %s
            """,
            (user_id, key),
        ).fetchone()
    if row is None or not (row["content"] or "").strip():
        raise LookupError(f"Master resume not found: {key}")
    return row["content"]


def save_master_resume(
    user_id: int,
    slug: str,
    content: str,
    *,
    label: str = "",
) -> dict:
    key = normalize_master_resume_slug(slug)
    now = _utc_now()
    with db_transaction() as conn:
        conn.execute(
            """
            INSERT INTO mcp_master_resumes (user_id, slug, label, content, updated_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (user_id, slug) DO UPDATE SET
                label = EXCLUDED.label,
                content = EXCLUDED.content,
                updated_at = EXCLUDED.updated_at
            """,
            (user_id, key, (label or "").strip(), content, now),
        )
    return {"user_id": user_id, "slug": key, "label": (label or "").strip(), "updated_at": now}


def read_profile(user_id: int) -> ApplicationProfile:
    docs = get_user_documents(user_id)
    if docs is None:
        raise LookupError("Application profile not set. Use save_application_profile first.")
    raw = json.loads(docs.get("profile_json") or "{}")
    return ApplicationProfile(**raw)


def save_profile(user_id: int, profile: ApplicationProfile) -> dict:
    now = _utc_now()
    payload = json.dumps(profile.model_dump())
    with db_transaction() as conn:
        conn.execute(
            """
            INSERT INTO mcp_user_documents (user_id, profile_json, updated_at)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
                profile_json = EXCLUDED.profile_json,
                updated_at = EXCLUDED.updated_at
            """,
            (user_id, payload, now),
        )
    return {"user_id": user_id, "updated_at": now}


def get_application(user_id: int, idempotency_key: str) -> dict | None:
    with db_read() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM mcp_applications
            WHERE user_id = %s AND idempotency_key = %s
            """,
            (user_id, idempotency_key),
        ).fetchone()
    return _row(row) if row else None


def list_applications_for_company(
    user_id: int,
    country: str,
    company: str,
) -> list[dict]:
    with db_read() as conn:
        rows = conn.execute(
            """
            SELECT idempotency_key, tailored_tex, pdf_bytes, master_resume_slug,
                   tailored_tex_updated_at, pdf_updated_at, job_url
            FROM mcp_applications
            WHERE user_id = %s AND country = %s AND company_name = %s
            """,
            (user_id, country.strip().lower(), company.strip()),
        ).fetchall()
    return [_row(row) for row in rows]


def load_application_summaries(
    user_id: int,
    *,
    country: str | None = None,
) -> dict[str, dict]:
    sql = """
        SELECT idempotency_key, tailored_tex, pdf_bytes, master_resume_slug
        FROM mcp_applications
        WHERE user_id = %s
    """
    params: list = [user_id]
    if country:
        sql += " AND country = %s"
        params.append(country.strip().lower())
    with db_read() as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()
    summaries: dict[str, dict] = {}
    for row in rows:
        key = (row["idempotency_key"] or "").strip()
        if not key:
            continue
        summaries[key] = {
            "has_tailored_tex": bool((row.get("tailored_tex") or "").strip()),
            "has_pdf": bool(row.get("pdf_bytes")),
            "master_resume_slug": (row.get("master_resume_slug") or "").strip(),
        }
    return summaries


def read_pdf_bytes(user_id: int, idempotency_key: str) -> bytes:
    row = get_application(user_id, idempotency_key)
    if row is None or not row.get("pdf_bytes"):
        raise LookupError(f"No PDF for application {idempotency_key}")
    data = row["pdf_bytes"]
    if isinstance(data, memoryview):
        return bytes(data)
    return data


def upsert_application_shell(
    user_id: int,
    idempotency_key: str,
    *,
    country: str,
    company: str,
    url: str,
    master_resume_slug: str = "",
) -> dict:
    now = _utc_now()
    slug = ""
    if master_resume_slug.strip():
        slug = normalize_master_resume_slug(master_resume_slug)
    with db_transaction() as conn:
        conn.execute(
            """
            INSERT INTO mcp_applications (
                user_id, idempotency_key, country, company_name, job_url,
                master_resume_slug, meta_json, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, '{}', %s)
            ON CONFLICT (user_id, idempotency_key) DO UPDATE SET
                country = EXCLUDED.country,
                company_name = EXCLUDED.company_name,
                job_url = EXCLUDED.job_url,
                master_resume_slug = COALESCE(NULLIF(EXCLUDED.master_resume_slug, ''), mcp_applications.master_resume_slug),
                updated_at = EXCLUDED.updated_at
            """,
            (user_id, idempotency_key, country, company, url, slug, now),
        )
    return get_application(user_id, idempotency_key) or {}


def save_tailored_tex(
    user_id: int,
    idempotency_key: str,
    content: str,
    *,
    country: str,
    company: str,
    url: str,
    master_resume_slug: str,
) -> dict:
    now = _utc_now()
    slug = normalize_master_resume_slug(master_resume_slug)
    read_master_resume(user_id, slug)
    upsert_application_shell(
        user_id,
        idempotency_key,
        country=country,
        company=company,
        url=url,
        master_resume_slug=slug,
    )
    with db_transaction() as conn:
        conn.execute(
            """
            UPDATE mcp_applications
            SET tailored_tex = %s,
                master_resume_slug = %s,
                tailored_tex_updated_at = %s,
                updated_at = %s
            WHERE user_id = %s AND idempotency_key = %s
            """,
            (content, slug, now, now, user_id, idempotency_key),
        )
    return {
        "user_id": user_id,
        "idempotency_key": idempotency_key,
        "master_resume_slug": slug,
        "updated_at": now,
    }


def read_tailored_tex(user_id: int, idempotency_key: str) -> str:
    row = get_application(user_id, idempotency_key)
    if row is None or not (row.get("tailored_tex") or "").strip():
        raise LookupError(f"No tailored resume for application {idempotency_key}")
    return row["tailored_tex"]


def save_pdf(user_id: int, idempotency_key: str, pdf_bytes: bytes) -> dict:
    now = _utc_now()
    with db_transaction() as conn:
        conn.execute(
            """
            UPDATE mcp_applications
            SET pdf_bytes = %s, pdf_updated_at = %s, updated_at = %s
            WHERE user_id = %s AND idempotency_key = %s
            """,
            (pdf_bytes, now, now, user_id, idempotency_key),
        )
    return {
        "user_id": user_id,
        "idempotency_key": idempotency_key,
        "pdf_bytes": len(pdf_bytes),
    }


def touch_application_meta(
    user_id: int,
    idempotency_key: str,
    *,
    country: str,
    company: str,
    url: str,
    event: str,
    extra: dict | None = None,
) -> dict:
    now = _utc_now()
    upsert_application_shell(user_id, idempotency_key, country=country, company=company, url=url)
    row = get_application(user_id, idempotency_key) or {}
    base = json.loads(row.get("meta_json") or "{}")
    base.update({
        "country": country,
        "company": company,
        "url": url,
        "idempotency_key": idempotency_key,
        "updated_at": now,
        event: now,
    })
    if extra:
        base.update(extra)
    with db_transaction() as conn:
        conn.execute(
            """
            UPDATE mcp_applications
            SET meta_json = %s, updated_at = %s
            WHERE user_id = %s AND idempotency_key = %s
            """,
            (json.dumps(base), now, user_id, idempotency_key),
        )
    return base
