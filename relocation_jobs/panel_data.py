"""Backward-compatibility shim — logic lives in services/.

All business logic has moved to:
  services/catalog_service.py  — flatten_companies, compute_stats, location helpers
  services/company_service.py  — company CRUD and tracking
  services/job_service.py      — job mutations and tracking
"""

from relocation_jobs.core.location_tags import COUNTRY_LABELS  # noqa: F401
from relocation_jobs.services.catalog_service import (  # noqa: F401
    COUNTRY_FILES,
    _ats_score_value,
    _company_activity_ts,
    _job_dict,
    _load_country_data,
    _resolve_status_history,
    _title_from_tracked_url,
    _tracking_bool,
    compute_stats,
    flatten_companies,
    flatten_jobs,
    list_ats_types,
    list_company_cities,
    list_company_locations,
    now_iso,
    parse_company_cities,
    today,
)
from relocation_jobs.services.company_service import (  # noqa: F401
    add_company,
    add_manual_jobs,
    detect_ats_for_company,
    detect_country_from_url,
    enrich_new_company,
    fetch_relocate_metadata,
    find_company_in_data,
    find_job_in_data,
    normalize_careers_url,
    normalize_company_size,
    parse_country_from_location,
    remove_company,
    rename_company,
    resolve_company_name,
    resolve_country_key,
    set_company_applied,
    set_company_awaiting_response,
    set_company_fetch_ok,
    set_company_fetch_problem,
    touch_company_fetch_time,
    update_company_careers,
    update_company_city,
)
from relocation_jobs.services.job_service import (  # noqa: F401
    _normalize_linkedin_url,
    reconcile_wrong_location_hides,
    set_job_applied,
    set_job_ats_score,
    set_job_looking_to_apply,
    set_job_not_for_me,
    set_job_reapply,
    set_job_rejected,
    set_job_seen,
    set_job_waiting_referral,
)
