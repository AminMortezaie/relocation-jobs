from __future__ import annotations

import re

_FILENAME_PART_RE = re.compile(r"[^a-z0-9]+")


def _filename_part(text: str) -> str:
    return _FILENAME_PART_RE.sub("_", (text or "").strip().lower()).strip("_")


def master_pdf_filename(full_name: str, slug: str) -> str:
    parts = [part for part in (full_name or "").strip().split() if part]
    if len(parts) >= 2:
        name_bits = [_filename_part(parts[0]), _filename_part(parts[-1])]
    elif len(parts) == 1:
        name_bits = [_filename_part(parts[0])]
    else:
        name_bits = ["resume"]

    variant = _filename_part(slug) or "master"
    return f"{'_'.join([*name_bits, variant])}.pdf"


def project_pdf_filename(full_name: str, slug: str) -> str:
    parts = [part for part in (full_name or "").strip().split() if part]
    if len(parts) >= 2:
        name_bits = [_filename_part(parts[0]), _filename_part(parts[-1]), "project"]
    elif len(parts) == 1:
        name_bits = [_filename_part(parts[0]), "project"]
    else:
        name_bits = ["project"]

    variant = _filename_part(slug) or "master"
    return f"{'_'.join([*name_bits, variant])}.pdf"


def application_pdf_filename(full_name: str, company_name: str) -> str:
    parts = [part for part in (full_name or "").strip().split() if part]
    if len(parts) >= 2:
        name_bits = [_filename_part(parts[0]), _filename_part(parts[-1])]
    elif len(parts) == 1:
        name_bits = [_filename_part(parts[0])]
    else:
        name_bits = ["resume"]

    company = _filename_part(company_name) or "company"
    return f"{'_'.join([*name_bits, company])}.pdf"


def application_cover_letter_pdf_filename(full_name: str, company_name: str) -> str:
    base = application_pdf_filename(full_name, company_name)
    return f"{base.removesuffix('.pdf')}_cover_letter.pdf"
