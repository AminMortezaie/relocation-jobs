from __future__ import annotations

from flask import Flask, request, send_from_directory

from relocation_jobs.core.auth import init_auth
from relocation_jobs.core.paths import PROJECT_ROOT, STATIC_DIR
from relocation_jobs.v2.db.migrate import apply_v2_migrations
from relocation_jobs.v2.web.routes import register_routes

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
    from relocation_jobs.core.db import get_connection
    from relocation_jobs.db import init_db
    from relocation_jobs.v2.fetch import repo as fetch_repo

    init_db()
    apply_v2_migrations(get_connection())
    fetch_repo.reap_orphan_running_fetch_runs()
    init_auth(app)
    _bootstrapped = True


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


@app.route("/admin")
def admin_page():
    resp = send_from_directory(STATIC, "admin.html")
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/")
def index():
    resp = send_from_directory(STATIC, "index.html")
    resp.headers["Cache-Control"] = "no-store"
    return resp


register_routes(app)
