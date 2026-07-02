/** HTTP client and backend API calls. */

import { findCompany, state, onUnauthorized } from "./state.js";
import {
  hideJobAsNotForMe,
  patchJobOnBoard,
  applyPinToCatalog,
  reapplyJobLocally,
  restoreJobToOpen,
  refreshJobBoard,
} from "./job-board.js";
import { toast, browserTimezone } from "./utils.js";

async function reloadBoardFallback() {
  const { loadBoard } = await import("./board.js");
  await loadBoard({ force: true, refreshUserStats: true, noOverlay: true });
}

async function refreshUserStatsQuiet() {
  const { refreshBoardUserStats } = await import("./board.js");
  await refreshBoardUserStats();
}

function applyJobMutation(country, company, url, idempotencyKey, data, { pin = true } = {}) {
  const key = data.idempotency_key || idempotencyKey || "";
  if (patchJobOnBoard(country, company, url, key, data)) {
    if (pin) void pinJob(country, company, url, key);
    void refreshUserStatsQuiet();
    return true;
  }
  void reloadBoardFallback();
  return false;
}

export async function pinJob(country, company, url, idempotencyKey = "", pinned = true) {
  const res = await apiFetch("/api/jobs/pin", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      country,
      company,
      url,
      pinned,
      ...(idempotencyKey ? { idempotency_key: idempotencyKey } : {}),
    }),
  });
  const data = await parseJsonResponse(res);
  if (!res.ok) {
    toast(data.error || (pinned ? "Could not pin role" : "Could not unpin role"));
    return false;
  }
  applyPinToCatalog(country, company, url, idempotencyKey, data);
  return true;
}

export async function apiFetch(url, options = {}) {
  const res = await fetch(url, {
    credentials: "same-origin",
    ...options,
    headers: {
      ...(options.headers || {}),
    },
  });
  if (res.status === 401 && !url.startsWith("/api/auth/")) {
    onUnauthorized();
    throw new Error("auth");
  }
  return res;
}

async function parseJsonResponse(res) {
  const ct = res.headers.get("content-type") || "";
  if (!ct.includes("application/json")) return {};
  return res.json().catch(() => ({}));
}

function apiNotFoundHint(routeName) {
  return `${routeName} API not found — restart the panel: python3 panel_server.py`;
}

export async function removeCompany(country, company) {
  const res = await apiFetch("/api/companies/remove", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ country, company }),
  });
  const data = await parseJsonResponse(res);
  if (!res.ok) {
    const msg = res.status === 404 && !data.error
      ? apiNotFoundHint("Remove-company")
      : (data.error || "Could not remove company");
    toast(msg);
    return false;
  }
  return data;
}

export async function updateCareersUrl(country, company, careers_url, redetect_ats) {
  const res = await apiFetch("/api/companies/careers", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ country, company, careers_url, redetect_ats }),
  });
  const data = await parseJsonResponse(res);
  if (!res.ok) {
    const msg = res.status === 404 && !data.error
      ? apiNotFoundHint("Edit-careers")
      : (data.error || "Could not save careers URL");
    toast(msg);
    return null;
  }
  return data;
}

export async function updateCompanyName(country, company, new_name) {
  const res = await apiFetch("/api/companies/name", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ country, company, new_name }),
  });
  const data = await parseJsonResponse(res);
  if (!res.ok) {
    const msg = res.status === 404 && !data.error
      ? apiNotFoundHint("Rename-company")
      : (data.error || "Could not rename company");
    toast(msg);
    return null;
  }
  return data;
}

export async function updateCompanyCity(country, company, locations) {
  const payload = Array.isArray(locations)
    ? { locations: locations.map((loc) => ({
        country: loc.country,
        city: loc.city,
      })) }
    : { locations: [] };
  const res = await apiFetch("/api/companies/city", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      country,
      company,
      ...payload,
    }),
  });
  const data = await parseJsonResponse(res);
  if (!res.ok) {
    const msg = res.status === 404 && !data.error
      ? apiNotFoundHint("Edit-city")
      : (data.error || "Could not save locations");
    toast(msg);
    return null;
  }
  return data;
}

export async function markFetchOk(country, company) {
  const res = await apiFetch("/api/companies/fetch-ok", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ country, company }),
  });
  const data = await parseJsonResponse(res);
  if (!res.ok) {
    const msg = res.status === 404 && !data.error
      ? apiNotFoundHint("Fetch-OK")
      : (data.error || "Could not mark Fetch OK");
    toast(msg);
    return null;
  }
  return data;
}

