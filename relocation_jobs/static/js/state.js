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
  collapsedCompanies: new Set(),
  showNotForMeCompanies: new Set(),
  showRejectedCompanies: new Set(),
  scrapeConfig: { default_concurrency: 16, max_concurrency: 16 },
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
  fetchingCompanyKey: null,
  fetchJobSummary: null,
  serverFetchRunning: false,
  fetchPollFailures: 0,
  lastFetchStatus: null,
  fetchControlsEnabled: false,
  frozenCompanyOrder: null,
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
