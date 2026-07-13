/** Job scrape / fetch orchestration. */

import {
  state,
  beginCompanySession,
  bindSessionRun,
  completeSession,
  endSession,
  isSessionActive,
  isSessionRunning,
} from "./state.js";
import { $, toast } from "./utils.js";
import {
  cancelFetchRequest,
  fetchCompanyRequest,
  getFetchStatus,
  startFetchRequest,
} from "./api.js";
import { loadJobs } from "./data.js";
import { syncBoardView } from "./board-view.js";
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
  hideFetchCompletion,
  hideFetchPanel,
} from "./render.js";

const FETCH_POLL_FAILURE_LIMIT = 3;
const FETCH_POLL_MS = 800;

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

function statusRunId(st) {
  if (st?.run_id != null) return Number(st.run_id);
  if (st?.last_fetch_run?.id != null) return Number(st.last_fetch_run.id);
  return null;
}

function stopPollTimer() {
  if (state.pollTimer) {
    clearTimeout(state.pollTimer);
    state.pollTimer = null;
  }
  if (state.fetchVisibilityHandler) {
    document.removeEventListener("visibilitychange", state.fetchVisibilityHandler);
    state.fetchVisibilityHandler = null;
  }
  state.fetchPollInFlight = false;
}

export function clearFetchActivity({ toast: showToast = false, message, syncBoard = true } = {}) {
  stopPollTimer();
  state.fetchPollFailures = 0;
  setFetchBusy(false, null, { syncBoard });
  if (showToast) toast(message || "Fetch status cleared");
}

/** Quiet board refresh once the modal conversation ends (OK / problem / close). */
export async function endSessionAndSettle({ closePanel = false } = {}) {
  const dirty = state.fetchSession.boardDirty || state.fetchSession.phase === "complete";
  const wasActive = isSessionActive();

  if (closePanel) hideFetchPanel();

  if (wasActive) {
    state.fetchSession.phase = "settling";
  }

  stopPollTimer();
  setFetchBusy(false, null, { syncBoard: false });

  if (dirty) {
    await loadJobs({ force: true, preserveContent: true, noOverlay: true, enterAnimation: false });
  } else if (wasActive) {
    // Clear fetching highlight without a network round-trip.
    syncBoardView();
  }

  endSession();
  state.fetchSession.boardDirty = false;
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
      endSession();
    }
    return null;
  }

  // Reconcile flags only while a local session owns the modal.
  if (isSessionRunning()) {
    syncFetchJobSummary(st);
    if (st.running) {
      markFetchActiveFromStatus(st);
      ensureFetchPolling();
    }
    return st;
  }

  syncFetchJobSummary(st);

  const clientThinksActive = state.countryFetchActive || state.fetchBusy || state.serverFetchRunning;
  if (st.running) {
    markFetchActiveFromStatus(st);
    ensureFetchPolling();
    return st;
  }
  if (clientThinksActive) {
    if (!st.running && state.fetchSession.phase === "idle") {
      // Sticky complete without an active session — safe to paint for reopen.
      applyFetchStatus(st, { replaceLog: true });
    }
    clearFetchActivity({
      toast: toastOnClear,
      message: "Fetch is no longer running",
    });
  }

  return st;
}

function singleCompanySummarySubtitle(st) {
  const review = st?.review_jobs || {};
  const matched = Array.isArray(review.included) ? review.included.length : 0;
  const filtered = Array.isArray(review.filtered) ? review.filtered.length : 0;
  const newJobs = Math.max(0, Number(st?.new_jobs_total) || 0);
  const run = st?.last_fetch_run;
  const durationSec = run?.duration_seconds
    ?? (st?.started_at && st?.finished_at
      ? Math.max(0, Math.round((Date.parse(st.finished_at) - Date.parse(st.started_at)) / 1000))
      : null);
  const parts = [
    `${matched} matched`,
    `${filtered} filtered`,
    `${newJobs} new`,
  ];
  if (durationSec != null && Number.isFinite(durationSec)) {
    parts.push(durationSec < 60 ? `${durationSec}s` : `${Math.round(durationSec / 60)}m`);
  }
  return parts.join(" · ");
}