export async function toggleFetchProblem(country, company, fetch_problem, { markFetchOk = false } = {}) {
  const res = await apiFetch("/api/companies/fetch-problem", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      country,
      company,
      fetch_problem,
      mark_fetch_ok: markFetchOk,
    }),
  });
  const data = await parseJsonResponse(res);
  if (!res.ok) {
    const msg = res.status === 404 && !data.error
      ? apiNotFoundHint("Fetch-problem")
      : (data.error || "Could not update tag");
    toast(msg);
    return null;
  }
  return data;
}

export async function setNotForMe(country, company, url, notForMe, reason = null) {
  const body = { country, company, url, not_for_me: notForMe };
  if (notForMe && reason) body.reason = reason;
  const res = await apiFetch("/api/jobs/not-for-me", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await parseJsonResponse(res);
  if (!res.ok) {
    const msg = res.status === 404 && !data.error
      ? apiNotFoundHint("Not for me")
      : (data.error || (notForMe ? "Could not hide role" : "Could not restore role"));
    toast(msg);
    return false;
  }
  const co = findCompany(country, company);
  const idempotencyKey = data.idempotency_key || "";
  if (co) {
    if (notForMe) {
      hideJobAsNotForMe(co, url, idempotencyKey, reason);
    } else {
      restoreJobToOpen(co, url, idempotencyKey);
    }
    void refreshUserStatsQuiet();
  } else {
    await reloadBoardFallback();
  }
  return true;
}

export async function markNotForMe(country, company, url) {
  return setNotForMe(country, company, url, true, "not_for_me");
}

export async function markNoRelocation(country, company, url) {
  return setNotForMe(country, company, url, true, "no_relocation");
}

export async function markWrongLocation(country, company, url) {
  return setNotForMe(country, company, url, true, "wrong_location");
}

export async function restoreJob(country, company, url) {
  return setNotForMe(country, company, url, false);
}

export async function toggleCompanyApplied(country, company, applied) {
  const res = await apiFetch("/api/companies/applied", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ country, company, applied }),
  });
  const data = await res.json();
  if (!res.ok) {
    toast(data.error || "Could not save");
    return null;
  }
  return data;
}

export async function toggleCompanyAwaitingResponse(country, company, awaiting) {
  const res = await apiFetch("/api/companies/awaiting-response", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ country, company, awaiting_response: awaiting }),
  });
  const data = await parseJsonResponse(res);
  if (!res.ok) {
    toast(data.error || "Could not save company status");
    return null;
  }
  const co = findCompany(country, company);
  if (co) {
    co.awaiting_response = data.awaiting_response;
    co.awaiting_response_date = data.awaiting_response_date || "";
    refreshJobBoard();
  }
  return data;
}

export async function toggleApplied(country, company, url, applied, idempotencyKey = "") {
  const res = await apiFetch("/api/jobs/applied", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      country,
      company,
      url,
      applied,
      ...(idempotencyKey ? { idempotency_key: idempotencyKey } : {}),
    }),
  });
  const data = await res.json();
  if (!res.ok) {
    toast(data.error || "Could not save");
    return null;
  }
  applyJobMutation(country, company, url, idempotencyKey, data);
  return data;
}

export async function saveAtsScore(country, company, url, atsScore) {
  const res = await apiFetch("/api/jobs/ats-score", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      country,
      company,
      url,
      ats_score: atsScore,
    }),
  });
  const data = await parseJsonResponse(res);
  if (!res.ok) {
    const msg = res.status === 404 && !data.error
      ? apiNotFoundHint("ATS score")
      : (data.error || "Could not save ATS score");
    toast(msg);
    return null;
  }
  applyJobMutation(country, company, url, "", data);
  return data;
}

export async function saveWaitingReferral(country, company, url, waitingReferral, linkedinUrl = "") {
  const res = await apiFetch("/api/jobs/waiting-referral", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      country,
      company,
      url,
      waiting_referral: waitingReferral,
      linkedin_url: linkedinUrl,
    }),
  });
  const data = await parseJsonResponse(res);
  if (!res.ok) {
    toast(data.error || "Could not save waiting referral");
    return null;
  }
  applyJobMutation(country, company, url, "", data);
  toast(waitingReferral ? "Waiting for referral" : "Referral status cleared");
  return data;
}

export async function reapplyJob(country, company, url) {
  const res = await apiFetch("/api/jobs/reapply", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ country, company, url }),
  });
  const data = await parseJsonResponse(res);
  if (!res.ok) {
    const msg = res.status === 404 && !data.error
      ? apiNotFoundHint("Reapply")
      : (data.error || "Could not reapply");
    toast(msg);
    return null;
  }
  const co = findCompany(country, company);
  if (co) {
    reapplyJobLocally(co, url, data.idempotency_key || "", data);
    void pinJob(country, company, url, data.idempotency_key || "");
    void refreshUserStatsQuiet();
  } else {
    await reloadBoardFallback();
  }
  return data;
}

