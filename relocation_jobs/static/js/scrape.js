/** Job scrape / fetch orchestration. */

import { state } from "./state.js";
import { $, toast } from "./utils.js";
import {
  cancelFetchRequest,
  fetchCompanyRequest,
  getFetchStatus,
  startFetchRequest,
} from "./api.js";
import { loadJobs } from "./data.js";
import {
  setFetchBusy,
  showFetchPanel,
  updateFetchProgress,
  finishFetchPanel,
  appendFetchLog,
  updateFetchActivity,
  updateFetchRunMeta,
  setFetchPanelRunning,
  renderFetchReview,
  clearFetchReview,
  clearFetchReviewContent,
  setFetchReviewFooterPending,
  setFetchLogMode,
  showFetchReviewFeedback,
  normalizeTsForSort,
  syncFetchJobSummary,
  openFetchPanel,
} from "./render.js";

const FETCH_POLL_FAILURE_LIMIT = 3;

function countryLabel(countryId) {
  const opt = [...$("country").options].find((o) => o.value === countryId);
  return opt?.textContent?.trim() || countryId || "";
}

function atsLabel(atsId) {
  if (!atsId || atsId === "all") return "";
  const opt = [...($("ats")?.options || [])].find((o) => o.value === atsId);
  return opt?.textContent?.trim() || atsId;
}

function fetchScopeSubtitle(country, atsType, concurrency) {
  const parts = [countryLabel(country)];
  const ats = atsLabel(atsType);
  if (ats) parts.push(ats);
  if (concurrency) parts.push(`${concurrency} parallel workers`);
  return parts.join(" · ");
}

export function clearFetchActivity({ toast: showToast = false, message } = {}) {
  if (state.pollTimer) {
    clearInterval(state.pollTimer);
    state.pollTimer = null;
  }
  state.fetchPollFailures = 0;
  setFetchBusy(false);
  if (showToast) toast(message || "Fetch status cleared");
}

export async function syncFetchStateFromServer({ toastOnClear = false } = {}) {
  let st;
  try {
    st = await getFetchStatus();
    state.fetchPollFailures = 0;
  } catch {
    state.fetchPollFailures = (state.fetchPollFailures || 0) + 1;
    const clientThinksActive = state.countryFetchActive || state.fetchBusy || state.serverFetchRunning;
    if (clientThinksActive && state.fetchPollFailures >= FETCH_POLL_FAILURE_LIMIT) {
      clearFetchActivity({
        toast: toastOnClear,
        message: "Server unreachable — cleared stale fetch status",
      });
    }
    return null;
  }

  syncFetchJobSummary(st);

  const clientThinksActive = state.countryFetchActive || state.fetchBusy || state.serverFetchRunning;
  if (st.running) {
    markFetchActiveFromStatus(st);
    ensureFetchPolling();
    return st;
  }
  if (clientThinksActive) {
    clearFetchActivity({
      toast: toastOnClear,
      message: "Fetch is no longer running",
    });
  }

  return st;
}

