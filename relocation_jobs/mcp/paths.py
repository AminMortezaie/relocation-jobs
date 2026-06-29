from __future__ import annotations

import shutil
from pathlib import Path

from relocation_jobs.core.paths import PACKAGE_DIR, ensure_data_dir

ASSETS_DIR = PACKAGE_DIR / "mcp" / "assets"
MASTER_RESUME_NAME = "master_resume.tex"
PROFILE_NAME = "profile.json"
PROFILE_EXAMPLE_NAME = "profile.example.json"


def mcp_root() -> Path:
    return ensure_data_dir() / "mcp"


def master_resume_path() -> Path:
    return mcp_root() / MASTER_RESUME_NAME


def profile_path() -> Path:
    return mcp_root() / PROFILE_NAME


def applications_root() -> Path:
    return mcp_root() / "applications"


def application_dir(idempotency_key: str) -> Path:
    safe = (idempotency_key or "unknown").strip()
    if not safe:
        safe = "unknown"
    return applications_root() / safe


def tailored_tex_path(idempotency_key: str) -> Path:
    return application_dir(idempotency_key) / "resume.tex"


def pdf_path(idempotency_key: str) -> Path:
    return application_dir(idempotency_key) / "resume.pdf"


def application_meta_path(idempotency_key: str) -> Path:
    return application_dir(idempotency_key) / "meta.json"


def ensure_data_layout() -> Path:
    root = mcp_root()
    root.mkdir(parents=True, exist_ok=True)
    applications_root().mkdir(parents=True, exist_ok=True)
    master = master_resume_path()
    if not master.is_file():
        shutil.copy2(ASSETS_DIR / MASTER_RESUME_NAME, master)
    profile = profile_path()
    if not profile.is_file():
        shutil.copy2(ASSETS_DIR / PROFILE_EXAMPLE_NAME, profile)
    return root
