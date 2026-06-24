from __future__ import annotations

from collections.abc import Callable

from flask import jsonify

from relocation_jobs.core.paths import SUPPORTED_COUNTRIES

_JOB_MUTATION_ERROR_RULES: tuple[Callable[[tuple[str, str, str]], tuple | None], ...] = (
    lambda ctx: (
        jsonify({"error": "country is required (not 'all')"}),
        400,
    )
    if not ctx[0] or ctx[0] == "all"
    else None,
    lambda ctx: (
        jsonify({"error": f"Unknown country: {ctx[0]}"}),
        400,
    )
    if ctx[0] not in SUPPORTED_COUNTRIES
    else None,
    lambda ctx: (
        jsonify({"error": "company and url are required"}),
        400,
    )
    if not ctx[1] or not ctx[2]
    else None,
)


def job_mutation_error(body: dict) -> tuple | None:
    ctx = (
        body.get("country", ""),
        body.get("company", ""),
        body.get("url", ""),
    )
    for rule in _JOB_MUTATION_ERROR_RULES:
        err = rule(ctx)
        if err is not None:
            return err
    return None


def job_mutation_fields(body: dict) -> tuple[str, str, str]:
    return body.get("country", ""), body.get("company", ""), body.get("url", "")