function applyFetchStatus(st, { replaceLog = false } = {}) {
  const logText = (st.log || []).join("\n") || "(waiting…)";
  if (replaceLog) {
    $("fetchLog").textContent = `${logText}\n`;
  } else {
    appendFetchLog(logText);
  }
  updateFetchActivity(st);
  if (st.running) {
    updateFetchRunMeta(st, { running: true });
  }

  const progress = st.progress || {};
  const current = progress.current || 0;
  const total = progress.total || (st.company ? 1 : 0);
  const company = progress.company || st.company || null;
  const progressStatus = progress.status || "";

  if (st.running) {
    const singleFetch = Boolean(st.company);
    if (singleFetch) {
      clearFetchReviewContent();
      setFetchReviewFooterPending({
        country: st.country,
        company: st.company,
      });
    } else {
      clearFetchReview();
    }
    state.fetchPanelSingle = singleFetch;
    if (singleFetch) {
      $("fetchTitle").textContent = `Fetching ${st.company}`;
      const activityMsg = (st.activity?.message || "").trim();
      $("fetchSubtitle").textContent = st.cancel_requested
        ? `${countryLabel(st.country)} · cancelling…`
        : (activityMsg || `${countryLabel(st.country)} · working…`);
      $("fetchProgressWrap").hidden = true;
      $("fetchActivity").hidden = false;
      $("fetchLog").hidden = true;
      setFetchLogMode(true);
    } else {
      const n = st.concurrency || state.scrapeConfig?.default_concurrency || 16;
      $("fetchTitle").textContent = st.ats_type
        ? `Fetching ${atsLabel(st.ats_type)} companies`
        : "Fetching companies";
      $("fetchSubtitle").textContent = fetchScopeSubtitle(st.country, st.ats_type, n);
      $("fetchProgressWrap").hidden = false;
      $("fetchActivity").hidden = false;
      $("fetchLog").hidden = true;
      updateFetchProgress({
        current,
        total,
        company,
        status: progressStatus,
        running: true,
        cancelled: st.cancel_requested,
        newJobsTotal: st.new_jobs_total,
      });
    }
    if (st.cancel_requested) {
      $("fetchCancelBtn").disabled = true;
      $("fetchCancelBtn").textContent = "Cancelling…";
    }
    syncFetchJobSummary(st);
    return { done: false };
  }

  const cancelled = st.cancelled || st.exit_code === 130;
  const failed = !cancelled && st.exit_code != null && st.exit_code !== 0;
  const singleFetch = Boolean(st.company);
  if (!singleFetch) {
    updateFetchProgress({
      current: total > 0 ? total : current,
      total,
      company: null,
      running: false,
      cancelled,
      newJobsTotal: st.new_jobs_total,
    });
  } else {
    $("fetchLog").hidden = false;
  }

  const newJobsTotal = Math.max(0, Number(st.new_jobs_total) || 0);
  const newJobsNote = newJobsTotal > 0
    ? `${newJobsTotal} new role${newJobsTotal === 1 ? "" : "s"} from this fetch`
    : "";
  const resultSubtitle = st.result_line
    ? st.result_line.replace(/^\[\d+\/\d+\]\s*/, "").replace(/^Done\s+/, "")
    : "Jobs list updated";
  finishFetchPanel({
    title: cancelled ? "Fetch cancelled" : (failed ? "Fetch finished with errors" : "Fetch complete"),
    subtitle: cancelled
      ? (newJobsNote ? `${newJobsNote} · completed companies were saved.` : "Completed companies were saved.")
      : (newJobsNote || resultSubtitle),
    cancelled,
    failed,
    singleCompany: Boolean(st.company),
    fetchRun: st.last_fetch_run || null,
    fetchStatus: st,
  });

  if (!cancelled && st.company) {
    if (!failed) {
      renderFetchReview(st.review_jobs || { included: [], filtered: [] }, {
        country: st.country,
        company: st.company,
        missingReview: !st.review_jobs,
      });
      state.lastFetchReview = {
        review: st.review_jobs,
        country: st.country,
        company: st.company,
      };
    } else {
      clearFetchReview();
      showFetchReviewFeedback({
        country: st.country,
        company: st.company,
        failed: true,
      });
      state.lastFetchReview = null;
    }
  } else {
    clearFetchReview();
    state.lastFetchReview = null;
  }
  syncFetchJobSummary(st);
  return { done: true, st };
}

function showFetchPanelForStatus(st, { reopen = false } = {}) {
  if (st.company) {
    showFetchPanel({
      title: `Fetching ${st.company}`,
      subtitle: countryLabel(st.country),
      singleCompany: true,
      country: st.country,
      company: st.company,
      reopen,
    });
    return;
  }
  showFetchPanel({
    title: st.ats_type ? `Fetching ${atsLabel(st.ats_type)} companies` : "Fetching companies",
    subtitle: fetchScopeSubtitle(st.country, st.ats_type, st.concurrency),
    singleCompany: false,
    country: st.country,
    reopen,
  });
}

function markFetchActiveFromStatus(st) {
  if (st.company) {
    const key = `${st.country}:${st.company}`;
    if (!state.fetchBusy || state.fetchingCompanyKey !== key) {
      setFetchBusy(true, key);
    }
  } else if (!state.countryFetchActive) {
    setFetchBusy(true, null, { countryScope: true });
  }
  syncFetchJobSummary(st);
  state.fetchPanelSingle = Boolean(st.company);
}

