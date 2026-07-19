from __future__ import annotations

import os

from flask import Flask, Response, redirect, request, send_from_directory

from relocation_jobs.core.auth import init_auth
from relocation_jobs.core.db import get_connection
from relocation_jobs.core.location_tags import all_country_labels
from relocation_jobs.core.paths import PROJECT_ROOT, STATIC_DIR
from relocation_jobs.db import init_db
from relocation_jobs.db.migrate import apply_v2_migrations
from relocation_jobs.fetch.log import configure_fetch_logging
from relocation_jobs.web.routes import register_routes

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

ROOT = PROJECT_ROOT
STATIC = STATIC_DIR
HOMEPAGE_STATIC = STATIC / "homepage"

FIXED_MARKETING_PATHS = (
    "/",
    "/how-it-works",
    "/pricing",
)

PRIVATE_ROBOTS_DISALLOW = (
    "/panel",
    "/admin",
    "/apply",
    "/company",
    "/api/",
)


def _public_site_url() -> str:
    return (os.environ.get("PUBLIC_SITE_URL") or "https://kuchup.com").strip().rstrip("/")


def _country_marketing_path(country_key: str) -> str:
    return f"/relocation-jobs-{country_key}"


def _country_html_exists(country_key: str) -> bool:
    return (HOMEPAGE_STATIC / f"relocation-jobs-{country_key}.html").is_file()


def _country_key_from_marketing_path(path: str) -> str | None:
    prefix = "/relocation-jobs-"
    if not path.startswith(prefix):
        return None
    key = path[len(prefix):].strip().lower()
    return key or None


def public_marketing_paths() -> tuple[str, ...]:
    country_paths = tuple(
        _country_marketing_path(key)
        for key in sorted(all_country_labels())
        if _country_html_exists(key)
    )
    return FIXED_MARKETING_PATHS + country_paths

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
    return redirect("/panel", code=301)


@app.route("/company/<country>/<path:company_slug>")
def company_workspace_page(country, company_slug):
    resp = send_from_directory(STATIC, "company.html")
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/")
def public_home_page():
    if (HOMEPAGE_STATIC / "index.html").is_file():
        resp = send_from_directory(HOMEPAGE_STATIC, "index.html")
    else:
        resp = send_from_directory(STATIC, "public.html")
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/_next/<path:asset_path>")
def homepage_next_assets(asset_path):
    resp = send_from_directory(HOMEPAGE_STATIC / "_next", asset_path)
    if resp.status_code == 200:
        resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return resp


@app.route("/icon.svg")
def homepage_icon():
    if (HOMEPAGE_STATIC / "icon.svg").is_file():
        resp = send_from_directory(HOMEPAGE_STATIC, "icon.svg")
        resp.headers["Cache-Control"] = "public, max-age=86400"
        return resp
    return Response(status=404)


@app.route("/brand/<path:asset_path>")
def homepage_brand_assets(asset_path):
    brand_dir = HOMEPAGE_STATIC / "brand"
    target = (brand_dir / asset_path).resolve()
    if not str(target).startswith(str(brand_dir.resolve())) or not target.is_file():
        return Response(status=404)
    resp = send_from_directory(brand_dir, asset_path)
    resp.headers["Cache-Control"] = "public, max-age=86400"
    return resp


@app.route("/panel")
def panel_page():
    resp = send_from_directory(STATIC, "index.html")
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/preview")
def preview_page():
    return redirect("/", code=301)


@app.route("/robots.txt")
def robots_txt():
    public_site_url = _public_site_url()
    disallow_lines = "\n".join(f"Disallow: {p}" for p in PRIVATE_ROBOTS_DISALLOW)
    body = "\n".join((
        "User-agent: *",
        "Allow: /",
        disallow_lines,
        "",
        f"Sitemap: {public_site_url}/sitemap.xml",
        "",
    ))
    return Response(body, mimetype="text/plain")


@app.route("/sitemap.xml")
def sitemap_xml():
    public_site_url = _public_site_url()
    urls = "\n".join(
        f"  <url>\n    <loc>{public_site_url}{path}</loc>\n  </url>"
        for path in public_marketing_paths()
    )
    body = "\n".join((
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        urls,
        "</urlset>",
        "",
    ))
    return Response(body, mimetype="application/xml")


register_routes(app)


def _is_marketing_path(path: str) -> bool:
    if path in FIXED_MARKETING_PATHS and path != "/":
        return True
    country_key = _country_key_from_marketing_path(path)
    if not country_key or not _country_html_exists(country_key):
        return False
    return country_key in all_country_labels()


# Marketing route catch-all — must be the final route so Flask matches
# all explicit routes (panel, admin, robots, sitemap, api/*, etc.) first.
def _marketing_404():
    not_found = HOMEPAGE_STATIC / "404.html"
    if not_found.is_file():
        resp = send_from_directory(HOMEPAGE_STATIC, "404.html")
        resp.headers["Cache-Control"] = "no-store"
        resp.status_code = 404
        return resp
    return Response(status=404)


@app.route("/<path:slug>")
def marketing_page(slug: str):
    path = f"/{slug}"
    if not _is_marketing_path(path):
        return _marketing_404()
    segment = slug.rstrip("/")
    filename = f"{segment}.html"
    index = HOMEPAGE_STATIC / filename
    if not index.is_file():
        return _marketing_404()
    resp = send_from_directory(HOMEPAGE_STATIC, filename)
    resp.headers["Cache-Control"] = "no-store"
    return resp
