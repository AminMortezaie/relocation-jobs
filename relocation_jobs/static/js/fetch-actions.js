/** Fetch UI actions wired from React components. */

import { state } from "./state.js";
import { toast } from "./utils.js";
import { markFetchOk, toggleFetchProblem, addManualJobs } from "./api.js";
import { loadJobs } from "./data.js";
import {
  cancelFetch,
  ensureFetchPolling,
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

export function registerFetchActions() {
  window.relocationJobs = window.relocationJobs || {};
  window.relocationJobs.fetchActions = {
    startFetch: () => runFetchAction(() => handleFetchCountryClick()),
    openProgress: () => runFetchAction(() => openFetchProgress()),
    cancelFetch: () => runFetchAction(() => cancelFetch()),
    fetchCompany: (country, company) => runFetchAction(() => fetchOneCompany(country, company)),
    closePanel: () => {
      hideFetchPanel();
      ensureFetchPolling();
    },
    toggleReviewExpand: () => toggleFetchReviewFilteredExpanded(),
    async submitReviewFeedback(country, company, action) {
      if (!country || !company) return;
      try {
        const result = action === "ok"
          ? await markFetchOk(country, company)
          : await toggleFetchProblem(country, company, true);
        if (!result) return;
        state.fetchReviewFeedback = { country, company, status: action === "ok" ? "ok" : "problem" };
        setFetchReviewFeedbackDone(state.fetchReviewFeedback.status);
        toast(action === "ok" ? `Fetch OK — ${company}` : `Fetch problem — ${company}`);
        await loadJobs({ overlayLabel: "Updating board…" });
        if (
          state.fetchReviewFeedback?.country === country
          && state.fetchReviewFeedback?.company === company
        ) {
          setFetchReviewFeedbackDone(state.fetchReviewFeedback.status);
        }
      } catch (err) {
        if (err?.message !== "auth") {
          toast(err?.message || "Could not save fetch status");
        }
        throw err;
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
      await loadJobs();
      hideFetchPanel();
    },
  };
}

registerFetchActions();