function applyFetchStatus(st, { replaceLog = false } = {}) {
  const logText = (st.log || []).join("\n") || "(waiting…)";
  if (replaceLog) {
    appendFetchLog(`${logText}\n`);
  } else {
    appendFetchLog(logText);
  }
  updateFetchActivity(st);

  const progress = st.progress || {};
  const current = progress.current || 0;
  const total = progress.total || (st.company ? 1 : 0);
  const company = progress.company || st.company || null;
  const progressStatus = progress.status || "";
  const singleFetch = Boolean(st.company);

  if (st.running) {
    // Running: progress only — never paint review / LAST RUN for single-company.
    if (singleFetch) {
      clearFetchReviewContent();
      hideFetchCompletion();
      setFetchReviewFooterPending({
        country: st.country,
        company: st.company,
        prompt: "Fetch in progress…",
      });
      state.fetchPanelSingle = true;
      const activityMsg = (st.activity?.message || "").trim();
      patchRunningFetchPanel({
        title: `Fetching ${st.company}`,
        subtitle: st.cancel_requested
          ? `${countryLabel(st.country)} · cancelling…`
          : (activityMsg || `${countryLabel(st.country)} · working…`),
        singleCompany: true,
        progressWrapHidden: true,
        activityHidden: false,
        logHidden: true,
        cancelRequested: st.cancel_requested,
      });
      setFetchLogMode(true);
    } else {
      clearFetchReview();
      updateFetchCountryResults(st);
      updateFetchRunMeta(st, { running: true });
      state.fetchPanelSingle = false;
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

  // Complete
  const cancelled = st.cancelled || st.exit_code === 130;
  const failed = !cancelled && st.exit_code != null && st.exit_code !== 0;

  if (!singleFetch) {
    updateFetchProgress({
      current: total > 0 ? total : current,
      total,
      company: null,
      running: false,
      cancelled,
      newJobsTotal: st.new_jobs_total,
    });
  }

  if (singleFetch && !cancelled && !failed) {
    finishFetchPanel({
      title: "Fetch complete",
      subtitle: singleCompanySummarySubtitle(st),
      cancelled: false,
      failed: false,
      singleCompany: true,
      fetchRun: null,
      fetchStatus: st,
      hideCompletionMeta: true,
    });
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
  } else if (singleFetch && failed) {
    finishFetchPanel({
      title: "Fetch finished with errors",
      subtitle: st.result_line || "Check the log for details.",
      cancelled: false,
      failed: true,
      singleCompany: true,
      fetchRun: null,
      fetchStatus: st,
      hideCompletionMeta: true,
    });
    clearFetchReview();
    showFetchReviewFeedback({
      country: st.country,
      company: st.company,
      failed: true,
    });
    state.lastFetchReview = null;
  } else if (singleFetch && cancelled) {
    finishFetchPanel({
      title: "Fetch cancelled",
      subtitle: "Completed companies were saved.",
      cancelled: true,
      failed: false,
      singleCompany: true,
      fetchRun: null,
      fetchStatus: st,
      hideCompletionMeta: true,
    });
    clearFetchReview();
    state.lastFetchReview = null;
  } else {
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
      singleCompany: false,
      fetchRun: st.last_fetch_run || null,
      fetchStatus: st,
    });
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

function statusBelongsToSession(st) {
  const session = state.fetchSession;
  if (session.phase === "idle") return true;
  const rid = statusRunId(st);
  if (session.runId == null) {
    // Starting: only accept running status for our company (or unbound country).
    if (!st.running) return false;
    if (session.kind === "company") {
      return st.company === session.company && st.country === session.country;
    }
    return !st.company;
  }
  if (rid == null) return false;
  return Number(rid) === Number(session.runId);
}

export function ensureFetchPolling() {
  if (!state.pollTimer && (state.serverFetchRunning || state.countryFetchActive || state.fetchBusy)) {
    pollFetchStatus();
  }
}

export async function openFetchProgress() {
  // Never apply sticky complete into an active starting/running session.
  if (isSessionRunning()) {
    ensureFetchPolling();
    return;
  }

  const cached = state.lastFetchStatus;
  const clientActive = fetchClientActive();

  if (cached?.running || clientActive) {
    if (cached?.running) {
      syncFetchJobSummary(cached);
      markFetchActiveFromStatus(cached);
      showFetchPanelForStatus(cached, { reopen: true });
      applyFetchStatus(cached, { replaceLog: true });
      ensureFetchPolling();
    }
  } else if (cached?.company && cached?.review_jobs && state.fetchSession.phase === "idle") {
    openFetchPanel();
    applyFetchStatus(cached, { replaceLog: true });
  }

  let st;
  try {
    st = await getFetchStatus();
    state.fetchPollFailures = 0;
  } catch {
    if (state.lastFetchStatus?.running) {
      st = state.lastFetchStatus;
    } else if (cached?.running || clientActive) {
      return;
    } else {
      toast("Could not load fetch status");
      return;
    }
  }

  if (isSessionRunning()) {
    ensureFetchPolling();
    return;
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
  endSession();
  await startCountryFetch();
}

export function pollFetchStatus(expectedRunId = null) {
  stopPollTimer();

  if (expectedRunId != null && state.fetchSession.runId == null) {
    bindSessionRun(expectedRunId);
  }

  async function tick() {
    if (state.fetchPollInFlight) return;
    if (state.pollTimer) {
      clearTimeout(state.pollTimer);
      state.pollTimer = null;
    }
    state.fetchPollInFlight = true;
    try {
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
          endSession();
          return;
        }
        scheduleNext();
        return;
      }

      const expected = expectedRunId ?? state.fetchSession.runId;
      if (expected != null) {
        const rid = statusRunId(st);
        if (st.running) {
          if (rid != null && rid !== Number(expected)) {
            scheduleNext();
            return;
          }
        } else if (rid == null || rid !== Number(expected)) {
          // Ignore sticky prior completion while waiting for our run.
          if (isSessionRunning()) {
            scheduleNext();
            return;
          }
        }
      }

      if (isSessionActive() && !statusBelongsToSession(st)) {
        scheduleNext();
        return;
      }

      if (!st.running && fetchClientActive()) {
        syncFetchJobSummary(st);
        const result = applyFetchStatus(st, { replaceLog: true });
        stopPollTimer();

        const single = Boolean((result.st || st).company);
        if (single && isSessionActive()) {
          completeSession();
          // Clear fetching highlight only — no network board reload until settle.
          setFetchBusy(false, null, { syncBoard: true });
        } else {
          clearFetchActivity({ syncBoard: false });
          await loadJobs({ force: true, preserveContent: true, noOverlay: true, enterAnimation: false });
        }

        const doneSt = result.st || st;
        const cancelled = doneSt.cancelled || doneSt.exit_code === 130;
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
        return;
      }

      const result = applyFetchStatus(st);
      if (!result.done) {
        scheduleNext();
        return;
      }

      stopPollTimer();
      const single = Boolean(result.st?.company);
      if (single && isSessionActive()) {
        completeSession();
        setFetchBusy(false, null, { syncBoard: true });
      } else {
        setFetchBusy(false, null, { syncBoard: false });
        await loadJobs({ force: true, preserveContent: true, noOverlay: true, enterAnimation: false });
      }

      const { st: doneSt } = result;
      const cancelled = doneSt.cancelled || doneSt.exit_code === 130;
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
    } finally {
      state.fetchPollInFlight = false;
    }
  }

  function scheduleNext() {
    stopPollTimerVisibilityOnly();
    state.pollTimer = setTimeout(() => {
      state.pollTimer = null;
      tick();
    }, FETCH_POLL_MS);
  }

  function stopPollTimerVisibilityOnly() {
    if (state.pollTimer) {
      clearTimeout(state.pollTimer);
      state.pollTimer = null;
    }
  }

  const onVisibility = () => {
    if (!document.hidden && (state.pollTimer || fetchClientActive() || isSessionRunning())) {
      tick();
    }
  };
  state.fetchVisibilityHandler = onVisibility;
  document.addEventListener("visibilitychange", onVisibility);

  tick();
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

  state.fetchSession.phase = "starting";
  state.fetchSession.runId = null;
  state.fetchSession.kind = "country";
  state.fetchSession.country = country;
  state.fetchSession.company = null;
  state.fetchSession.boardDirty = false;

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
        if (st.run_id != null) bindSessionRun(st.run_id);
        showFetchPanelForStatus(st, { reopen: true });
        applyFetchStatus(st, { replaceLog: true });
        ensureFetchPolling();
        return;
      }
      setFetchBusy(false);
      endSession();
      hideFetchPanelOnFailure();
      return;
    }
    if (data.run_id != null) bindSessionRun(data.run_id);
    else state.fetchSession.phase = "running";
    pollFetchStatus(data.run_id ?? null);
  } catch {
    toast("Network error");
    setFetchBusy(false);
    endSession();
    hideFetchPanelOnFailure();
  }
}

