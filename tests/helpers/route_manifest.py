from __future__ import annotations

PANEL_PAGE_ROUTES: dict[str, frozenset[str]] = {
    "/": frozenset({"GET"}),
    "/admin": frozenset({"GET"}),
}

PANEL_API_ROUTES: dict[str, frozenset[str]] = {
    "/api/auth/status": frozenset({"GET"}),
    "/api/auth/login": frozenset({"POST"}),
    "/api/auth/logout": frozenset({"POST"}),
    "/api/auth/register": frozenset({"POST"}),
    "/api/config": frozenset({"GET"}),
    "/api/countries": frozenset({"GET"}),
    "/api/ats-types": frozenset({"GET"}),
    "/api/cities": frozenset({"GET"}),
    "/api/locations": frozenset({"GET", "POST"}),
    "/api/jobs": frozenset({"GET"}),
    "/api/jobs/applied": frozenset({"PATCH", "POST"}),
    "/api/jobs/rejected": frozenset({"PATCH", "POST"}),
    "/api/jobs/reapply": frozenset({"PATCH", "POST"}),
    "/api/jobs/ats-score": frozenset({"PATCH", "POST"}),
    "/api/jobs/waiting-referral": frozenset({"PATCH", "POST"}),
    "/api/jobs/not-for-me": frozenset({"POST"}),
    "/api/jobs/looking-to-apply": frozenset({"PATCH", "POST"}),
    "/api/jobs/seen": frozenset({"PATCH", "POST"}),
    "/api/board": frozenset({"GET"}),
    "/api/board/stats": frozenset({"GET"}),
    "/api/companies/<country>/<path:company_name>": frozenset({"GET"}),
    "/api/companies/applied": frozenset({"PATCH", "POST"}),
    "/api/companies/awaiting-response": frozenset({"PATCH", "POST"}),
    "/api/companies": frozenset({"POST", "DELETE"}),
    "/api/companies/remove": frozenset({"POST"}),
    "/api/companies/name": frozenset({"PATCH", "POST"}),
    "/api/companies/careers": frozenset({"PATCH", "POST"}),
    "/api/companies/city": frozenset({"PATCH", "POST"}),
    "/api/companies/fetch-problem": frozenset({"PATCH", "POST"}),
    "/api/companies/fetch-ok": frozenset({"POST"}),
    "/api/companies/jobs/manual-add": frozenset({"POST"}),
    "/api/companies/fetch": frozenset({"POST"}),
    "/api/fetch/status": frozenset({"GET"}),
    "/api/fetch/cancel": frozenset({"POST"}),
    "/api/fetch/history": frozenset({"GET"}),
    "/api/fetch": frozenset({"POST"}),
    "/api/fetch/attempts": frozenset({"GET"}),
    "/api/admin/dashboard": frozenset({"GET"}),
    "/api/admin/overview": frozenset({"GET"}),
    "/api/admin/catalog": frozenset({"GET"}),
    "/api/admin/users": frozenset({"GET"}),
    "/api/admin/fetch-runs": frozenset({"GET"}),
    "/api/admin/panel-stats": frozenset({"GET"}),
    "/api/admin/config": frozenset({"GET"}),
}

V2_ONLY_ROUTES: frozenset[str] = frozenset({
    "/api/companies/<country>/<path:company_name>",
    "/api/fetch/attempts",
    "/api/board",
    "/api/board/stats",
})

REQUIRED_ROUTES: dict[str, frozenset[str]] = {
    **PANEL_PAGE_ROUTES,
    **PANEL_API_ROUTES,
}
