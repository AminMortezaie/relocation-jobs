/** Local job-board updates after tracking mutations (avoid full /api/jobs reload). */

import { applyBoardView } from "./board.js";
import { shouldShowCompanyOnBoard } from "./board-filter.js";
import { recomputeNewestJobFetched } from "./render.js";
import { findCompany, findJobInCompany, state } from "./state.js";

const JOB_PATCH_FIELDS = [
  "applied",
  "applied_date",
  "applied_at",
  "rejected",
  "rejected_date",
  "looking_to_apply",
  "looking_to_apply_date",
  "seen",
  "seen_date",
  "waiting_referral",
  "waiting_referral_date",
  "referral_linkedin_url",
  "ats_score",
  "not_for_me",
  "not_for_me_reason",
  "not_for_me_date",
  "applied_history",
  "applied_events",
  "rejected_history",
  "url",
  "idempotency_key",
  "pinned",
  "pinned_at",
];

function jobMatches(job, url, idempotencyKey = "") {
  if (!job) return false;
  const probe = { jobs: [job] };
  return findJobInCompany(probe, url, idempotencyKey) === job;
}

function mergeJobPatch(job, data) {
  const next = { ...job };
  for (const key of JOB_PATCH_FIELDS) {
    if (data[key] !== undefined) next[key] = data[key];
  }
  if (data.applied === true) {
    next.looking_to_apply = false;
    if (data.looking_to_apply_date === undefined) {
      next.looking_to_apply_date = "";
    }
  }
  if (data.applied === false) {
    if (data.applied_date === undefined) next.applied_date = "";
    if (data.applied_at === undefined) next.applied_at = "";
  }
  if (data.rejected === false && data.rejected_date === undefined) {
    next.rejected_date = "";
  }
  if (data.seen === false && data.seen_date === undefined) {
    next.seen_date = "";
  }
  if (data.waiting_referral === false) {
    if (data.waiting_referral_date === undefined) next.waiting_referral_date = "";
    if (data.referral_linkedin_url === undefined) next.referral_linkedin_url = "";
  }
  return next;
}

function syncCompanyHeaderFromJobs(company, data = {}) {
  const openApplied = (company.jobs || []).filter((job) => job.applied).length;
  const rejectedApplied = (company.rejected_jobs || []).filter((job) => job.applied).length;
  const appliedTotal = openApplied + rejectedApplied;
  company.positions_applied = openApplied;
  company.positions_applied_all = appliedTotal;
  if (appliedTotal > 0) {
    company.company_applied = true;
    if (data.applied_date) company.company_applied_date = data.applied_date;
  } else if (!company.company_applied) {
    company.company_applied_date = "";
    company.company_applied_at = "";
  }
  if (data.applied === true) {
    company.awaiting_response = true;
  }
}

function bucketLists(company) {
  return [
    company.jobs,
    company.rejected_jobs,
    company.not_for_me_jobs,
    company.hidden_jobs,
  ].filter(Array.isArray);
}

export function findJobBucket(company, url, idempotencyKey = "") {
  for (const list of bucketLists(company)) {
    const job = list.find((j) => jobMatches(j, url, idempotencyKey));
    if (job) return { job, list };
  }
  return null;
}

function removeFromList(list, url, idempotencyKey = "") {
  const idx = list.findIndex((j) => jobMatches(j, url, idempotencyKey));
  if (idx < 0) return null;
  return list.splice(idx, 1)[0];
}

function ensureList(company, key) {
  if (!Array.isArray(company[key])) company[key] = [];
  return company[key];
}

function recomputeCounts(company) {
  company.job_count = (company.jobs || []).length;
  company.positions_applied = (company.jobs || []).filter((j) => j.applied).length;
  company.positions_rejected = (company.rejected_jobs || []).length;
  company.positions_not_for_me = (company.not_for_me_jobs || []).length;
  recomputeNewestJobFetched(company);
}

function evictCompanyIfHidden(company) {
  if (shouldShowCompanyOnBoard(company)) return;
  const idx = state.boardCatalog.findIndex(
    (row) => row.country === company.country && row.name === company.name,
  );
  if (idx < 0) return;
  state.boardCatalog.splice(idx, 1);
  if (state.boardMeta.total_companies != null) {
    state.boardMeta.total_companies = Math.max(0, state.boardMeta.total_companies - 1);
  }
  if (state.boardMeta.total_pages != null && state.boardMeta.page_size) {
    state.boardMeta.total_pages = Math.max(
      1,
      Math.ceil(state.boardMeta.total_companies / state.boardMeta.page_size),
    );
  }
}

export function refreshJobBoard() {
  applyBoardView();
}

const JOB_BUCKETS = ["jobs", "rejected_jobs", "not_for_me_jobs", "hidden_jobs"];

function sortPinnedJobsFirst(jobs) {
  if (!jobs?.length) return jobs || [];
  const pinned = jobs.filter((job) => job.pinned);
  const rest = jobs.filter((job) => !job.pinned);
  return [...pinned, ...rest];
}

