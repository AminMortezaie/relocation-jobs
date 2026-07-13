/** Fetch UI actions wired from React components. */

import { findCompany, isSessionRunning, state } from "./state.js";
import { toast } from "./utils.js";
import { markFetchOk, toggleFetchProblem, addManualJobs } from "./api.js";
import {
  cancelFetch,
  ensureFetchPolling,
  endSessionAndSettle,
  handleFetchCountryClick,
  openFetchProgress,
  fetchOneCompany,
} from "./scrape.js";
import {
  hideFetchPanel,
  setFetchReviewFeedbackDone,
  toggleFetchReviewFilteredExpanded,
} from "./render.js";

async function runFetchAction(fn) {
  try {
    await fn();
  } catch (err) {
    console.error("Fetch action failed:", err);
    toast(err?.message || "Fetch failed");
  }
}

function applyFetchFeedbackOptimistic(country, company, action) {
  const co = findCompany(country, company);
  if (!co) return;
  if (action === "ok") {
    co.fetch_ok = true;
    co.fetch_ok_date = new Date().toISOString().replace(/\.\d{3}Z$/, "+00:00");
    co.fetch_problem = false;
    co.fetch_problem_date = "";
  } else {
    co.fetch_problem = true;
    co.fetch_problem_date = new Date().toISOString().replace(/\.\d{3}Z$/, "+00:00");
    co.fetch_ok = false;
    co.fetch_ok_date = "";
  }
}

function closeFetchPanelAction() {
  // Running: hide only — keep session + chip + polling (interruptibility ≠ abort).
  if (isSessionRunning() || state.serverFetchRunning || state.fetchBusy || state.countryFetchActive) {
    hideFetchPanel();
    ensureFetchPolling();
    return;
  }
  void endSessionAndSettle({ closePanel: true }).then(() => ensureFetchPolling());
}

export function registerFetchActions() {
  window.relocationJobs = window.relocationJobs || {};
  window.relocationJobs.fetchActions = {
    startFetch: () => runFetchAction(() => handleFetchCountryClick()),
    openProgress: () => runFetchAction(() => openFetchProgress()),
    cancelFetch: () => runFetchAction(() => cancelFetch()),
    fetchCompany: (country, company) => runFetchAction(() => fetchOneCompany(country, company)),
    closePanel: () => closeFetchPanelAction(),
    toggleReviewExpand: () => toggleFetchReviewFilteredExpanded(),
    async submitReviewFeedback(country, company, action) {
      if (!country || !company) return;
      // Instant press feedback — footer + optimistic badge before network.
      state.fetchReviewFeedback = { country, company, status: action === "ok" ? "ok" : "problem" };
      setFetchReviewFeedbackDone(state.fetchReviewFeedback.status);
      applyFetchFeedbackOptimistic(country, company, action);
      toast(action === "ok" ? `Fetch OK — ${company}` : `Fetch problem — ${company}`);

      try {
        const result = action === "ok"
          ? await markFetchOk(country, company)
          : await toggleFetchProblem(country, company, true);
        if (result) {
          const co = findCompany(country, company);
          if (co) {
            co.fetch_ok = Boolean(result.fetch_ok);
            co.fetch_ok_date = result.fetch_ok_date || "";
            co.fetch_problem = Boolean(result.fetch_problem);
            co.fetch_problem_date = result.fetch_problem_date || "";
          }
        }
      } catch (err) {
        if (err?.message !== "auth") {
          toast(err?.message || "Could not save fetch status");
        }
        throw err;
      } finally {
        await endSessionAndSettle({ closePanel: false });
      }
    },
    async addSelectedReviewJobs(country, company, selected) {
      if (!selected?.length) {
        toast("Select at least one role");
        return;
      }
      const result = await addManualJobs(country, company, selected);
      if (!result) return;
      toast(`Added ${result.added} role(s) to ${result.company}`);
      state.fetchSession.boardDirty = true;
      await endSessionAndSettle({ closePanel: true });
    },
  };
}

registerFetchActions();
