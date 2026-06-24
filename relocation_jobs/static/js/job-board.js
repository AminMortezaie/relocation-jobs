/** Local job-board updates after tracking mutations (avoid full /api/jobs reload). */

import { applyBoardView } from "./board.js";
import { findJobInCompany } from "./state.js";

function jobMatches(job, url, idempotencyKey = "") {
  if (!job) return false;
  const probe = { jobs: [job] };
  return findJobInCompany(probe, url, idempotencyKey) === job;
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
}

export function refreshJobBoard() {
  applyBoardView();
}

export function finalizeCompanyBoard(company) {
  recomputeCounts(company);
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
