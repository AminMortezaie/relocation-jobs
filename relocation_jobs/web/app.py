"""Flask application factory and static page routes."""

from __future__ import annotations

from flask import Flask, request, send_from_directory

from relocation_jobs.core.auth import init_auth
from relocation_jobs.core.paths import PROJECT_ROOT, STATIC_DIR
from relocation_jobs.web.routes import register_routes

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


register_routes(app)
