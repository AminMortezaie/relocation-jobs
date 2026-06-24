/** Fetch header + panel view model for React. */

import { state } from "./state.js";
import { $ } from "./utils.js";
import { publishFetchView } from "./fetch-sync.js";

export const fetchPanelState = {
  open: false,
  title: "Fetching companies",
  subtitle: "Starting…",
  singleCompany: false,
  cancelHidden: true,
  cancelDisabled: false,
  cancelText: "Cancel",
  cancelTitle: "Stop fetching remaining companies",
  closeHidden: false,
  progressWrapHidden: true,
  progress: {
    current: 0,
    total: 0,
    pct: 0,
    label: "0 / 0 companies",
    companyLine: "",
  },
  activity: {
    hidden: true,
    step: "Starting…",
    detail: "",
    items: [],
  },
  log: {
    hidden: true,
    text: "",
    active: false,
  },
  review: {
    visible: false,
    hint: "",
    included: [],
    filtered: [],
    filteredExpanded: false,
    country: "",
    company: "",
    missingReview: false,
    addBtnVisible: false,
    expandHidden: true,
    expandLabel: "",
  },
  completion: {
    hidden: true,
    label: "Current run",
    started: "—",
    finished: "—",
    duration: "—",
    newJobs: "—",
  },
  footer: {
    hidden: true,
    pending: false,
    resolved: false,
    resolvedStatus: null,
    prompt: "Did the fetch work correctly?",
    country: "",
    company: "",
    okDisabled: false,
    problemDisabled: false,
  },
};

function countryLabelFromId(countryId) {
  const opt = [...($("country")?.options || [])].find((o) => o.value === countryId);
  return opt?.textContent?.trim() || countryId || "";
}

function snapshotPanelState() {
  return {
    ...fetchPanelState,
    progress: { ...fetchPanelState.progress },
    activity: {
      ...fetchPanelState.activity,
      items: [...fetchPanelState.activity.items],
    },
    log: { ...fetchPanelState.log },
    review: {
      ...fetchPanelState.review,
      included: [...fetchPanelState.review.included],
      filtered: [...fetchPanelState.review.filtered],
    },
    completion: { ...fetchPanelState.completion },
    footer: { ...fetchPanelState.footer },
  };
}

function buildHeaderState() {
  const controlsEnabled = Boolean(state.fetchControlsEnabled);
  const active = state.serverFetchRunning || state.countryFetchActive || state.fetchBusy;
  const country = $("country")?.value || "all";
  const countryRequired = !country || country === "all";

  if (!controlsEnabled) {
    return { controlsEnabled: false, active: false, showButton: false, showChip: false };
  }

  if (!active) {
    return {
      controlsEnabled: true,
      active: false,
      showButton: true,
      showChip: false,
      countryRequired,
      buttonTitle: countryRequired
        ? "Select a single country first (not All countries)"
        : "Fetch jobs for the selected country and ATS filter",
    };
  }

  const summary = state.fetchJobSummary || {};
  let metaText = "Fetching…";
  let pct = 0;
  let chipTitle = "View fetch progress";

  if (state.fetchBusy && state.fetchingCompanyKey) {
    const company = state.fetchingCompanyKey.split(":").slice(1).join(":");
    metaText = company || "Fetching…";
    chipTitle = `View progress — ${company}`;
  } else if (summary.total > 0) {
    pct = Math.min(99, Math.round((summary.current / summary.total) * 100));
    metaText = `${summary.current}/${summary.total}`;
    chipTitle = `View progress — ${summary.current} of ${summary.total} companies (${pct}%)`;
    if (summary.company) {
      metaText = `${summary.current}/${summary.total} · ${summary.company}`;
      chipTitle += ` · ${summary.company}`;
    }
  } else if (summary.company) {
    metaText = summary.company;
    chipTitle = `View progress — ${summary.company}`;
  } else if (summary.countryLabel) {
    metaText = summary.countryLabel;
    chipTitle = `View progress — ${summary.countryLabel}`;
  }

  return {
    controlsEnabled: true,
    active: true,
    showButton: false,
    showChip: true,
    metaText,
    pct: Math.max(4, pct),
    chipTitle,
  };
}

export function publishFetchUi() {
  publishFetchView({
    header: buildHeaderState(),
    panel: snapshotPanelState(),
  });
}

export function patchFetchPanel(patch) {
  Object.assign(fetchPanelState, patch);
  publishFetchUi();
}
