"""
Public API for the db package.

Every name that was previously importable from ``relocation_jobs.db`` is
re-exported here, so all existing call sites continue to work unchanged:

    from relocation_jobs.db import set_job_applied_db, get_connection, ...
"""

from relocation_jobs.core.db import (
    db_read,
    db_transaction,
    get_connection,
    init_db,
    reset_db_initialized,
)

from relocation_jobs.db.events import (
    _local_day_utc_bounds,
    count_jobs_applied_db,
    count_jobs_applied_today_db,
    list_jobs_applied_today_db,
    load_job_status_history,
)

from relocation_jobs.db.users import (
    admin_tracking_totals,
    create_user,
    get_user_by_id,
    get_user_by_username,
    is_user_admin,
    list_users_with_stats,
    rename_user,
    update_user_password,
    user_count,
)

from relocation_jobs.db.tracking import (
    load_job_tracking,
    load_wrong_location_hides_db,
    reapply_job_db,
    set_job_applied_db,
    set_job_ats_score_db,
    set_job_looking_to_apply_db,
    set_job_not_for_me_db,
    set_job_rejected_db,
    set_job_seen_db,
    set_job_waiting_referral_db,
)

from relocation_jobs.db.companies import (
    clear_company_tracking,
    load_company_tracking,
    rename_company_tracking,
    set_company_applied_db,
    set_company_awaiting_response_db,
    sync_company_applied_from_jobs_db,
)

from relocation_jobs.db.fetch_runs import (
    list_all_fetch_runs,
    list_fetch_runs,
    migrate_tracking_from_json,
    record_fetch_run,
    tracking_is_empty,
)

__all__ = [
    # core
    "db_read",
    "db_transaction",
    "get_connection",
    "init_db",
    "reset_db_initialized",
    # events
    "count_jobs_applied_db",
    "count_jobs_applied_today_db",
    "list_jobs_applied_today_db",
    "load_job_status_history",
    # users
    "admin_tracking_totals",
    "create_user",
    "get_user_by_id",
    "get_user_by_username",
    "is_user_admin",
    "list_users_with_stats",
    "rename_user",
    "update_user_password",
    "user_count",
    # tracking
    "load_job_tracking",
    "load_wrong_location_hides_db",
    "reapply_job_db",
    "set_job_applied_db",
    "set_job_ats_score_db",
    "set_job_looking_to_apply_db",
    "set_job_not_for_me_db",
    "set_job_rejected_db",
    "set_job_seen_db",
    "set_job_waiting_referral_db",
    # companies
    "clear_company_tracking",
    "load_company_tracking",
    "rename_company_tracking",
    "set_company_applied_db",
    "set_company_awaiting_response_db",
    "sync_company_applied_from_jobs_db",
    # fetch_runs
    "list_all_fetch_runs",
    "list_fetch_runs",
    "migrate_tracking_from_json",
    "record_fetch_run",
    "tracking_is_empty",
]
