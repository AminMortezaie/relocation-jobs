/** Shared mutable application state. */

export const state = {
  allCompanies: [],
  pollTimer: null,
  fetchingCompanyKey: null,
  collapsedCompanies: new Set(),
  showNotForMeCompanies: new Set(),
  showRejectedCompanies: new Set(),
  scrapeConfig: { default_concurrency: 16, max_concurrency: 64 },
  authState: { authenticated: false, allow_register: false },
  loginMode: "login",
  editCareersContext: null,
  editCompanyNameContext: null,
  editCityContext: null,
  fetchPanelSingle: false,
  fetchReviewFeedback: null,
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
  return state.allCompanies.find(
    (c) => c.country === country && c.name === company
  );
}

function looseJobUrl(url) {
  return (url || "").trim().replace(/\/$/, "");
}

export function findJobInCompany(company, url, idempotencyKey = "") {
  const jobs = company.jobs || [];
  const direct = jobs.find((j) => j.url === url);
  if (direct) return direct;
  const key = (idempotencyKey || "").trim();
  if (key) {
    const byKey = jobs.find((j) => j.idempotency_key === key);
    if (byKey) return byKey;
  }
  const loose = looseJobUrl(url);
  if (!loose) return undefined;
  return jobs.find((j) => looseJobUrl(j.url) === loose);
}
