from __future__ import annotations

from flask import Flask

from relocation_jobs.v2.web.routes import auth, catalog, jobs


def register_routes(app: Flask) -> None:
    for module in (auth, catalog, jobs):
        module.register(app)
