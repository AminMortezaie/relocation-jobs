/** Shared mutable application state. */

export const state = {
  boardCatalog: [],
  boardMeta: {},
  boardUserStats: {},
  boardScopeKey: "",
  boardRequestKey: "",
  boardPage: 1,
  allCompanies: [],
  pollTimer: null,
  fetchVisibilityHandler: null,
  fetchingCompanyKey: null,
  showNotForMeCompanies: new Set(),
  showRejectedCompanies: new Set(),
  scrapeConfig: { default_concurrency: 16, max_concurrency: 16 },
  atsTypes: [],
  authState: { authenticated: false, allow_register: false },
  loginMode: "login",
  editCareersContext: null,
  editCompanyNameContext: null,
  editCityContext: null,
  fetchPanelSingle: false,
  fetchReviewFeedback: null,
  boardStats: null,
  fetchBusy: false,
  countryFetchActive: false,
  fetchJobSummary: null,
  serverFetchRunning: false,
  fetchPollFailures: 0,
  lastFetchStatus: null,
  fetchControlsEnabled: false,
  frozenCompanyOrder: null,
  fetchPollInFlight: false,
  boardEnterTimer: null,

  /** Fetch session — single-company fetch lifecycle to prevent stale UI. */
  fetchSession: {
    phase: "idle", // idle | starting | running | complete | settling
    runId: null,
    kind: null,    // "company" | "country"
    country: null,
    company: null,
    boardDirty: false,
  },
};

/** Called by api.js on 401 — wired in main.js to avoid circular imports. */
export let onUnauthorized = () => {};

export function setOnUnauthorized(fn) {
  onUnauthorized = fn;
}

export function companyKey(country, company) {
  return `${country}:${company}`;
}

export function findCompany(country, company) {
  return state.boardCatalog.find(
    (c) => c.country === country && c.name === company
  );
}

export function looseJobUrl(url) {
  return (url || "").trim().replace(/\/$/, "");
}

/**
 * Fetch session helpers — single-company lifecycle.
 * Each helper returns a shallow copy so callers can chain.
 */
export function beginCompanySession(country, company) {
  state.fetchSession.phase = "starting";
  state.fetchSession.runId = null;
  state.fetchSession.kind = "company";
  state.fetchSession.country = country;
  state.fetchSession.company = company;
  state.fetchSession.boardDirty = false;
  return { ...state.fetchSession };
}

export function bindSessionRun(runId) {
  state.fetchSession.phase = "running";
  state.fetchSession.runId = runId;
  return { ...state.fetchSession };
}

export function completeSession() {
  state.fetchSession.phase = "complete";
  state.fetchSession.boardDirty = true;
  return { ...state.fetchSession };
}

export function endSession() {
  state.fetchSession.phase = "idle";
  state.fetchSession.runId = null;
  state.fetchSession.kind = null;
  state.fetchSession.country = null;
  state.fetchSession.company = null;
  state.fetchSession.boardDirty = false;
}

export function isSessionActive() {
  return state.fetchSession.phase !== "idle";
}

export function isSessionRunning() {
  return state.fetchSession.phase === "running" || state.fetchSession.phase === "starting";
}

export function sessionOwnsRun(runId) {
  if (!isSessionRunning()) return false;
  if (state.fetchSession.runId == null) return true; // no bound run yet — all status belongs to us
  return Number(state.fetchSession.runId) === Number(runId);
}

function companyJobLists(company) {
  return [
    company.jobs || [],
    company.rejected_jobs || [],
    company.not_for_me_jobs || [],
    company.hidden_jobs || [],
  ].filter(Array.isArray);
}

export function findJobInCompany(company, url, idempotencyKey = "") {
  const jobs = companyJobLists(company).flat();
  const raw = (url || "").trim();
  const loose = looseJobUrl(raw);
  const key = (idempotencyKey || "").trim();

  if (raw) {
    const exact = jobs.find((j) => j.url === raw);
    if (exact) return exact;
  }
  if (loose) {
    const looseMatches = jobs.filter((j) => looseJobUrl(j.url) === loose);
    if (looseMatches.length === 1) return looseMatches[0];
    if (looseMatches.length > 1 && key) {
      const keyed = looseMatches.find((j) => j.idempotency_key === key);
      if (keyed) return keyed;
    }
  }
  if (key) {
    const keyMatches = jobs.filter((j) => j.idempotency_key === key);
    if (keyMatches.length === 1) return keyMatches[0];
    if (keyMatches.length > 1) {
      if (raw) {
        const exactAmong = keyMatches.find((j) => j.url === raw);
        if (exactAmong) return exactAmong;
      }
      if (loose) {
        const looseAmong = keyMatches.find((j) => looseJobUrl(j.url) === loose);
        if (looseAmong) return looseAmong;
      }
    }
  }
  return undefined;
}
