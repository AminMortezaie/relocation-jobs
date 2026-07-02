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
  syncFetchJobSummary,
  openFetchPanel,
  patchRunningFetchPanel,
  setFetchCancelPending,
  showFetchNotice,
  updateFetchCountryResults,
} from "./render.js";

const FETCH_POLL_FAILURE_LIMIT = 3;

function fetchClientActive() {
  return state.countryFetchActive || state.fetchBusy || state.serverFetchRunning;
}

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
  if (state.fetchVisibilityHandler) {
    document.removeEventListener("visibilitychange", state.fetchVisibilityHandler);
    state.fetchVisibilityHandler = null;
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
    if (!st.running) {
      applyFetchStatus(st, { replaceLog: true });
    }
    clearFetchActivity({
      toast: toastOnClear,
      message: "Fetch is no longer running",
    });
  }

  return st;
}

function showSingleCompanyReviewDuringFetch(st) {
  if (!st?.company || !st?.review_jobs) return false;
  renderFetchReview(st.review_jobs, {
    country: st.country,
    company: st.company,
    missingReview: false,
  });
  setFetchLogMode(false);
  return true;
}

function applyFetchStatus(st, { replaceLog = false } = {}) {
  const logText = (st.log || []).join("\n") || "(waiting…)";
  if (replaceLog) {
    appendFetchLog(`${logText}\n`);
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
      if (!showSingleCompanyReviewDuringFetch(st)) {
        clearFetchReviewContent();
        setFetchReviewFooterPending({
          country: st.country,
          company: st.company,
        });
      }
    } else {
      clearFetchReview();
      updateFetchCountryResults(st);
    }
    state.fetchPanelSingle = singleFetch;
    if (singleFetch) {
      const activityMsg = (st.activity?.message || "").trim();
      const reviewReady = Boolean(st.review_jobs);
      patchRunningFetchPanel({
        title: `Fetching ${st.company}`,
        subtitle: st.cancel_requested
          ? `${countryLabel(st.country)} · cancelling…`
          : (reviewReady
            ? `${countryLabel(st.country)} · saving roles…`
            : (activityMsg || `${countryLabel(st.country)} · working…`)),
        singleCompany: true,
        progressWrapHidden: true,
        activityHidden: reviewReady,
        logHidden: true,
        cancelRequested: st.cancel_requested,
      });
      if (!reviewReady) setFetchLogMode(true);
    } else {
      const n = st.concurrency || state.scrapeConfig?.default_concurrency || 16;
      patchRunningFetchPanel({
        title: st.ats_type ? `Fetching ${atsLabel(st.ats_type)} companies` : "Fetching companies",
        subtitle: fetchScopeSubtitle(st.country, st.ats_type, n),
        singleCompany: false,
        progressWrapHidden: false,
        activityHidden: false,
        logHidden: true,
        cancelRequested: st.cancel_requested,
      });
      updateFetchProgress({
        current,
        total,
        company,
        status: progressStatus,
        running: true,
        cancelled: st.cancel_requested,
        newJobsTotal: st.new_jobs_total,
      });
      updateFetchCountryResults(st);
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
  } else if (!st.review_jobs) {
    patchRunningFetchPanel({ logHidden: false });
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
    updateFetchCountryResults(st);
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
    if (fetchClientActive()) {
      applyFetchStatus(st, { replaceLog: true });
      clearFetchActivity({ toast: true, message: "Fetch is no longer running" });
      return;
    }
    if (st?.company && st?.review_jobs) {
      openFetchPanel();
      applyFetchStatus(st, { replaceLog: true });
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
    markFetchActiveFromStatus(st);
    syncFetchJobSummary(st);
    await openFetchProgress();
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
  if (state.fetchVisibilityHandler) {
    document.removeEventListener("visibilitychange", state.fetchVisibilityHandler);
    state.fetchVisibilityHandler = null;
  }

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

    if (!st.running && fetchClientActive()) {
      syncFetchJobSummary(st);
      applyFetchStatus(st, { replaceLog: true });
      clearFetchActivity();
      return;
    }

    const result = applyFetchStatus(st);
    if (!result.done) return;

    clearInterval(state.pollTimer);
    state.pollTimer = null;
    const fetchingKey = state.fetchingCompanyKey;
    await loadJobs({ force: true, overlayLabel: "Refreshing jobs…" });
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

  const onVisibility = () => {
    if (!document.hidden && state.pollTimer) tick();
  };
  state.fetchVisibilityHandler = onVisibility;
  document.addEventListener("visibilitychange", onVisibility);

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

  setFetchCancelPending(true);
  const ok = await cancelFetchRequest();
  if (!ok) {
    setFetchCancelPending(false);
    return;
  }
  ensureFetchPolling();
}

export async function startCountryFetch() {
  const country = $("country")?.value;
  const atsType = $("ats")?.value || "all";
  if (!country || country === "all") {
    toast("Select a single country to fetch (not All countries).");
    showFetchNotice({
      title: "Select a country",
      subtitle: "Choose one country from the dropdown above — All countries cannot be fetched at once.",
    });
    return;
  }
  if (state.scrapeConfig?.scrape_enabled === false) {
    toast("Scraping is disabled on this host.");
    showFetchNotice({
      title: "Scraping disabled",
      subtitle: "Scraping is disabled on this host. Run scrapes locally, then sync catalog to Postgres.",
    });
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
    subtitle: fetchScopeSubtitle(country, atsType, concurrency),
    singleCompany: false,
    country,
  });

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
    await loadJobs({ force: true, noOverlay: true });
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
    if (st?.company && st?.review_jobs && fetchClientActive()) {
      openFetchPanel();
      applyFetchStatus(st, { replaceLog: true });
    }
    clearFetchActivity();
    return;
  }

  markFetchActiveFromStatus(st);
  syncFetchJobSummary(st);
  ensureFetchPolling();
}
