/** Client-side panel view filters (catalog scope stays on the server). */

import { $ } from "./utils.js";

function readFlag(id) {
  return Boolean(document.getElementById(id)?.checked);
}

export function panelFilterFlags() {
  return {
    visaOnly: readFlag("visaOnly"),
    hideApplied: readFlag("hideApplied"),
    hideEmpty: readFlag("hideEmpty"),
    notAppliedOnly: readFlag("notAppliedOnly"),
    hidePositionApplied: readFlag("hidePositionApplied"),
    hidePositionRejected: readFlag("hidePositionRejected"),
    positionAppliedOnly: readFlag("positionAppliedOnly"),
    positionRejectedOnly: readFlag("positionRejectedOnly"),
    positionLookingToApplyOnly: readFlag("positionLookingToApplyOnly"),
    fetchOkOnly: readFlag("fetchOkOnly"),
    fetchProblemOnly: readFlag("fetchProblemOnly"),
  };
}

function includeJobForPanelFilters(job, flags) {
  const applied = Boolean(job?.applied);
  const rejected = Boolean(job?.rejected);
  const lookingToApply = Boolean(job?.looking_to_apply);
  if (flags.hidePositionApplied && applied) return false;
  if (flags.hidePositionRejected && rejected) return false;
  if (flags.positionAppliedOnly && !applied) return false;
  if (flags.positionRejectedOnly && !rejected) return false;
  if (flags.positionLookingToApplyOnly && !lookingToApply) return false;
  return true;
}

function filterOpenJobs(jobs, flags) {
  let list = Array.isArray(jobs) ? jobs : [];
  if (flags.visaOnly) {
    list = list.filter((job) => job.visa_sponsorship === true);
  }
  return list.filter((job) => includeJobForPanelFilters(job, flags));
}

function filterRejectedJobs(jobs, flags) {
  let list = Array.isArray(jobs) ? jobs : [];
  if (flags.hidePositionRejected) return [];
  if (flags.visaOnly) {
    list = list.filter((job) => job.visa_sponsorship === true);
  }
  return list.filter((job) => includeJobForPanelFilters(job, flags));
}

function companyViewRow(company, flags) {
  const jobs = filterOpenJobs(company.jobs, flags);
  const rejectedJobs = filterRejectedJobs(company.rejected_jobs, flags);
  const notForMeJobs = company.not_for_me_jobs || company.hidden_jobs || [];
  const positionsApplied = jobs.filter((job) => job.applied).length;
  return {
    ...company,
    jobs,
    rejected_jobs: rejectedJobs,
    not_for_me_jobs: notForMeJobs,
    job_count: jobs.length,
    positions_applied: positionsApplied,
    positions_rejected: rejectedJobs.length,
    positions_not_for_me: notForMeJobs.length,
  };
}

function includeCompany(view, flags) {
  if (flags.hideApplied && view.company_applied) return false;
  if (flags.fetchOkOnly && !(view.fetch_ok && !view.fetch_problem)) return false;
  if (flags.fetchProblemOnly && !view.fetch_problem) return false;
  if (flags.visaOnly && !view.jobs.length && !view.rejected_jobs.length) return false;
  if (flags.positionRejectedOnly && !view.rejected_jobs.length) return false;
  if ((flags.positionAppliedOnly || flags.positionLookingToApplyOnly) && !view.jobs.length) {
    return false;
  }
  if (
    flags.hideEmpty
    && !view.jobs.length
    && !(flags.positionRejectedOnly && view.rejected_jobs.length)
  ) {
    return false;
  }
  if (flags.notAppliedOnly && (view.company_applied || !view.jobs.length)) return false;
  return true;
}

export function applyPanelFilters(catalog, flags = panelFilterFlags()) {
  return (catalog || [])
    .map((company) => companyViewRow(company, flags))
    .filter((view) => includeCompany(view, flags));
}

export function shouldShowCompanyOnBoard(company, flags = panelFilterFlags()) {
  return includeCompany(companyViewRow(company, flags), flags);
}

export function computeViewStats(companies, meta = {}) {
  let totalJobs = 0;
  let visaSponsored = 0;
  let positionsRejected = 0;
  let companiesApplied = 0;
  let latestJobFetch = "";

  for (const company of companies || []) {
    for (const job of company.jobs || []) {
      if (job.applied) continue;
      totalJobs += 1;
      if (job.visa_sponsorship === true) visaSponsored += 1;
    }
    positionsRejected += company.positions_rejected ?? company.rejected_jobs?.length ?? 0;
    if (company.company_applied || (company.positions_applied_all ?? company.positions_applied ?? 0) > 0) {
      companiesApplied += 1;
    }
    const fetchTs = (company.newest_job_fetched || company.latest_fetched || "").trim();
    if (fetchTs && fetchTs.localeCompare(latestJobFetch) > 0) {
      latestJobFetch = fetchTs;
    }
  }

  const companiesWithOpen = (companies || []).filter(
    (company) => (company.jobs || []).some((job) => !job.applied)
  ).length;

  return {
    total_jobs: totalJobs,
    companies_with_jobs: companiesWithOpen,
    visa_sponsored: visaSponsored,
    applied: companiesApplied,
    positions_rejected: positionsRejected,
    fetch_problems: meta.fetch_problem_total ?? 0,
    latest_job_fetch: latestJobFetch,
    latest_fetch_new_jobs: meta.latest_fetch_new_jobs ?? 0,
  };
}

export function mergeBoardStats(viewStats, userStats = {}) {
  return {
    ...viewStats,
    positions_applied: userStats.positions_applied ?? 0,
    positions_applied_today: userStats.positions_applied_today ?? 0,
    applied_today_jobs: userStats.applied_today_jobs || [],
    recent_fetch_runs: userStats.recent_fetch_runs || [],
    latest_fetch_new_jobs: userStats.latest_fetch_new_jobs ?? viewStats.latest_fetch_new_jobs ?? 0,
  };
}