export function ensureFetchPolling() {
  if (!state.pollTimer && (state.serverFetchRunning || state.countryFetchActive || state.fetchBusy)) {
    pollFetchStatus();
  }
}

export async function openFetchProgress() {
  let st;
  try {
    st = await getFetchStatus();
    state.fetchPollFailures = 0;
  } catch {
    if (state.lastFetchStatus?.running) {
      st = state.lastFetchStatus;
    } else {
      toast("Could not load fetch status");
      return;
    }
  }

  if (!st?.running) {
    if (state.countryFetchActive || state.fetchBusy || state.serverFetchRunning) {
      clearFetchActivity({ toast: true, message: "Fetch is no longer running" });
    }
    return;
  }

  syncFetchJobSummary(st);
  markFetchActiveFromStatus(st);
  showFetchPanelForStatus(st, { reopen: true });
  applyFetchStatus(st, { replaceLog: true });
  ensureFetchPolling();
}

export async function reopenFetchProgress() {
  await openFetchProgress();
}

export async function handleFetchCountryClick() {
  let st;
  try {
    st = await getFetchStatus();
    state.fetchPollFailures = 0;
  } catch {
    toast("Could not reach server");
    return;
  }

  if (st.running) {
    toast("A fetch is already running — use the progress chip to view it");
    syncFetchJobSummary(st);
    markFetchActiveFromStatus(st);
    ensureFetchPolling();
    return;
  }

  if (state.countryFetchActive || state.fetchBusy || state.serverFetchRunning) {
    clearFetchActivity();
  }
  await startCountryFetch();
}

export function pollFetchStatus() {
  if (state.pollTimer) clearInterval(state.pollTimer);

  async function tick() {
    let st;
    try {
      st = await getFetchStatus();
      state.fetchPollFailures = 0;
    } catch {
      state.fetchPollFailures = (state.fetchPollFailures || 0) + 1;
      if (state.fetchPollFailures >= FETCH_POLL_FAILURE_LIMIT) {
        clearFetchActivity({
          toast: true,
          message: "Lost connection to server — fetch status cleared",
        });
        return;
      }
      return;
    }

    if (!st.running && (state.countryFetchActive || state.fetchBusy || state.serverFetchRunning)) {
      syncFetchJobSummary(st);
      applyFetchStatus(st);
      clearFetchActivity();
      return;
    }

    const result = applyFetchStatus(st);
    if (!result.done) return;

    clearInterval(state.pollTimer);
    state.pollTimer = null;
    const fetchingKey = state.fetchingCompanyKey;
    const optimisticTs = fetchingKey
      ? state.allCompanies.find((c) => `${c.country}:${c.name}` === fetchingKey)?.updated
      : null;
    await loadJobs({ silent: true });
    if (fetchingKey && optimisticTs) {
      const company = state.allCompanies.find((c) => `${c.country}:${c.name}` === fetchingKey);
      if (company) {
        const serverTs = company.updated || company.newest_job_fetched || "";
        if (!serverTs || normalizeTsForSort(optimisticTs).localeCompare(normalizeTsForSort(serverTs)) > 0) {
          company.updated = optimisticTs;
          company.newest_job_fetched = optimisticTs;
        }
      }
    }
    setFetchBusy(false);

    if (state.lastFetchReview?.country && state.lastFetchReview?.company) {
      renderFetchReview(
        state.lastFetchReview.review || { included: [], filtered: [] },
        {
          country: state.lastFetchReview.country,
          company: state.lastFetchReview.company,
          missingReview: !state.lastFetchReview.review,
        }
      );
    }

    const { st: doneSt } = result;
    const cancelled = doneSt.cancelled || doneSt.exit_code === 130;
    const failed = !cancelled && doneSt.exit_code != null && doneSt.exit_code !== 0;
    const summary = doneSt.result_line
      ? doneSt.result_line.replace(/^\[\d+\/\d+\]\s*/, "")
      : (doneSt.company ? `${doneSt.company} updated` : "Jobs list updated");

    if (cancelled) {
      toast("Fetch cancelled — progress saved");
    } else if (doneSt.exit_code === 0) {
      toast(summary);
    } else {
      toast(doneSt.result_line || "Fetch failed — see log");
    }
  }

  tick();
  state.pollTimer = setInterval(tick, 800);
}

