/** Job scrape / fetch orchestration. */

import { state } from "./state.js";
import { $, toast } from "./utils.js";
import {
  cancelFetchRequest,
  fetchCompanyRequest,
  getFetchStatus,
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
} from "./render.js";

function countryLabel(countryId) {
  const opt = [...$("country").options].find((o) => o.value === countryId);
  return opt?.textContent?.trim() || countryId || "";
}

function applyFetchStatus(st) {
  appendFetchLog((st.log || []).join("\n") || "(waiting…)");
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
      $("fetchTitle").textContent = "Fetching companies";
      const n = st.concurrency || state.scrapeConfig?.default_concurrency || 16;
      $("fetchSubtitle").textContent = `${countryLabel(st.country)} · ${n} parallel workers`;
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
  return { done: true, st };
}

export function pollFetchStatus() {
  if (state.pollTimer) clearInterval(state.pollTimer);

  async function tick() {
    const st = await getFetchStatus();
    const result = applyFetchStatus(st);
    if (!result.done) return;

    clearInterval(state.pollTimer);
    state.pollTimer = null;
    const fetchingKey = state.fetchingCompanyKey;
    const optimisticTs = fetchingKey
      ? state.allCompanies.find((c) => `${c.country}:${c.name}` === fetchingKey)?.updated
      : null;
    await loadJobs();
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
  if (!state.fetchBusy) return;
  $("fetchCancelBtn").disabled = true;
  $("fetchCancelBtn").textContent = "Cancelling…";
  const ok = await cancelFetchRequest();
  if (!ok) {
    $("fetchCancelBtn").disabled = false;
    $("fetchCancelBtn").textContent = "Cancel";
  }
}

export async function fetchOneCompany(country, company) {
  if (state.fetchBusy) {
    toast("A fetch is already running.");
    return;
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
    await loadJobs();
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
  const st = await getFetchStatus();
  if (!st.running || !st.company) return;
  setFetchBusy(true, `${st.country}:${st.company}`);
  showFetchPanel({
    title: `Fetching ${st.company}`,
    subtitle: countryLabel(st.country),
    singleCompany: true,
    country: st.country,
    company: st.company,
  });
  pollFetchStatus();
}
