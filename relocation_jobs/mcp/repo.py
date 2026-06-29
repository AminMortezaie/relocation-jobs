from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from relocation_jobs.mcp import paths
from relocation_jobs.mcp.types import ApplicationProfile


def read_master_resume() -> str:
    paths.ensure_data_layout()
    return paths.master_resume_path().read_text(encoding="utf-8")


def read_profile() -> ApplicationProfile:
    paths.ensure_data_layout()
    raw = json.loads(paths.profile_path().read_text(encoding="utf-8"))
    return ApplicationProfile(**raw)


def save_tailored_tex(idempotency_key: str, content: str) -> Path:
    paths.ensure_data_layout()
    dest = paths.tailored_tex_path(idempotency_key)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding="utf-8")
    return dest


def read_tailored_tex(idempotency_key: str) -> str:
    path = paths.tailored_tex_path(idempotency_key)
    if not path.is_file():
        raise FileNotFoundError(f"No tailored resume at {path}")
    return path.read_text(encoding="utf-8")


def write_application_meta(idempotency_key: str, payload: dict) -> Path:
    dest = paths.application_meta_path(idempotency_key)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return dest


def touch_application_meta(
    idempotency_key: str,
    *,
    country: str,
    company: str,
    url: str,
    event: str,
    extra: dict | None = None,
) -> dict:
    dest = paths.application_meta_path(idempotency_key)
    base: dict = {}
    if dest.is_file():
        base = json.loads(dest.read_text(encoding="utf-8"))
    now = datetime.now(timezone.utc).isoformat()
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
    write_application_meta(idempotency_key, base)
    return base
