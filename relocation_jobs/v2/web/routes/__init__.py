from __future__ import annotations

from flask import Flask

from relocation_jobs.v2.web.routes import auth, catalog, fetch, jobs


def register_routes(app: Flask) -> None:
    for module in (auth, catalog, fetch, jobs):
        module.register(app)