export async function fetchOneCompany(country, company) {
  if (state.lastFetchStatus?.running || isSessionRunning()) {
    toast("A fetch is already running.");
    return;
  }
  if (state.fetchBusy || state.countryFetchActive || state.serverFetchRunning) {
    clearFetchActivity();
  }

  beginCompanySession(country, company);
  setFetchBusy(true, `${country}:${company}`);
  state.lastFetchReview = null;
  state.lastFetchStatus = null;
  showFetchPanel({
    title: `Fetching ${company}`,
    subtitle: countryLabel(country),
    singleCompany: true,
    country,
    company,
  });

  try {
    const st = await getFetchStatus();
    if (st?.running) {
      toast("A fetch is already running.");
      setFetchBusy(false);
      endSession();
      hideFetchPanelOnFailure();
      return;
    }
  } catch {
    // Status check failed — proceed and let fetchCompanyRequest surface the real error.
  }

  try {
    const data = await fetchCompanyRequest(country, company);
    if (!data) {
      setFetchBusy(false);
      endSession();
      hideFetchPanelOnFailure();
      return;
    }
    if (data.run_id != null) bindSessionRun(data.run_id);
    else state.fetchSession.phase = "running";
    pollFetchStatus(data.run_id ?? null);
  } catch {
    toast("Network error");
    setFetchBusy(false);
    endSession();
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
    if (st?.company && st?.review_jobs && fetchClientActive() && !isSessionRunning()) {
      openFetchPanel();
      applyFetchStatus(st, { replaceLog: true });
    }
    clearFetchActivity();
    return;
  }

  markFetchActiveFromStatus(st);
  syncFetchJobSummary(st);
  if (st.run_id != null && state.fetchSession.phase === "idle") {
    state.fetchSession.phase = "running";
    state.fetchSession.runId = st.run_id;
    state.fetchSession.kind = st.company ? "company" : "country";
    state.fetchSession.country = st.country;
    state.fetchSession.company = st.company || null;
  }
  ensureFetchPolling();
}
