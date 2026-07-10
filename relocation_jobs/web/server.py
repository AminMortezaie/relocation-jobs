from __future__ import annotations

import os

from flask import Flask, Response, request, send_from_directory

from relocation_jobs.core.auth import init_auth
from relocation_jobs.core.db import get_connection
from relocation_jobs.core.paths import PROJECT_ROOT, STATIC_DIR
from relocation_jobs.db import init_db
from relocation_jobs.db.migrate import apply_v2_migrations
from relocation_jobs.fetch import repo as fetch_repo
from relocation_jobs.fetch.log import configure_fetch_logging
from relocation_jobs.web.routes import register_routes

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

ROOT = PROJECT_ROOT
STATIC = STATIC_DIR


def _public_site_url() -> str:
    return (os.environ.get("PUBLIC_SITE_URL") or "https://kuchup.com").strip().rstrip("/")

app = Flask(__name__, static_folder=str(STATIC), static_url_path="/static")
app.secret_key = os.environ.get("PANEL_SECRET_KEY", "").strip() or "dev-fallback-key"
_bootstrapped = False


def bootstrap_app() -> None:
    global _bootstrapped
    if _bootstrapped:
        return
    STATIC.mkdir(exist_ok=True)
    if load_dotenv is not None:
        load_dotenv(ROOT / ".env")
    init_db()
    configure_fetch_logging()
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


@app.route("/apply")
def apply_page():
    resp = send_from_directory(STATIC, "apply.html")
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/app")
def app_page():
    resp = send_from_directory(STATIC, "index.html")
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/company/<country>/<path:company_slug>")
def company_workspace_page(country, company_slug):
    resp = send_from_directory(STATIC, "company.html")
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/")
def index():
    resp = send_from_directory(STATIC, "index.html")
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/preview")
def preview_page():
    resp = send_from_directory(STATIC, "public.html")
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/robots.txt")
def robots_txt():
    public_site_url = _public_site_url()
    body = "\n".join((
        "User-agent: *",
        "Allow: /",
        f"Sitemap: {public_site_url}/sitemap.xml",
        "",
    ))
    return Response(body, mimetype="text/plain")


@app.route("/sitemap.xml")
def sitemap_xml():
    public_site_url = _public_site_url()
    body = "\n".join((
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        "  <url>",
        f"    <loc>{public_site_url}/preview</loc>",
        "  </url>",
        "</urlset>",
        "",
    ))
    return Response(body, mimetype="application/xml")


register_routes(app)
