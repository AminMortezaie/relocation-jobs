from __future__ import annotations

from tests.helpers.route_manifest import (
    PANEL_API_ROUTES,
    REQUIRED_ROUTES,
    V2_ONLY_ROUTES,
)


def _registered_routes(app) -> dict[str, frozenset[str]]:
    out: dict[str, set[str]] = {}
    for rule in app.url_map.iter_rules():
        if rule.endpoint == "static":
            continue
        methods = {m for m in rule.methods if m not in ("HEAD", "OPTIONS")}
        out.setdefault(rule.rule, set()).update(methods)
    return {path: frozenset(methods) for path, methods in out.items()}


def test_v2_registers_panel_route_manifest(v2_app):
    registered = _registered_routes(v2_app)
    missing: list[str] = []
    wrong_methods: list[str] = []

    for path, want_methods in REQUIRED_ROUTES.items():
        if path not in registered:
            missing.append(path)
            continue
        have = registered[path]
        if not want_methods <= have:
            wrong_methods.append(
                f"{path}: want {sorted(want_methods)}, have {sorted(have)}"
            )

    assert not missing, f"missing routes: {missing}"
    assert not wrong_methods, f"method mismatch: {wrong_methods}"


def test_static_js_api_paths_covered_by_manifest():
    from pathlib import Path
    import re

    from relocation_jobs.core.paths import STATIC_DIR

    root = STATIC_DIR / "js"
    paths: set[str] = set()
    for name in ("api.js", "admin.js", "auth.js"):
        text = (root / name).read_text(encoding="utf-8")
        paths |= set(re.findall(r'apiFetch\(\s*["`](/api/[^"`?]+)', text))
        paths |= set(re.findall(r'apiGet\(\s*["`](/api/[^"`?]+)', text))
        paths |= set(re.findall(r'fetch\(\s*["`](/api/[^"`?]+)', text))

    manifest_paths = set(PANEL_API_ROUTES)
    literal_manifest = {p for p in manifest_paths if "<" not in p}

    uncovered = sorted(
        p for p in paths
        if p not in literal_manifest
        and not any(p.startswith(m.split("<")[0].rstrip("/")) for m in manifest_paths if "<" in m)
    )
    assert not uncovered, (
        f"static/js/api.js calls not in manifest (update route_manifest.py): {uncovered}"
    )


def test_v2_only_routes_are_documented():
    assert V2_ONLY_ROUTES <= set(REQUIRED_ROUTES)
