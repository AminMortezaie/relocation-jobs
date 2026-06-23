"""Shared helpers for HTTP routes."""

from __future__ import annotations

import os

from flask import request

from relocation_jobs.core.paths import SUPPORTED_COUNTRIES
from relocation_jobs.web.scrape_runner import build_fetch_status_payload


def scrape_enabled() -> bool:
    return os.environ.get("PANEL_SCRAPE_ENABLED", "1").lower() not in (
        "0",
        "false",
        "no",
    )


def admin_fetch_snapshot() -> dict:
    status = build_fetch_status_payload()
    progress = status.get("progress") or {}
    return {
        "running": bool(status.get("running")),
        "country": status.get("country"),
        "company": status.get("company"),
        "ats_type": status.get("ats_type"),
        "scope": "company" if status.get("company") else "country",
        "progress": dict(progress) if isinstance(progress, dict) else {},
        "started_at": status.get("started_at"),
        "run_id": status.get("run_id"),
    }


def query_bool(name: str) -> bool:
    return request.args.get(name, "").lower() in ("1", "true", "yes")


def query_flags() -> dict:
    country = request.args.get("country", "all")
    country_key = country if country != "all" else None
    timezone_name = (request.args.get("timezone") or "").strip() or None
    city = (request.args.get("city") or "").strip() or None
    location = (request.args.get("location") or "").strip() or None
    ats = (request.args.get("ats_type") or request.args.get("ats") or "all").strip()
    ats_type = ats if ats and ats != "all" else None
    return {
        "country_key": country_key,
        "country_all": country == "all",
        "timezone_name": timezone_name,
        "city": city,
        "location": location,
        "ats_type": ats_type,
        "visa_only": query_bool("visa_only"),
        "hide_applied": query_bool("hide_applied"),
        "hide_empty": query_bool("hide_empty"),
        "not_applied_only": query_bool("not_applied_only"),
        "hide_position_applied": query_bool("hide_position_applied"),
        "hide_position_rejected": query_bool("hide_position_rejected"),
        "position_applied_only": query_bool("position_applied_only"),
        "position_rejected_only": query_bool("position_rejected_only"),
        "position_looking_to_apply_only": query_bool("position_looking_to_apply_only"),
        "fetch_ok_only": query_bool("fetch_ok_only"),
        "fetch_problem_only": query_bool("fetch_problem_only"),
    }