export async function toggleRejected(country, company, url, rejected, idempotencyKey = "") {
  const res = await apiFetch("/api/jobs/rejected", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      country,
      company,
      url,
      rejected,
      ...(idempotencyKey ? { idempotency_key: idempotencyKey } : {}),
    }),
  });
  const data = await parseJsonResponse(res);
  if (!res.ok) {
    const msg = res.status === 404 && !data.error
      ? apiNotFoundHint("Rejection")
      : (data.error || "Could not save rejection");
    toast(msg);
    return null;
  }
  applyJobMutation(country, company, url, idempotencyKey, data);
  return data;
}

export async function toggleLookingToApply(country, company, url, lookingToApply, idempotencyKey = "") {
  const res = await apiFetch("/api/jobs/looking-to-apply", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      country,
      company,
      url,
      looking_to_apply: lookingToApply,
      ...(idempotencyKey ? { idempotency_key: idempotencyKey } : {}),
    }),
  });
  const data = await parseJsonResponse(res);
  if (!res.ok) {
    toast(data.error || "Could not save");
    return null;
  }
  applyJobMutation(country, company, url, idempotencyKey, data);
  return data;
}

export async function toggleSeen(country, company, url, seen, idempotencyKey = "", { pin = true } = {}) {
  const res = await apiFetch("/api/jobs/seen", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      country,
      company,
      url,
      seen,
      ...(idempotencyKey ? { idempotency_key: idempotencyKey } : {}),
    }),
  });
  const data = await parseJsonResponse(res);
  if (!res.ok) {
    toast(data.error || "Could not update saw-before tag");
    return null;
  }
  applyJobMutation(country, company, url, idempotencyKey, data, { pin });
  return data;
}

export async function markJobSeen(country, company, url, idempotencyKey = "") {
  return toggleSeen(country, company, url, true, idempotencyKey, { pin: false });
}

export async function addCompany(payload) {
  const res = await apiFetch("/api/companies", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok) {
    const msg = res.status === 404
      ? apiNotFoundHint("Add-company")
      : (data.error || "Could not add company");
    toast(msg);
    return null;
  }
  return data;
}

export async function startFetchRequest(payload) {
  const res = await apiFetch("/api/fetch", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok) {
    toast(data.error || "Fetch failed");
    return null;
  }
  return data;
}

export async function fetchCompanyRequest(country, company) {
  const res = await apiFetch("/api/companies/fetch", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ country, company }),
  });
  const data = await parseJsonResponse(res);
  if (!res.ok) {
    const msg = res.status === 404
      ? apiNotFoundHint("Fetch")
      : (data.error || "Fetch failed");
    toast(msg);
    return null;
  }
  return data;
}

export async function getFetchStatus() {
  const res = await apiFetch("/api/fetch/status");
  if (!res.ok) {
    throw new Error(`Fetch status failed (${res.status})`);
  }
  return res.json();
}

export async function addManualJobs(country, company, jobs) {
  const res = await apiFetch("/api/companies/jobs/manual-add", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ country, company, jobs }),
  });
  const data = await parseJsonResponse(res);
  if (!res.ok) {
    toast(data.error || "Could not add jobs");
    return null;
  }
  return data;
}

export async function cancelFetchRequest() {
  const res = await apiFetch("/api/fetch/cancel", { method: "POST" });
  const data = await parseJsonResponse(res);
  if (!res.ok) {
    const msg = res.status === 404
      ? "Cancel API not found — restart the panel server"
      : (data.error || "Could not cancel fetch");
    toast(msg);
    return false;
  }
  return true;
}

function filterQueryFlag(id) {
  const el = document.getElementById(id);
  return el && el.checked ? "1" : "0";
}

export function catalogQueryParams() {
  const country = document.getElementById("country").value;
  const atsEl = document.getElementById("ats");
  const atsType = atsEl && atsEl.value !== "all" ? atsEl.value : "";
  const locationEl = document.getElementById("location");
  const location = locationEl && locationEl.value !== "all" ? locationEl.value : "";
  const params = new URLSearchParams({ country });
  if (location) params.set("location", location);
  if (atsType) params.set("ats_type", atsType);
  return params.toString();
}

