from relocation_jobs.companies import service as companies
from relocation_jobs.positions import service as positions

set_job_applied = positions.set_job_applied
set_job_rejected = positions.set_job_rejected
set_job_reapply = positions.set_job_reapply
set_job_ats_score = positions.set_job_ats_score
set_job_waiting_referral = positions.set_job_waiting_referral
set_job_not_for_me = positions.set_job_not_for_me
set_job_looking_to_apply = positions.set_job_looking_to_apply
set_job_seen = positions.set_job_seen
set_job_pinned = positions.set_job_pinned
reconcile_wrong_location_hides = positions.reconcile_wrong_location_hides

add_company = companies.add_company
add_manual_jobs = companies.add_manual_jobs
list_ats_types = companies.list_ats_types
remove_company = companies.remove_company
rename_company = companies.rename_company
resolve_company_name = companies.resolve_company_name
set_company_applied = companies.set_company_applied
set_company_awaiting_response = companies.set_company_awaiting_response
set_company_fetch_ok = companies.set_company_fetch_ok
set_company_fetch_problem = companies.set_company_fetch_problem
touch_company_fetch_time = companies.touch_company_fetch_time
update_company_careers = companies.update_company_careers
update_company_city = companies.update_company_city
