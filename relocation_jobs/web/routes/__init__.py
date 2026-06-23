"""Register all panel HTTP route modules."""

from __future__ import annotations

from flask import Flask

from relocation_jobs.web.routes import admin, auth, catalog, companies, fetch, jobs


def register_routes(app: Flask) -> None:
    for module in (auth, admin, catalog, jobs, companies, fetch):
        module.register(app)
