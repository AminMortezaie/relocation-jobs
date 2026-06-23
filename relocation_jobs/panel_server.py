#!/usr/bin/env python3
"""
Job opportunities dashboard — view cached matches and trigger new scrapes.

    python3 scripts/panel_server.py
    # or: python3 -m relocation_jobs.panel_server
    # open http://127.0.0.1:5050
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import os
import re
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, g, jsonify, request, send_from_directory

from relocation_jobs.core.auth import (
    admin_required,
    auth_status,
    authenticate,
    init_auth,
    login_required,
    login_user,
    logout_user,
    register_user,
)

from relocation_jobs.core.location_tags import add_custom_city
from relocation_jobs.panel_data import (
    COUNTRY_FILES,
    COUNTRY_LABELS,
    add_company,
    add_manual_jobs,
    compute_stats,
    flatten_companies,
    list_company_cities,
    list_company_locations,
    list_ats_types,
    remove_company,
    rename_company,
    resolve_company_name,
    set_company_applied,
    set_company_awaiting_response,
    set_company_fetch_ok,
    set_company_fetch_problem,
    touch_company_fetch_time,
    set_job_applied,
    set_job_ats_score,
    set_job_not_for_me,
    set_job_looking_to_apply,
    set_job_rejected,
    set_job_reapply,
    set_job_seen,
    set_job_waiting_referral,
    update_company_careers,
    update_company_city,
    reconcile_wrong_location_hides,
)
from relocation_jobs.catalog_db import touch_country_meta
from relocation_jobs.admin_data import (
    get_admin_dashboard,
    get_admin_overview,
    get_catalog_overview,
    get_system_config,
)
from relocation_jobs.db import (
    is_user_admin,
    list_all_fetch_runs,
    list_fetch_runs,
    list_users_with_stats,
    record_fetch_run,
)
from relocation_jobs.core.paths import (
    PROJECT_ROOT,
    STATIC_DIR,
)

try:
    from relocation_jobs.scrape_jobs import (
        DEFAULT_CONCURRENCY,
        HTTPX_AVAILABLE,
        clear_cancel_checker,
        clear_progress_reporter,
        clear_review_reporter,
        run_country,
        set_cancel_checker,
        set_progress_reporter,
        set_review_reporter,
    )
except ImportError:
    DEFAULT_CONCURRENCY = 16
    HTTPX_AVAILABLE = False
    run_country = None  # type: ignore
    set_cancel_checker = None  # type: ignore
    clear_cancel_checker = None  # type: ignore
    set_progress_reporter = None  # type: ignore
    clear_progress_reporter = None  # type: ignore
    set_review_reporter = None  # type: ignore
    clear_review_reporter = None  # type: ignore

ROOT = PROJECT_ROOT
STATIC = STATIC_DIR

app = Flask(__name__, static_folder=str(STATIC), static_url_path="/static")

_bootstrapped = False


def bootstrap_app() -> None:
    global _bootstrapped
    if _bootstrapped:
        return
    STATIC.mkdir(exist_ok=True)
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass
    init_auth(app)
    _bootstrapped = True

_fetch_lock = threading.RLock()
_fetch_state: dict = {
    "running": False,
    "country": None,
    "company": None,
    "file": None,
    "concurrency": DEFAULT_CONCURRENCY,
    "started_at": None,
    "finished_at": None,
    "exit_code": None,
    "result_line": None,
    "cancel_requested": False,
    "cancelled": False,
    "progress": {"current": 0, "total": 0, "company": None, "status": ""},
    "review_jobs": None,
    "activity": {"message": "", "detail": ""},
    "activity_log": deque(maxlen=20),
    "activity_touch_company": None,
    "new_jobs_total": 0,
    "log": deque(maxlen=200),
    "process": None,
    "user_id": None,
    "fetch_run_recorded": False,
    "last_fetch_run": None,
}

_fetch_thread: threading.Thread | None = None

_TOTAL_RE = re.compile(r"\((\d+)\s+to process")


def _reap_zombie_fetch() -> None:
    """Clear stale running flag when the scrape thread has exited."""
    global _fetch_thread
    should_persist = False
    with _fetch_lock:
        if not _fetch_state.get("running"):
            return
        if _fetch_thread is None:
            return
        if _fetch_thread.is_alive():
            return
        _fetch_state["running"] = False
        if _fetch_state.get("exit_code") is None:
            _fetch_state["exit_code"] = 1
            _fetch_state["log"].append("Fetch thread stopped unexpectedly")
        if not _fetch_state.get("finished_at"):
            _fetch_state["finished_at"] = datetime.now(timezone.utc).isoformat()
        should_persist = not _fetch_state.get("fetch_run_recorded")
    if should_persist:
        _persist_fetch_run()


def _should_cancel_fetch() -> bool:
    with _fetch_lock:
        return bool(_fetch_state.get("cancel_requested"))


def _on_scrape_progress(info: dict) -> None:
    with _fetch_lock:
        _fetch_state["progress"] = {
            "current": int(info.get("current") or 0),
            "total": int(info.get("total") or 0),
            "company": info.get("company"),
            "status": info.get("status") or "",
        }


def _on_scrape_review(info: dict) -> None:
    with _fetch_lock:
        _fetch_state["review_jobs"] = {
            "included": list(info.get("included") or []),
            "filtered": list(info.get("filtered") or []),
        }


def _reset_fetch_run_state(*, country, company, file_name, concurrency, user_id=None) -> None:
    global _fetch_thread
    _fetch_thread = None
    _fetch_state["running"] = True
    _fetch_state["country"] = country
    _fetch_state["company"] = company
    _fetch_state["file"] = file_name
    _fetch_state["concurrency"] = concurrency
    _fetch_state["user_id"] = user_id
    _fetch_state["fetch_run_recorded"] = False
    _fetch_state["last_fetch_run"] = None
    _fetch_state["started_at"] = datetime.now(timezone.utc).isoformat()
    _fetch_state["finished_at"] = None
    _fetch_state["exit_code"] = None
    _fetch_state["result_line"] = None
    _fetch_state["cancel_requested"] = False
    _fetch_state["cancelled"] = False
    _fetch_state["progress"] = {"current": 0, "total": 0, "company": None, "status": ""}
    _fetch_state["review_jobs"] = None
    _fetch_state["activity"] = {"message": "", "detail": ""}
    _fetch_state["activity_log"].clear()
    _fetch_state["activity_touch_company"] = None
    _fetch_state["new_jobs_total"] = 0
    _fetch_state["log"].clear()
    if company:
        _push_fetch_activity(f"Fetching {company}…")
    else:
        _push_fetch_activity("Starting country fetch…")


def _build_fetch_run_snapshot() -> dict | None:
    with _fetch_lock:
        if _fetch_state.get("fetch_run_recorded"):
            return None
        user_id = _fetch_state.get("user_id")
        country = _fetch_state.get("country")
        started_at = _fetch_state.get("started_at")
        finished_at = _fetch_state.get("finished_at")
        if not user_id or not country or not started_at or not finished_at:
            return None
        prog = _fetch_state.get("progress") or {}
        _fetch_state["fetch_run_recorded"] = True
        return {
            "user_id": int(user_id),
            "country": str(country),
            "company_name": _fetch_state.get("company"),
            "started_at": str(started_at),
            "finished_at": str(finished_at),
            "exit_code": _fetch_state.get("exit_code"),
            "cancelled": bool(_fetch_state.get("cancelled")),
            "new_jobs": int(_fetch_state.get("new_jobs_total") or 0),
            "concurrency": _fetch_state.get("concurrency"),
            "companies_done": int(prog.get("current") or 0) or None,
            "companies_total": int(prog.get("total") or 0) or None,
            "result_line": _fetch_state.get("result_line"),
        }


def _persist_fetch_run() -> dict | None:
    snapshot = _build_fetch_run_snapshot()
    if not snapshot:
        return None
    try:
        row = record_fetch_run(**snapshot)
    except Exception:
        return None
    with _fetch_lock:
        _fetch_state["last_fetch_run"] = row
    return row


def _push_fetch_activity(message: str, detail: str = "") -> None:
    message = (message or "").strip()
    if not message:
        return
    entry = {"message": message, "detail": (detail or "").strip()}
    _fetch_state["activity"] = entry
    if not _fetch_state["activity_log"] or _fetch_state["activity_log"][-1] != entry:
        _fetch_state["activity_log"].append(entry)


def _activity_from_scrape_line(text: str) -> dict | None:
    """Turn scraper console lines into user-facing fetch steps."""
    t = (text or "").strip()
    if not t or t.startswith("@@"):
        return None
    if t.startswith("Finished ") or t.startswith("Done "):
        return None

    m = re.match(r"Fetching (.+)$", t)
    if m:
        return {"message": f"Fetching {m.group(1).strip()}…", "detail": ""}

    m = re.match(r"Detected:\s*(\S+)\s*→\s*(.+)", t)
    if m:
        return {"message": f"Detected {m.group(1)} board", "detail": m.group(2).strip()}

    m = re.match(r"Known(?: override)?:\s*(\S+)\s*→\s*(.+)", t)
    if m:
        return {"message": f"Using {m.group(1)} board", "detail": m.group(2).strip()}

    if "Detecting ATS via Playwright" in t:
        return {"message": "Detecting job board from careers page…", "detail": "Playwright"}

    if "No ATS detected, using generic" in t:
        return {"message": "No job board detected", "detail": "Loading careers page directly"}

    m = re.match(r"TeamTailor HTML board:\s*(\d+) role", t)
    if m:
        return {"message": f"Loaded {m.group(1)} roles from TeamTailor", "detail": ""}

    m = re.match(r"Loading TeamTailor page (\d+)…", t)
    if m:
        return {"message": f"Loading TeamTailor page {m.group(1)}", "detail": ""}

    if t.endswith(" API") or " API error" in t:
        return None

    for label in (
        "Greenhouse", "Lever", "Recruitee", "Ashby", "Personio",
        "SmartRecruiters", "Workable", "Join", "Deel", "bol careers",
    ):
        if f"{label} error" in t:
            return {"message": f"{label} request failed", "detail": t}

    if "Playwright error" in t:
        return {"message": "Careers page load failed", "detail": t}

    if " — enriched " in t and "job(s)" in t:
        m = re.search(r"enriched (\d+) job", t)
        if m:
            return {"message": f"Checking visa/relocation on {m.group(1)} roles", "detail": ""}

    if " — " in t and t[0] == "[":
        return None

    return None


def _handle_scrape_ipc_line(line: str) -> bool:
    if line.startswith("@@PROGRESS@@"):
        try:
            data = json.loads(line[len("@@PROGRESS@@"):])
            company = data.get("company")
            status = data.get("status") or ""
            country = None
            with _fetch_lock:
                _fetch_state["progress"] = {
                    "current": int(data.get("current") or 0),
                    "total": int(data.get("total") or 0),
                    "company": company,
                    "status": status,
                }
                if status == "done" and "new_jobs" in data:
                    _fetch_state["new_jobs_total"] = int(
                        _fetch_state.get("new_jobs_total") or 0
                    ) + int(data.get("new_jobs") or 0)
                country = _fetch_state.get("country")
                should_touch = (
                    status == "fetching"
                    and company
                    and country
                    and _fetch_state.get("activity_touch_company") != company
                )
                if should_touch:
                    _fetch_state["activity_touch_company"] = company
            if should_touch:
                try:
                    touch_company_fetch_time(country, company)
                except (LookupError, ValueError):
                    pass
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
        return True
    if line.startswith("@@REVIEW@@"):
        try:
            data = json.loads(line[len("@@REVIEW@@"):])
            with _fetch_lock:
                _fetch_state["review_jobs"] = {
                    "included": list(data.get("included") or []),
                    "filtered": list(data.get("filtered") or []),
                }
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
        return True
    if line.startswith("@@ACTIVITY@@"):
        try:
            data = json.loads(line[len("@@ACTIVITY@@"):])
            with _fetch_lock:
                _push_fetch_activity(
                    str(data.get("message") or ""),
                    str(data.get("detail") or ""),
                )
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
        return True
    return False


def _log(line: str) -> None:
    text = line.rstrip()
    if not text:
        return
    with _fetch_lock:
        _fetch_state["log"].append(text)
        activity = _activity_from_scrape_line(text)
        if activity:
            _push_fetch_activity(activity["message"], activity.get("detail", ""))
        if " — " in text and (text.startswith("[") or text.startswith("Done ")):
            _fetch_state["result_line"] = text
        m_total = _TOTAL_RE.search(text)
        if m_total:
            _fetch_state["progress"]["total"] = int(m_total.group(1))


def _build_scrape_cmd(
    country: str,
    skip_filled: bool,
    concurrency: int,
    *,
    company: str | None = None,
) -> list[str]:
    if country not in COUNTRY_FILES:
        raise LookupError(f"Unknown country: {country}")
    cmd = [
        sys.executable,
        "-m",
        "relocation_jobs.scrape_jobs",
        "--country",
        country,
    ]
    if skip_filled and not company:
        cmd.append("--skip-filled")
    workers = 1 if company else max(1, min(int(concurrency), 64))
    if workers <= 1:
        cmd.append("--serial")
    else:
        cmd.extend(["--workers", str(workers)])
    if company:
        cmd.append(company)
    return cmd


def _terminate_scrape_process(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=2.0)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=2.0)


class _LogWriter:
    """Capture scraper stdout into the fetch log line-by-line."""

    def write(self, s: str) -> None:
        if not s:
            return
        for line in s.splitlines():
            _log(line)

    def flush(self) -> None:
        pass


def _run_scrape(
    country: str,
    skip_filled: bool,
    concurrency: int,
    *,
    company: str | None = None,
) -> None:
    proc: subprocess.Popen | None = None
    exit_code: int | None = None
    try:
        if company:
            concurrency = 1
            with _fetch_lock:
                _fetch_state["progress"]["total"] = 1
        else:
            concurrency = max(1, min(int(concurrency), 64))
        _fetch_state["concurrency"] = concurrency

        filename = COUNTRY_FILES.get(country)
        if company:
            _log(f"Fetching {company}")
        else:
            _log(f"Fetching all companies in {filename} ({concurrency} workers)")

        if not HTTPX_AVAILABLE:
            _log("Error: httpx is not installed. Run: pip install httpx")
            _fetch_state["exit_code"] = 1
            return

        cmd = _build_scrape_cmd(
            country,
            skip_filled and not company,
            concurrency,
            company=company,
        )
        env = {**os.environ, "PANEL_SCRAPE_CHILD": "1"}
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
            cwd=str(ROOT),
        )
        with _fetch_lock:
            _fetch_state["process"] = proc

        if proc.stdout is not None:
            for line in proc.stdout:
                text = line.rstrip("\n")
                if _handle_scrape_ipc_line(text):
                    continue
                _log(text)
        exit_code = proc.wait()
    except LookupError as e:
        _log(f"Error: {e}")
        exit_code = 1
        _log("Finished (exit 1)")
    except Exception as e:
        _log(f"Error: {e}")
        exit_code = 1
        _log("Finished (exit 1)")
    finally:
        with _fetch_lock:
            cancelled = bool(_fetch_state.get("cancel_requested"))
            if cancelled:
                _fetch_state["exit_code"] = 130
                _log("Cancelled by user")
            elif exit_code == 0:
                _fetch_state["exit_code"] = 0
                _log("Finished (exit 0)")
            elif exit_code is not None:
                _fetch_state["exit_code"] = exit_code
                _log(f"Finished (exit {exit_code})")
            elif _fetch_state.get("exit_code") is None:
                _fetch_state["exit_code"] = 1

            prog = _fetch_state.get("progress") or {}
            total = int(prog.get("total") or 0)
            if total > 0 and not cancelled:
                _fetch_state["progress"] = {
                    **prog,
                    "current": total,
                    "status": "done",
                }
            if company and _fetch_state.get("review_jobs") is None:
                _fetch_state["review_jobs"] = {"included": [], "filtered": []}
            if cancelled:
                _fetch_state["cancelled"] = True
            _fetch_state["running"] = False
            _fetch_state["finished_at"] = datetime.now(timezone.utc).isoformat()
            _fetch_state["process"] = None
            country_key = _fetch_state.get("country")
            new_jobs_total = int(_fetch_state.get("new_jobs_total") or 0)
        if country_key and country_key in COUNTRY_FILES:
            try:
                touch_country_meta(country_key, last_fetch_new_jobs=new_jobs_total)
            except Exception:
                pass
        _persist_fetch_run()
        if proc is not None and proc.poll() is None:
            _terminate_scrape_process(proc)


@app.before_request
def _ensure_bootstrapped():
    if request.endpoint == "static":
        return
    bootstrap_app()


@app.after_request
def _static_no_cache(response):
    if request.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.route("/")
def index():
    resp = send_from_directory(STATIC, "index.html")
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/admin")
def admin_page():
    resp = send_from_directory(STATIC, "admin.html")
    resp.headers["Cache-Control"] = "no-store"
    return resp


def _admin_fetch_snapshot() -> dict:
    with _fetch_lock:
        running = bool(_fetch_state.get("running"))
        progress = _fetch_state.get("progress") or {}
        return {
            "running": running,
            "country": _fetch_state.get("country"),
            "company": _fetch_state.get("company"),
            "scope": "company" if _fetch_state.get("company") else "country",
            "progress": dict(progress) if isinstance(progress, dict) else {},
            "started_at": _fetch_state.get("started_at"),
        }


@app.get("/api/admin/dashboard")
@admin_required
def api_admin_dashboard():
    try:
        limit = 50
        raw_limit = request.args.get("limit")
        if raw_limit is not None:
            try:
                limit = int(raw_limit)
            except ValueError:
                limit = 50
        return jsonify(
            get_admin_dashboard(
                fetch_state=_admin_fetch_snapshot(),
                scrape_enabled=scrape_enabled(),
                httpx_available=HTTPX_AVAILABLE,
                fetch_runs_limit=limit,
            )
        )
    except Exception as exc:
        app.logger.exception("admin dashboard failed")
        return jsonify({"error": str(exc)}), 500


@app.get("/api/admin/overview")
@admin_required
def api_admin_overview():
    try:
        return jsonify(get_admin_overview(fetch_state=_admin_fetch_snapshot()))
    except Exception as exc:
        app.logger.exception("admin overview failed")
        return jsonify({"error": str(exc)}), 500


@app.get("/api/admin/catalog")
@admin_required
def api_admin_catalog():
    try:
        return jsonify(get_catalog_overview())
    except Exception as exc:
        app.logger.exception("admin catalog failed")
        return jsonify({"error": str(exc)}), 500


@app.get("/api/admin/users")
@admin_required
def api_admin_users():
    try:
        return jsonify({"users": list_users_with_stats()})
    except Exception as exc:
        app.logger.exception("admin users failed")
        return jsonify({"error": str(exc)}), 500


@app.get("/api/admin/fetch-runs")
@admin_required
def api_admin_fetch_runs():
    country = (request.args.get("country") or "").strip() or None
    try:
        limit = int(request.args.get("limit", "50"))
    except ValueError:
        limit = 50
    try:
        return jsonify(
            {"runs": list_all_fetch_runs(country=country, limit=limit)}
        )
    except Exception as exc:
        app.logger.exception("admin fetch-runs failed")
        return jsonify({"error": str(exc)}), 500


@app.get("/api/admin/config")
@admin_required
def api_admin_config():
    try:
        return jsonify(
            get_system_config(
                scrape_enabled=scrape_enabled(),
                httpx_available=HTTPX_AVAILABLE,
            )
        )
    except Exception as exc:
        app.logger.exception("admin config failed")
        return jsonify({"error": str(exc)}), 500


@app.get("/api/auth/status")
def api_auth_status():
    return jsonify(auth_status())


@app.post("/api/auth/login")
def api_auth_login():
    body = request.get_json(silent=True) or {}
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400
    user = authenticate(username, password)
    if not user:
        return jsonify({"error": "Invalid username or password"}), 401
    login_user(user["id"], user["username"])
    return jsonify({"ok": True, **auth_status()})


@app.post("/api/auth/logout")
def api_auth_logout():
    logout_user()
    return jsonify({"ok": True, "authenticated": False})


@app.post("/api/auth/register")
def api_auth_register():
    body = request.get_json(silent=True) or {}
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    try:
        user = register_user(username, password)
        login_user(user["id"], user["username"])
        return jsonify({"ok": True, **auth_status()})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


def scrape_enabled() -> bool:
    return os.environ.get("PANEL_SCRAPE_ENABLED", "1").lower() not in (
        "0",
        "false",
        "no",
    )


@app.get("/api/config")
@login_required
def api_config():
    return jsonify({
        "default_concurrency": DEFAULT_CONCURRENCY,
        "max_concurrency": 64,
        "mode": "asyncio",
        "httpx_available": HTTPX_AVAILABLE,
        "scrape_enabled": scrape_enabled(),
        "description": (
            "Scraper uses an asyncio event loop with httpx for ATS API calls. "
            f"'--workers N' means {DEFAULT_CONCURRENCY} companies in flight by default."
        ),
    })


@app.get("/api/countries")
@login_required
def api_countries():
    return jsonify([
        {"id": "all", "label": "All countries"},
        *[{"id": k, "label": COUNTRY_LABELS[k]} for k in COUNTRY_FILES],
    ])


@app.get("/api/ats-types")
@login_required
def api_ats_types():
    return jsonify({"ats_types": list_ats_types()})


@app.get("/api/cities")
@login_required
def api_cities():
    country = request.args.get("country", "all")
    country_key = country if country != "all" else None
    if country != "all" and country not in COUNTRY_FILES:
        return jsonify({"error": f"Unknown country: {country}"}), 400
    for_picker = request.args.get("picker", "").lower() in ("1", "true", "yes")
    locations = list_company_locations(country_key, for_picker=for_picker)
    return jsonify({
        "cities": [loc["city"] for loc in locations],
        "locations": locations,
    })


@app.get("/api/locations")
@login_required
def api_locations():
    country = request.args.get("country", "all")
    country_key = country if country != "all" else None
    if country != "all" and country not in COUNTRY_FILES:
        return jsonify({"error": f"Unknown country: {country}"}), 400
    for_picker = request.args.get("picker", "").lower() in ("1", "true", "yes")
    return jsonify({
        "locations": list_company_locations(country_key, for_picker=for_picker),
    })


@app.post("/api/locations")
@login_required
def api_locations_add():
    body = request.get_json(silent=True) or {}
    country = (body.get("country") or "").strip().lower()
    city = (body.get("city") or "").strip()
    if not country or country == "all":
        return jsonify({"error": "country is required (not 'all')"}), 400
    if country not in COUNTRY_FILES:
        return jsonify({"error": f"Unknown country: {country}"}), 400
    if not city:
        return jsonify({"error": "city is required"}), 400
    try:
        location = add_custom_city(country, city)
        restored = reconcile_wrong_location_hides(
            g.user_id,
            country_key=country,
            city_label=location["city"],
        )
        return jsonify({"ok": True, "location": location, "restored_jobs": restored})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


def _query_bool(name: str) -> bool:
    return request.args.get(name, "").lower() in ("1", "true", "yes")


def _query_flags() -> dict:
    country = request.args.get("country", "all")
    country_key = country if country != "all" else None
    timezone_name = (request.args.get("timezone") or "").strip() or None
    city = (request.args.get("city") or "").strip() or None
    location = (request.args.get("location") or "").strip() or None
    return {
        "country_key": country_key,
        "country_all": country == "all",
        "timezone_name": timezone_name,
        "city": city,
        "location": location,
        "visa_only": _query_bool("visa_only"),
        "hide_applied": _query_bool("hide_applied"),
        "hide_empty": _query_bool("hide_empty"),
        "not_applied_only": _query_bool("not_applied_only"),
        "hide_position_applied": _query_bool("hide_position_applied"),
        "hide_position_rejected": _query_bool("hide_position_rejected"),
        "position_applied_only": _query_bool("position_applied_only"),
        "position_rejected_only": _query_bool("position_rejected_only"),
        "position_looking_to_apply_only": _query_bool("position_looking_to_apply_only"),
        "fetch_ok_only": _query_bool("fetch_ok_only"),
        "fetch_problem_only": _query_bool("fetch_problem_only"),
    }


@app.get("/api/jobs")
@login_required
def api_jobs():
    flags = _query_flags()
    companies, file_meta, fetch_problem_count = flatten_companies(
        flags["country_key"],
        visa_only=flags["visa_only"],
        hide_applied=flags["hide_applied"],
        hide_empty=flags["hide_empty"],
        not_applied_only=flags["not_applied_only"],
        hide_position_applied=flags["hide_position_applied"],
        hide_position_rejected=flags["hide_position_rejected"],
        position_applied_only=flags["position_applied_only"],
        position_rejected_only=flags["position_rejected_only"],
        position_looking_to_apply_only=flags["position_looking_to_apply_only"],
        fetch_ok_only=flags["fetch_ok_only"],
        fetch_problem_only=flags["fetch_problem_only"],
        location=flags["location"],
        city=flags["city"],
        user_id=g.user_id,
    )
    stats = compute_stats(
        companies,
        file_meta,
        fetch_problem_count=fetch_problem_count,
        user_id=g.user_id,
        country_key=flags["country_key"],
        timezone_name=flags["timezone_name"],
    )
    return jsonify({"companies": companies, "stats": stats})


@app.patch("/api/jobs/applied")
@app.post("/api/jobs/applied")
@login_required
def api_jobs_applied():
    body = request.get_json(silent=True) or {}
    country = body.get("country", "")
    company = body.get("company", "")
    url = body.get("url", "")
    applied = bool(body.get("applied", True))

    if not country or country == "all":
        return jsonify({"error": "country is required (not 'all')"}), 400
    if country not in COUNTRY_FILES:
        return jsonify({"error": f"Unknown country: {country}"}), 400
    if not company or not url:
        return jsonify({"error": "company and url are required"}), 400

    try:
        result = set_job_applied(country, company, url, applied, user_id=g.user_id)
        return jsonify({"ok": True, **result})
    except LookupError as e:
        return jsonify({"error": str(e)}), 404
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.patch("/api/jobs/rejected")
@app.post("/api/jobs/rejected")
@login_required
def api_jobs_rejected():
    body = request.get_json(silent=True) or {}
    country = body.get("country", "")
    company = body.get("company", "")
    url = body.get("url", "")
    rejected = bool(body.get("rejected", True))

    if not country or country == "all":
        return jsonify({"error": "country is required (not 'all')"}), 400
    if country not in COUNTRY_FILES:
        return jsonify({"error": f"Unknown country: {country}"}), 400
    if not company or not url:
        return jsonify({"error": "company and url are required"}), 400

    try:
        result = set_job_rejected(country, company, url, rejected, user_id=g.user_id)
        return jsonify({"ok": True, **result})
    except LookupError as e:
        return jsonify({"error": str(e)}), 404
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.patch("/api/jobs/reapply")
@app.post("/api/jobs/reapply")
@login_required
def api_jobs_reapply():
    body = request.get_json(silent=True) or {}
    country = body.get("country", "")
    company = body.get("company", "")
    url = body.get("url", "")

    if not country or country == "all":
        return jsonify({"error": "country is required (not 'all')"}), 400
    if country not in COUNTRY_FILES:
        return jsonify({"error": f"Unknown country: {country}"}), 400
    if not company or not url:
        return jsonify({"error": "company and url are required"}), 400

    try:
        result = set_job_reapply(country, company, url, user_id=g.user_id)
        return jsonify({"ok": True, **result})
    except LookupError as e:
        return jsonify({"error": str(e)}), 404
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.patch("/api/jobs/ats-score")
@app.post("/api/jobs/ats-score")
@login_required
def api_jobs_ats_score():
    body = request.get_json(silent=True) or {}
    country = body.get("country", "")
    company = body.get("company", "")
    url = body.get("url", "")

    if not country or country == "all":
        return jsonify({"error": "country is required (not 'all')"}), 400
    if country not in COUNTRY_FILES:
        return jsonify({"error": f"Unknown country: {country}"}), 400
    if not company or not url:
        return jsonify({"error": "company and url are required"}), 400

    raw_score = body.get("ats_score")
    if raw_score is None or raw_score == "":
        ats_score = None
    else:
        try:
            ats_score = int(raw_score)
        except (TypeError, ValueError):
            return jsonify({"error": "ats_score must be an integer 0–100"}), 400
        if not 0 <= ats_score <= 100:
            return jsonify({"error": "ats_score must be between 0 and 100"}), 400

    try:
        result = set_job_ats_score(country, company, url, ats_score, user_id=g.user_id)
        return jsonify({"ok": True, **result})
    except LookupError as e:
        return jsonify({"error": str(e)}), 404
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.patch("/api/jobs/waiting-referral")
@app.post("/api/jobs/waiting-referral")
@login_required
def api_jobs_waiting_referral():
    body = request.get_json(silent=True) or {}
    country = body.get("country", "")
    company = body.get("company", "")
    url = body.get("url", "")
    waiting_referral = bool(body.get("waiting_referral", True))
    linkedin_url = (body.get("linkedin_url") or body.get("referral_linkedin_url") or "").strip()

    if not country or country == "all":
        return jsonify({"error": "country is required (not 'all')"}), 400
    if country not in COUNTRY_FILES:
        return jsonify({"error": f"Unknown country: {country}"}), 400
    if not company or not url:
        return jsonify({"error": "company and url are required"}), 400

    try:
        result = set_job_waiting_referral(
            country,
            company,
            url,
            waiting_referral,
            user_id=g.user_id,
            linkedin_url=linkedin_url,
        )
        return jsonify({"ok": True, **result})
    except LookupError as e:
        return jsonify({"error": str(e)}), 404
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.post("/api/jobs/not-for-me")
@login_required
def api_jobs_not_for_me():
    body = request.get_json(silent=True) or {}
    country = body.get("country", "")
    company = body.get("company", "")
    url = body.get("url", "")
    not_for_me = bool(body.get("not_for_me", True))
    reason = (body.get("reason") or "").strip() or None

    if not country or country == "all":
        return jsonify({"error": "country is required (not 'all')"}), 400
    if country not in COUNTRY_FILES:
        return jsonify({"error": f"Unknown country: {country}"}), 400
    if not company or not url:
        return jsonify({"error": "company and url are required"}), 400

    try:
        result = set_job_not_for_me(
            country,
            company,
            url,
            user_id=g.user_id,
            not_for_me=not_for_me,
            reason=reason,
        )
        return jsonify({"ok": True, **result})
    except LookupError as e:
        return jsonify({"error": str(e)}), 404
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.patch("/api/jobs/looking-to-apply")
@app.post("/api/jobs/looking-to-apply")
@login_required
def api_jobs_looking_to_apply():
    body = request.get_json(silent=True) or {}
    country = body.get("country", "")
    company = body.get("company", "")
    url = body.get("url", "")
    looking_to_apply = bool(body.get("looking_to_apply", True))

    if not country or country == "all":
        return jsonify({"error": "country is required (not 'all')"}), 400
    if country not in COUNTRY_FILES:
        return jsonify({"error": f"Unknown country: {country}"}), 400
    if not company or not url:
        return jsonify({"error": "company and url are required"}), 400

    try:
        result = set_job_looking_to_apply(country, company, url, looking_to_apply, user_id=g.user_id)
        return jsonify({"ok": True, **result})
    except LookupError as e:
        return jsonify({"error": str(e)}), 404
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.patch("/api/jobs/seen")
@app.post("/api/jobs/seen")
@login_required
def api_jobs_seen():
    body = request.get_json(silent=True) or {}
    country = body.get("country", "")
    company = body.get("company", "")
    url = body.get("url", "")
    seen = bool(body.get("seen", True))

    if not country or country == "all":
        return jsonify({"error": "country is required (not 'all')"}), 400
    if country not in COUNTRY_FILES:
        return jsonify({"error": f"Unknown country: {country}"}), 400
    if not company or not url:
        return jsonify({"error": "company and url are required"}), 400

    try:
        result = set_job_seen(country, company, url, seen, user_id=g.user_id)
        return jsonify({"ok": True, **result})
    except LookupError as e:
        return jsonify({"error": str(e)}), 404
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.patch("/api/companies/applied")
@app.post("/api/companies/applied")
@login_required
def api_companies_applied():
    body = request.get_json(silent=True) or {}
    country = body.get("country", "")
    company = body.get("company", "")
    applied = bool(body.get("applied", body.get("company_applied", True)))

    if not country or country == "all":
        return jsonify({"error": "country is required (not 'all')"}), 400
    if country not in COUNTRY_FILES:
        return jsonify({"error": f"Unknown country: {country}"}), 400
    if not company:
        return jsonify({"error": "company is required"}), 400

    try:
        result = set_company_applied(country, company, applied, user_id=g.user_id)
        return jsonify({"ok": True, **result})
    except LookupError as e:
        return jsonify({"error": str(e)}), 404
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.patch("/api/companies/awaiting-response")
@app.post("/api/companies/awaiting-response")
@login_required
def api_companies_awaiting_response():
    body = request.get_json(silent=True) or {}
    country = body.get("country", "")
    company = body.get("company", "")
    awaiting = bool(body.get("awaiting_response", body.get("awaiting", True)))

    if not country or country == "all":
        return jsonify({"error": "country is required (not 'all')"}), 400
    if country not in COUNTRY_FILES:
        return jsonify({"error": f"Unknown country: {country}"}), 400
    if not company:
        return jsonify({"error": "company is required"}), 400

    try:
        result = set_company_awaiting_response(
            country, company, awaiting, user_id=g.user_id
        )
        return jsonify({"ok": True, **result})
    except LookupError as e:
        return jsonify({"error": str(e)}), 404
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.post("/api/companies")
@login_required
def api_companies_add():
    body = request.get_json(silent=True) or {}
    country = (body.get("country") or "").strip().lower()
    countries = body.get("countries")
    name = body.get("name", "")
    careers_url = body.get("careers_url", "")
    ats_hint = (body.get("ats") or body.get("ats_hint") or "").strip().lower()
    locations = body.get("locations")

    if not name.strip():
        return jsonify({"error": "Company name is required"}), 400
    if not careers_url.strip():
        return jsonify({"error": "Careers page URL is required"}), 400

    country_keys: list[str] | None = None
    if isinstance(countries, list) and countries:
        country_keys = [
            (item or "").strip().lower()
            for item in countries
            if (item or "").strip()
        ]
        for key in country_keys:
            if key not in COUNTRY_FILES:
                return jsonify({"error": f"Unknown country: {key}"}), 400
    else:
        country_hint = None if country in ("", "auto", "all") else country
        if country_hint and country_hint not in COUNTRY_FILES:
            return jsonify({"error": f"Unknown country: {country}"}), 400
        if country_hint:
            country_keys = [country_hint]

    if locations is not None and not isinstance(locations, list):
        return jsonify({"error": "locations must be an array"}), 400

    valid_ats = {item["id"] for item in list_ats_types()}
    if ats_hint and ats_hint not in ("auto", "") and ats_hint not in valid_ats:
        return jsonify({"error": f"Unknown ATS: {ats_hint}"}), 400
    ats_hint_arg = None if ats_hint in ("", "auto") else ats_hint

    try:
        result = add_company(
            name,
            careers_url,
            country_keys[0] if country_keys else None,
            country_keys=country_keys,
            ats_hint=ats_hint_arg,
            locations=locations,
        )
        return jsonify({"ok": True, "company": result})
    except LookupError as e:
        return jsonify({"error": str(e)}), 409
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.delete("/api/companies")
@app.post("/api/companies/remove")
@login_required
def api_companies_remove():
    body = request.get_json(silent=True) or {}
    country = (body.get("country") or "").strip().lower()
    company = (body.get("company") or "").strip()

    if not country or country == "all":
        return jsonify({"error": "country is required (not 'all')"}), 400
    if country not in COUNTRY_FILES:
        return jsonify({"error": f"Unknown country: {country}"}), 400
    if not company:
        return jsonify({"error": "company is required"}), 400

    try:
        company = resolve_company_name(country, company)
        result = remove_company(country, company)
        return jsonify({"ok": True, **result})
    except LookupError as e:
        return jsonify({"error": str(e)}), 404
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.patch("/api/companies/name")
@app.post("/api/companies/name")
@login_required
def api_companies_rename():
    body = request.get_json(silent=True) or {}
    country = (body.get("country") or "").strip().lower()
    company = (body.get("company") or "").strip()
    new_name = (body.get("new_name") or body.get("name") or "").strip()

    if not country or country == "all":
        return jsonify({"error": "country is required (not 'all')"}), 400
    if country not in COUNTRY_FILES:
        return jsonify({"error": f"Unknown country: {country}"}), 400
    if not company:
        return jsonify({"error": "company is required"}), 400
    if not new_name:
        return jsonify({"error": "new_name is required"}), 400

    try:
        company = resolve_company_name(country, company)
        result = rename_company(country, company, new_name)
        return jsonify({"ok": True, **result})
    except LookupError as e:
        return jsonify({"error": str(e)}), 409 if "already exists" in str(e).lower() else 404
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.patch("/api/companies/careers")
@app.post("/api/companies/careers")
@login_required
def api_companies_careers():
    body = request.get_json(silent=True) or {}
    country = (body.get("country") or "").strip().lower()
    company = (body.get("company") or "").strip()
    careers_url = body.get("careers_url", "")
    redetect_ats = bool(body.get("redetect_ats", True))

    if not country or country == "all":
        return jsonify({"error": "country is required (not 'all')"}), 400
    if country not in COUNTRY_FILES:
        return jsonify({"error": f"Unknown country: {country}"}), 400
    if not company:
        return jsonify({"error": "company is required"}), 400
    if not careers_url.strip():
        return jsonify({"error": "careers_url is required"}), 400

    try:
        company = resolve_company_name(country, company)
        result = update_company_careers(
            country, company, careers_url, redetect_ats=redetect_ats
        )
        return jsonify({"ok": True, **result})
    except LookupError as e:
        return jsonify({"error": str(e)}), 404
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.patch("/api/companies/city")
@app.post("/api/companies/city")
@login_required
def api_companies_city():
    body = request.get_json(silent=True) or {}
    country = (body.get("country") or "").strip().lower()
    company = (body.get("company") or "").strip()
    cities = body.get("cities")
    locations = body.get("locations")
    if locations is None and cities is None:
        legacy_city = (body.get("city") or "").strip()
        cities = [legacy_city] if legacy_city else []
    elif locations is not None and not isinstance(locations, list):
        return jsonify({"error": "locations must be an array"}), 400
    elif cities is not None and not isinstance(cities, list):
        return jsonify({"error": "cities must be an array"}), 400

    if not country or country == "all":
        return jsonify({"error": "country is required (not 'all')"}), 400
    if country not in COUNTRY_FILES:
        return jsonify({"error": f"Unknown country: {country}"}), 400
    if not company:
        return jsonify({"error": "company is required"}), 400

    try:
        company = resolve_company_name(country, company)
        result = update_company_city(
            country,
            company,
            cities=cities,
            locations=locations,
        )
        restored = reconcile_wrong_location_hides(g.user_id, country_key=country)
        return jsonify({"ok": True, **result, "restored_jobs": restored})
    except LookupError as e:
        return jsonify({"error": str(e)}), 404
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.patch("/api/companies/fetch-problem")
@app.post("/api/companies/fetch-problem")
@login_required
def api_companies_fetch_problem():
    body = request.get_json(silent=True) or {}
    country = (body.get("country") or "").strip().lower()
    company = (body.get("company") or "").strip()
    fetch_problem = bool(body.get("fetch_problem", True))
    mark_fetch_ok = bool(body.get("mark_fetch_ok", False))

    if not country or country == "all":
        return jsonify({"error": "country is required (not 'all')"}), 400
    if country not in COUNTRY_FILES:
        return jsonify({"error": f"Unknown country: {country}"}), 400
    if not company:
        return jsonify({"error": "company is required"}), 400

    try:
        company = resolve_company_name(country, company)
        result = set_company_fetch_problem(
            country, company, fetch_problem, mark_fetch_ok=mark_fetch_ok
        )
        return jsonify({"ok": True, **result})
    except LookupError as e:
        return jsonify({"error": str(e)}), 404
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.post("/api/companies/fetch-ok")
@login_required
def api_companies_fetch_ok():
    body = request.get_json(silent=True) or {}
    country = (body.get("country") or "").strip().lower()
    company = (body.get("company") or "").strip()

    if not country or country == "all":
        return jsonify({"error": "country is required (not 'all')"}), 400
    if country not in COUNTRY_FILES:
        return jsonify({"error": f"Unknown country: {country}"}), 400
    if not company:
        return jsonify({"error": "company is required"}), 400

    try:
        company = resolve_company_name(country, company)
        result = set_company_fetch_ok(country, company)
        return jsonify({"ok": True, **result})
    except LookupError as e:
        return jsonify({"error": str(e)}), 404
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.get("/api/fetch/status")
@login_required
def api_fetch_status():
    _reap_zombie_fetch()
    with _fetch_lock:
        return jsonify({
            "running": _fetch_state["running"],
            "country": _fetch_state["country"],
            "company": _fetch_state.get("company"),
            "file": _fetch_state["file"],
            "started_at": _fetch_state["started_at"],
            "finished_at": _fetch_state["finished_at"],
            "exit_code": _fetch_state["exit_code"],
            "concurrency": _fetch_state.get("concurrency"),
            "result_line": _fetch_state.get("result_line"),
            "cancel_requested": _fetch_state.get("cancel_requested", False),
            "cancelled": _fetch_state.get("cancelled", False),
            "progress": dict(_fetch_state.get("progress") or {}),
            "activity": dict(_fetch_state.get("activity") or {}),
            "activity_log": list(_fetch_state.get("activity_log") or []),
            "log": list(_fetch_state["log"]),
            "review_jobs": _fetch_state.get("review_jobs"),
            "new_jobs_total": int(_fetch_state.get("new_jobs_total") or 0),
            "last_fetch_run": _fetch_state.get("last_fetch_run"),
        })


@app.get("/api/fetch/history")
@admin_required
def api_fetch_history():
    country = (request.args.get("country") or "").strip().lower() or None
    if country and country not in COUNTRY_FILES:
        return jsonify({"error": f"Unknown country: {country}"}), 400
    try:
        limit = int(request.args.get("limit", 20))
    except (TypeError, ValueError):
        limit = 20
    return jsonify({
        "runs": list_fetch_runs(g.user_id, country=country, limit=limit),
    })


@app.post("/api/fetch/cancel")
@login_required
def api_fetch_cancel():
    proc = None
    with _fetch_lock:
        if not _fetch_state["running"]:
            return jsonify({"error": "No fetch is running"}), 400
        if not _fetch_state.get("company") and not is_user_admin(g.user_id):
            return jsonify({"error": "Admin access required"}), 403
        _fetch_state["cancel_requested"] = True
        proc = _fetch_state.get("process")
    _terminate_scrape_process(proc)
    return jsonify({"ok": True})


def _start_scrape_thread(
    country: str,
    skip_filled: bool,
    concurrency: int,
    *,
    company: str | None = None,
) -> None:
    global _fetch_thread
    workers = _fetch_state["concurrency"]
    _fetch_thread = threading.Thread(
        target=_run_scrape,
        args=(country, skip_filled, workers),
        kwargs={"company": company},
        daemon=True,
    )
    _fetch_thread.start()


@app.post("/api/companies/jobs/manual-add")
@login_required
def api_companies_jobs_manual_add():
    body = request.get_json(silent=True) or {}
    country = (body.get("country") or "").strip().lower()
    company = (body.get("company") or "").strip()
    jobs = body.get("jobs") or []

    if not country or country == "all":
        return jsonify({"error": "country is required (not 'all')"}), 400
    if country not in COUNTRY_FILES:
        return jsonify({"error": f"Unknown country: {country}"}), 400
    if not company:
        return jsonify({"error": "company is required"}), 400
    if not isinstance(jobs, list) or not jobs:
        return jsonify({"error": "jobs must be a non-empty list"}), 400

    try:
        company = resolve_company_name(country, company)
        result = add_manual_jobs(country, company, jobs)
        return jsonify({"ok": True, **result})
    except LookupError as e:
        return jsonify({"error": str(e)}), 404
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.post("/api/companies/fetch")
@login_required
def api_companies_fetch():
    body = request.get_json(silent=True) or {}
    country = body.get("country", "")
    company = (body.get("company") or "").strip()

    if not scrape_enabled():
        return jsonify({
            "error": "Scraping is disabled on this host. Run scrapes locally, then git push the JSON files.",
        }), 503

    if not HTTPX_AVAILABLE:
        return jsonify({
            "error": "httpx is not installed. Run: pip install httpx",
        }), 503

    if not country or country == "all":
        return jsonify({"error": "country is required (not 'all')"}), 400
    if country not in COUNTRY_FILES:
        return jsonify({"error": f"Unknown country: {country}"}), 400
    if not company:
        return jsonify({"error": "company is required"}), 400

    try:
        company = resolve_company_name(country, company)
    except LookupError as e:
        return jsonify({"error": str(e)}), 404

    with _fetch_lock:
        _reap_zombie_fetch()
        if _fetch_state["running"]:
            return jsonify({"error": "A fetch is already running"}), 409

        _reset_fetch_run_state(
            country=country,
            company=company,
            file_name=COUNTRY_FILES[country],
            concurrency=1,
            user_id=g.user_id,
        )

    try:
        touch_company_fetch_time(country, company)
    except (LookupError, ValueError) as e:
        return jsonify({"error": str(e)}), 404

    _start_scrape_thread(country, skip_filled=False, concurrency=1, company=company)

    return jsonify({
        "ok": True,
        "country": country,
        "company": company,
        "file": COUNTRY_FILES[country],
        "message": f"Fetching jobs for {company} ({COUNTRY_LABELS[country]})",
    })


@app.post("/api/fetch")
@admin_required
def api_fetch():
    body = request.get_json(silent=True) or {}
    country = body.get("country", "netherlands")
    skip_filled = bool(body.get("skip_filled", False))
    concurrency = int(body.get("concurrency", body.get("workers", DEFAULT_CONCURRENCY)))

    if not scrape_enabled():
        return jsonify({
            "error": "Scraping is disabled on this host. Run scrapes locally, then git push the JSON files.",
        }), 503

    if not HTTPX_AVAILABLE:
        return jsonify({
            "error": "httpx is not installed. Run: pip install httpx",
        }), 503

    if country == "all":
        return jsonify({"error": "Select a single country to fetch (not 'all')"}), 400
    if country not in COUNTRY_FILES:
        return jsonify({"error": f"Unknown country: {country}"}), 400

    with _fetch_lock:
        _reap_zombie_fetch()
        if _fetch_state["running"]:
            return jsonify({"error": "A fetch is already running"}), 409

        workers = max(1, min(concurrency, 64))
        _reset_fetch_run_state(
            country=country,
            company=None,
            file_name=COUNTRY_FILES[country],
            concurrency=workers,
            user_id=g.user_id,
        )

    _start_scrape_thread(country, skip_filled, workers)

    return jsonify({
        "ok": True,
        "country": country,
        "file": COUNTRY_FILES[country],
        "concurrency": workers,
        "message": (
            f"Started scraping {COUNTRY_LABELS[country]} "
            f"({workers} concurrent, asyncio)"
        ),
    })


def main():
    port = int(os.environ.get("PORT", "5050"))
    host = "0.0.0.0" if os.environ.get("PORT") else "127.0.0.1"
    print(f"Job panel: http://{host}:{port}")
    app.run(host=host, port=port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