export async function cancelFetch() {
  let active = state.fetchBusy || state.countryFetchActive || state.serverFetchRunning;
  if (!active) {
    try {
      const st = await getFetchStatus();
      if (!st?.running) return;
      markFetchActiveFromStatus(st);
      active = true;
    } catch {
      return;
    }
  }
  if (!active) return;

  $("fetchCancelBtn").disabled = true;
  $("fetchCancelBtn").textContent = "Cancelling…";
  const ok = await cancelFetchRequest();
  if (!ok) {
    $("fetchCancelBtn").disabled = false;
    $("fetchCancelBtn").textContent = "Cancel";
    return;
  }
  ensureFetchPolling();
}

export async function startCountryFetch() {
  const country = $("country")?.value;
  const atsType = $("ats")?.value || "all";
  if (!country || country === "all") {
    toast("Select a single country to fetch (not All countries).");
    return;
  }
  if (state.scrapeConfig?.scrape_enabled === false) {
    toast("Scraping is disabled on this host.");
    return;
  }

  const concurrency = Math.max(
    1,
    Math.min(
      parseInt(localStorage.getItem("panel_concurrency"), 10)
        || state.scrapeConfig?.default_concurrency
        || 16,
      state.scrapeConfig?.max_concurrency || 64,
    ),
  );

  setFetchBusy(true, null, { countryScope: true });
  state.lastFetchReview = null;
  state.fetchPanelSingle = false;
  showFetchPanel({
    title: atsType !== "all" ? `Fetching ${atsLabel(atsType)} companies` : "Fetching companies",
    subtitle: fetchScopeSubtitle(country, atsType),
    singleCompany: false,
    country,
  });
  $("fetchSubtitle").textContent = fetchScopeSubtitle(country, atsType, concurrency);

  try {
    const data = await startFetchRequest({
      country,
      ats_type: atsType !== "all" ? atsType : undefined,
      concurrency,
    });
    if (!data) {
      const st = await getFetchStatus().catch(() => null);
      if (st?.running) {
        markFetchActiveFromStatus(st);
        showFetchPanelForStatus(st, { reopen: true });
        applyFetchStatus(st, { replaceLog: true });
        ensureFetchPolling();
        return;
      }
      setFetchBusy(false);
      hideFetchPanelOnFailure();
      return;
    }
    pollFetchStatus();
  } catch {
    toast("Network error");
    setFetchBusy(false);
    hideFetchPanelOnFailure();
  }
}

export async function fetchOneCompany(country, company) {
  const st = await syncFetchStateFromServer();
  if (st?.running) {
    toast("A fetch is already running.");
    return;
  }
  if (state.fetchBusy || state.countryFetchActive) {
    clearFetchActivity();
  }

  setFetchBusy(true, `${country}:${company}`);
  state.lastFetchReview = null;
  showFetchPanel({
    title: `Fetching ${company}`,
    subtitle: countryLabel(country),
    singleCompany: true,
    country,
    company,
  });

  try {
    const data = await fetchCompanyRequest(country, company);
    if (!data) {
      setFetchBusy(false);
      hideFetchPanelOnFailure();
      return;
    }
    await loadJobs({ silent: true });
    pollFetchStatus();
  } catch {
    toast("Network error");
    setFetchBusy(false);
    hideFetchPanelOnFailure();
  }
}

function hideFetchPanelOnFailure() {
  finishFetchPanel({ title: "Fetch failed", subtitle: "Could not start fetch.", failed: true });
  setFetchPanelRunning(false);
}

export async function resumeFetchIfRunning() {
  const st = await syncFetchStateFromServer();
  if (!st?.running) {
    clearFetchActivity();
    return;
  }

  markFetchActiveFromStatus(st);
  syncFetchJobSummary(st);
  ensureFetchPolling();
}