function jobMatchesPinTarget(job, url, idempotencyKey, data) {
  const key = (data.idempotency_key || idempotencyKey || "").trim();
  const jobKey = (job?.idempotency_key || "").trim();
  if (key && jobKey && key === jobKey) return true;
  const probe = { jobs: [job] };
  if (findJobInCompany(probe, url, idempotencyKey) === job) return true;
  if (data.url && findJobInCompany(probe, data.url, key) === job) return true;
  return false;
}

function pinJobToTopOfCompany(company, url, idempotencyKey = "") {
  const found = findJobBucket(company, url, idempotencyKey);
  if (!found) return;
  const idx = found.list.indexOf(found.job);
  if (idx <= 0) return;
  found.list.splice(idx, 1);
  found.list.unshift(found.job);
}

/** Apply persisted pin state to the in-memory board catalog. */
export function applyPinToCatalog(country, companyName, url, idempotencyKey, data) {
  const scopeCountry = (data.country || country || "").trim();
  const targetCompany = data.company || companyName;
  const pinned = Boolean(data.pinned);

  const company = state.boardCatalog.find(
    (row) => row.country === scopeCountry && row.name === targetCompany,
  );
  if (!company) return false;

  for (const bucket of JOB_BUCKETS) {
    const list = company[bucket];
    if (!Array.isArray(list)) continue;
    for (const job of list) {
      const isPinnedJob = pinned && jobMatchesPinTarget(job, url, idempotencyKey, data);
      job.pinned = isPinnedJob;
      job.pinned_at = isPinnedJob ? (data.pinned_at || "") : "";
    }
    company[bucket] = sortPinnedJobsFirst(list);
  }
  if (pinned) {
    pinJobToTopOfCompany(company, url, idempotencyKey);
  }

  state.allCompanies = state.boardCatalog;
  applyBoardView();
  return true;
}

export function finalizeCompanyBoard(company) {
  recomputeCounts(company);
  evictCompanyIfHidden(company);
  applyBoardView();
}

export function syncAppliedVisibility(company) {
  finalizeCompanyBoard(company);
}

export function moveJobBetweenBuckets(company, url, idempotencyKey, targetKey, patch = {}) {
  const found = findJobBucket(company, url, idempotencyKey);
  if (!found) return;
  removeFromList(found.list, url, idempotencyKey);
  const next = { ...found.job, ...patch };
  ensureList(company, targetKey).push(next);
  finalizeCompanyBoard(company);
}

export function hideJobAsNotForMe(company, url, idempotencyKey, reason) {
  const found = findJobBucket(company, url, idempotencyKey);
  if (!found) return;
  removeFromList(found.list, url, idempotencyKey);
  const next = {
    ...found.job,
    not_for_me: true,
    not_for_me_reason: reason || "not_for_me",
    not_for_me_date: new Date().toISOString().slice(0, 10),
  };
  ensureList(company, "not_for_me_jobs").push(next);
  finalizeCompanyBoard(company);
}

export function restoreJobToOpen(company, url, idempotencyKey) {
  const hidden = company.not_for_me_jobs || company.hidden_jobs || [];
  const job = removeFromList(hidden, url, idempotencyKey);
  if (!job) return;
  const next = {
    ...job,
    not_for_me: false,
    not_for_me_reason: "",
    not_for_me_date: "",
  };
  ensureList(company, "jobs").push(next);
  finalizeCompanyBoard(company);
}

export function syncLookingToApplyVisibility(company) {
  finalizeCompanyBoard(company);
}

export function reapplyJobLocally(company, url, idempotencyKey, patch = {}) {
  const rejected = ensureList(company, "rejected_jobs");
  const job = removeFromList(rejected, url, idempotencyKey)
    || removeFromList(ensureList(company, "jobs"), url, idempotencyKey);
  if (!job) return;
  const next = {
    ...job,
    ...patch,
    rejected: false,
    rejected_date: "",
    applied: false,
    applied_date: "",
  };
  ensureList(company, "jobs").push(next);
  finalizeCompanyBoard(company);
}

export function patchJobOnBoard(country, companyName, url, idempotencyKey, data) {
  const company = findCompany(country, companyName);
  if (!company) return false;
  const key = data.idempotency_key || idempotencyKey || "";

  if (data.rejected === true) {
    const found = findJobBucket(company, url, key);
    if (!found) return false;
    removeFromList(found.list, url, key);
    ensureList(company, "rejected_jobs").push(mergeJobPatch(found.job, data));
    syncCompanyHeaderFromJobs(company, data);
    finalizeCompanyBoard(company);
    return true;
  }

  if (data.rejected === false) {
    const found = findJobBucket(company, url, key);
    if (!found) return false;
    removeFromList(found.list, url, key);
    ensureList(company, "jobs").push(mergeJobPatch({
      ...found.job,
      rejected: false,
      rejected_date: "",
    }, data));
    syncCompanyHeaderFromJobs(company, data);
    finalizeCompanyBoard(company);
    return true;
  }

  const found = findJobBucket(company, url, key);
  if (!found) return false;
  const idx = found.list.indexOf(found.job);
  if (idx < 0) return false;
  found.list[idx] = mergeJobPatch(found.job, data);
  syncCompanyHeaderFromJobs(company, data);
  finalizeCompanyBoard(company);
  return true;
}
