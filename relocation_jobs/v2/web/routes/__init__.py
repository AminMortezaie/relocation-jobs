from __future__ import annotations

from flask import Flask

from relocation_jobs.v2.web.routes import admin, auth, catalog, companies, fetch, jobs


def register_routes(app: Flask) -> None:
    for module in (admin, auth, catalog, companies, fetch, jobs):
        module.register(app)
