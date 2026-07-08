from __future__ import annotations

import logging
import os
import time

from relocation_jobs.core.ats_constants import HTTPX_AVAILABLE, MAX_CONCURRENCY
from relocation_jobs.core.auth import bootstrap_admin
from relocation_jobs.core.paths import supported_countries
from relocation_jobs.db import init_db
from relocation_jobs.users.repo import resolve_scheduler_user_id
from relocation_jobs.fetch import repo as fetch_repo
from relocation_jobs.fetch.log import configure_fetch_logging, log_event
from relocation_jobs.fetch import state as fetch_state
from relocation_jobs.fetch.runner import start_country_fetch

LOGGER = logging.getLogger("relocation_jobs.fetch.scheduler")


def schedule_enabled() -> bool:
    return os.environ.get("FETCH_SCHEDULE_ENABLED", "0").lower() not in ("0", "false", "no")


def schedule_interval_hours() -> float:
    raw = (os.environ.get("FETCH_SCHEDULE_INTERVAL_HOURS") or "6").strip()
    try:
        return max(0.25, float(raw))
    except (TypeError, ValueError):
        return 6.0


def schedule_concurrency() -> int:
    raw = (os.environ.get("FETCH_SCHEDULE_CONCURRENCY") or "4").strip()
    try:
        return max(1, min(int(raw), MAX_CONCURRENCY))
    except (TypeError, ValueError):
        return 4


def schedule_countries() -> tuple[str, ...]:
    raw = (os.environ.get("FETCH_SCHEDULE_COUNTRIES") or "").strip()
    if not raw:
        return tuple(sorted(supported_countries()))
    countries: list[str] = []
    for part in raw.split(","):
        key = part.strip().lower()
        if not key:
            continue
        if key not in supported_countries():
            raise ValueError(f"Unknown country in FETCH_SCHEDULE_COUNTRIES: {key}")
        if key not in countries:
            countries.append(key)
    if not countries:
        raise ValueError("FETCH_SCHEDULE_COUNTRIES is empty")
    return tuple(countries)


def bootstrap_scheduler() -> None:
    init_db()
    bootstrap_admin()
    configure_fetch_logging()
    fetch_repo.reap_orphan_running_fetch_runs()


def run_fetch_cycle(*, user_id: int | None = None) -> dict:
    if not schedule_enabled():
        return {"skipped": True, "reason": "schedule_disabled"}

    if not HTTPX_AVAILABLE:
        log_event("Scheduled fetch skipped: httpx is not installed", level=logging.ERROR)
        return {"skipped": True, "reason": "httpx_missing"}

    if fetch_state.fetch_is_running():
        log_event("Scheduled fetch skipped: another fetch is already running")
        return {"skipped": True, "reason": "fetch_busy"}

    resolved_user_id = user_id if user_id is not None else resolve_scheduler_user_id()
    countries = schedule_countries()
    concurrency = schedule_concurrency()
    started: list[str] = []
    skipped: list[str] = []

    log_event(
        "Scheduled fetch cycle starting",
        user_id=resolved_user_id,
        concurrency=concurrency,
        total=len(countries),
    )

    for country in countries:
        if fetch_state.fetch_is_running():
            skipped.extend(countries[countries.index(country):])
            log_event(
                "Scheduled fetch stopped: fetch became busy",
                country=country,
            )
            break

        try:
            run_id = start_country_fetch(
                user_id=resolved_user_id,
                country_key=country,
                concurrency=concurrency,
            )
        except RuntimeError as exc:
            skipped.append(country)
            log_event(
                f"Scheduled fetch could not start for {country}: {exc}",
                country=country,
                level=logging.WARNING,
            )
            continue

        started.append(country)
        log_event(
            "Scheduled country fetch started",
            run_id=run_id,
            country=country,
            user_id=resolved_user_id,
            concurrency=concurrency,
        )
        fetch_state.wait_for_fetch_thread()
        log_event(
            "Scheduled country fetch finished",
            run_id=run_id,
            country=country,
        )

    result = {
        "skipped": False,
        "started": started,
        "not_started": skipped,
        "countries": list(countries),
        "concurrency": concurrency,
    }
    log_event(
        "Scheduled fetch cycle finished",
        total=len(countries),
    )
    return result


def run_scheduler_loop() -> None:
    bootstrap_scheduler()
    if not schedule_enabled():
        LOGGER.error("FETCH_SCHEDULE_ENABLED is off; scheduler exiting")
        return

    interval_seconds = schedule_interval_hours() * 3600
    log_event(
        "Fetch scheduler started",
        concurrency=schedule_concurrency(),
        total=len(schedule_countries()),
    )

    while True:
        try:
            run_fetch_cycle()
        except Exception as exc:
            log_event(f"Scheduled fetch cycle failed: {exc}", level=logging.ERROR)
        time.sleep(interval_seconds)