export function boardQueryParams({ page = 1, pageSize = 25 } = {}) {
  const params = new URLSearchParams(catalogQueryParams());
  params.set("timezone", browserTimezone());
  params.set("page", String(page));
  params.set("page_size", String(pageSize));
  params.set("visa_only", filterQueryFlag("visaOnly"));
  params.set("hide_applied", filterQueryFlag("hideApplied"));
  params.set("hide_empty", filterQueryFlag("hideEmpty"));
  params.set("not_applied_only", filterQueryFlag("notAppliedOnly"));
  params.set("hide_position_applied", filterQueryFlag("hidePositionApplied"));
  params.set("hide_position_rejected", filterQueryFlag("hidePositionRejected"));
  params.set("position_applied_only", filterQueryFlag("positionAppliedOnly"));
  params.set("position_rejected_only", filterQueryFlag("positionRejectedOnly"));
  params.set("position_looking_to_apply_only", filterQueryFlag("positionLookingToApplyOnly"));
  params.set("fetch_ok_only", filterQueryFlag("fetchOkOnly"));
  params.set("fetch_problem_only", filterQueryFlag("fetchProblemOnly"));
  const q = document.getElementById("search")?.value.trim();
  if (q) params.set("q", q);
  const sort = document.getElementById("sortSelect")?.value === "name" ? "name" : "newest";
  params.set("sort", sort);
  return params;
}

export async function fetchBoard(options = {}) {
  const params = boardQueryParams({
    page: options.page ?? 1,
    pageSize: options.pageSize ?? 25,
  });
  const bust = options.bustCache ? `&_=${Date.now()}` : "";
  const res = await apiFetch(`/api/board?${params.toString()}${bust}`, {
    cache: "no-store",
  });
  const data = await parseJsonResponse(res);
  if (!res.ok) {
    const msg = data.error || "Could not load board";
    toast(msg);
    throw new Error(msg);
  }
  return data;
}

export async function fetchBoardUserStats() {
  const params = new URLSearchParams(catalogQueryParams());
  params.set("timezone", browserTimezone());
  const latest = state.boardMeta?.latest_fetch_new_jobs;
  if (latest != null) {
    params.set("latest_fetch_new_jobs", String(latest));
  }
  const res = await apiFetch(`/api/board/stats?${params.toString()}`, {
    cache: "no-store",
  });
  const data = await parseJsonResponse(res);
  if (!res.ok) {
    const msg = data.error || "Could not load board stats";
    toast(msg);
    throw new Error(msg);
  }
  return data;
}

export function jobsQueryParams() {
  const country = document.getElementById("country").value;
  const atsEl = document.getElementById("ats");
  const atsType = atsEl && atsEl.value !== "all" ? atsEl.value : "";
  const locationEl = document.getElementById("location");
  const location = locationEl && locationEl.value !== "all" ? locationEl.value : "";
  const params = new URLSearchParams({
    country,
    timezone: browserTimezone(),
    visa_only: filterQueryFlag("visaOnly"),
    hide_applied: filterQueryFlag("hideApplied"),
    hide_empty: filterQueryFlag("hideEmpty"),
    not_applied_only: filterQueryFlag("notAppliedOnly"),
    hide_position_applied: filterQueryFlag("hidePositionApplied"),
    position_applied_only: filterQueryFlag("positionAppliedOnly"),
    position_rejected_only: filterQueryFlag("positionRejectedOnly"),
    position_looking_to_apply_only: filterQueryFlag("positionLookingToApplyOnly"),
    fetch_ok_only: filterQueryFlag("fetchOkOnly"),
    fetch_problem_only: filterQueryFlag("fetchProblemOnly"),
  });
  if (location) params.set("location", location);
  if (atsType) params.set("ats_type", atsType);
  return params.toString();
}

export async function fetchJobs(options = {}) {
  const bust = options.bustCache ? `&_=${Date.now()}` : "";
  const res = await apiFetch(`/api/jobs?${jobsQueryParams()}${bust}`, {
    cache: "no-store",
  });
  const data = await parseJsonResponse(res);
  if (!res.ok) {
    const msg = data.error || "Could not load jobs";
    toast(msg);
    throw new Error(msg);
  }
  return data;
}

export async function fetchConfig() {
  const res = await apiFetch("/api/config");
  return res.json();
}

export async function fetchCountries() {
  const res = await apiFetch("/api/countries");
  return res.json();
}

export async function fetchCities(country = "all") {
  const data = await fetchLocations(country);
  return data.map((loc) => loc.city);
}

export async function fetchLocations(country = "all", { picker = false } = {}) {
  const params = new URLSearchParams({ country });
  if (picker) params.set("picker", "1");
  const res = await apiFetch(`/api/locations?${params}`);
  const data = await parseJsonResponse(res);
  if (!res.ok) {
    toast(data.error || "Could not load locations");
    return [];
  }
  return data.locations || [];
}

export async function addCustomLocation(country, city) {
  const res = await apiFetch("/api/locations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ country, city }),
  });
  const data = await parseJsonResponse(res);
  if (!res.ok) {
    toast(data.error || "Could not add city");
    return null;
  }
  return data.location || null;
}

export async function fetchAtsTypes() {
  const res = await apiFetch("/api/ats-types");
  const data = await parseJsonResponse(res);
  if (!res.ok) {
    toast(data.error || "Could not load ATS list");
    return [];
  }
  return data.ats_types || [];
}
