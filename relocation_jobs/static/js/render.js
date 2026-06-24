/** HTML rendering for stats, companies, and job rows. */

import { state, findCompany } from "./state.js";
import { $, escapeHtml, escapeAttr, formatAppliedLabel, formatAppliedHistoryTitle, formatActivityBadge, formatFetchDuration, parseFetchTimestamp, elapsedSecondsBetween, elapsedSecondsSince, atsScoreTone } from "./utils.js";
import {
  saveCollapsedCompanies,
  saveShowNotForMeCompanies,
  saveShowRejectedCompanies,
} from "./storage.js";
import { syncBoardView } from "./board-view.js";
import { updateFetchHeaderUI } from "./fetch-render.js";

function jobActivityTs(job) {
  return (job?.fetched || job?.last_seen || "").trim();
}

export function normalizeTsForSort(ts) {
  const value = (ts || "").trim();
  if (!value) return "0000-00-00T00:00:00";
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return `${value}T00:00:00`;
  return value.replace(/Z$/, "+00:00");
}

function companyActivityTs(company) {
  return (company?.latest_fetched || company?.updated || "").trim();
}

function fetchRunScopeLabel(run) {
  if (run?.company_name) return run.company_name;
  const done = Number(run?.companies_done) || 0;
  const total = Number(run?.companies_total) || 0;
  if (total > 0) return `${done}/${total} companies`;
  return "All companies";
}

function fetchRunStatusLabel(run) {
  if (run?.cancelled) return "Cancelled";
  const code = run?.exit_code;
  if (code === 0 || code == null) return "Complete";
  return `Exit ${code}`;
}

function renderFetchRunsTable(runs) {
  const items = Array.isArray(runs) ? runs : [];
  if (!items.length) {
    return `<p class="stats-fetch-runs-empty">No fetch runs recorded yet.</p>`;
  }
  const rows = items.map((run) => {
    const finished = escapeHtml(formatActivityBadge(run.finished_at || run.started_at || ""));
    const scope = escapeHtml(fetchRunScopeLabel(run));
    const duration = escapeHtml(formatFetchDuration(run.duration_seconds));
    const newJobs = Number(run.new_jobs) || 0;
    const status = escapeHtml(fetchRunStatusLabel(run));
    const statusClass = run.cancelled
      ? "stats-fetch-run-status--cancelled"
      : (run.exit_code === 0 || run.exit_code == null
        ? "stats-fetch-run-status--ok"
        : "stats-fetch-run-status--error");
    return `<tr>
      <td>${finished}</td>
      <td>${scope}</td>
      <td>${duration}</td>
      <td>${newJobs}</td>
      <td><span class="stats-fetch-run-status ${statusClass}">${status}</span></td>
    </tr>`;
  }).join("");
  return `
    <table class="stats-fetch-runs-table">
      <thead>
        <tr>
          <th>Finished</th>
          <th>Scope</th>
          <th>Duration</th>
          <th>New</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>`;
}

function compareDateDesc(a, b) {
  const av = normalizeTsForSort(a);
  const bv = normalizeTsForSort(b);
  if (av === bv) return 0;
  if (av === "0000-00-00T00:00:00") return 1;
  if (bv === "0000-00-00T00:00:00") return -1;
  return bv.localeCompare(av);
}

function companySortKey(company) {
  return `${company.country}:${company.name}`;
}

function isFetchingCompany(company) {
  return state.fetchBusy && state.fetchingCompanyKey === companySortKey(company);
}

function compareCompaniesDefault(a, b) {
  if ($("sortNewestFetch").checked) {
    const aFetching = isFetchingCompany(a);
    const bFetching = isFetchingCompany(b);
    if (aFetching !== bFetching) return aFetching ? -1 : 1;
    return compareDateDesc(companyActivityTs(a), companyActivityTs(b));
  }
  const byCountry = (a.country_label || a.country || "").localeCompare(
    b.country_label || b.country || "",
    undefined,
    { sensitivity: "base" }
  );
  if (byCountry !== 0) return byCountry;
  return (a.name || "").localeCompare(b.name || "", undefined, { sensitivity: "base" });
}

export function sortCompaniesList(companies) {
  const list = [...companies];
  const frozen = state.frozenCompanyOrder;
  if (frozen) {
    // While a fetch is active we keep the pre-fetch order so cards don't
    // reshuffle as their fetch timestamps update. Companies absent from the
    // frozen snapshot (newly added) sort normally after the frozen ones.
    list.sort((a, b) => {
      const ai = frozen.get(companySortKey(a));
      const bi = frozen.get(companySortKey(b));
      const aKnown = ai !== undefined;
      const bKnown = bi !== undefined;
      if (aKnown && bKnown) return ai - bi;
      if (aKnown !== bKnown) return aKnown ? -1 : 1;
      return compareCompaniesDefault(a, b);
    });
    return list;
  }
  list.sort(compareCompaniesDefault);
  return list;
}

/** Snapshot the current display order so an active fetch can't reshuffle it. */
export function freezeCompanyOrder() {
  if (state.frozenCompanyOrder) return;
  const map = new Map();
  [...state.allCompanies]
    .sort(compareCompaniesDefault)
    .forEach((company, index) => map.set(companySortKey(company), index));
  state.frozenCompanyOrder = map;
}

/** Release the frozen order so the board re-sorts on the next render. */
export function releaseCompanyOrder() {
  state.frozenCompanyOrder = null;
}

function companyHasNoVisibleJobs(company) {
  const jobCount = company.job_count ?? (company.jobs || []).length ?? 0;
  return jobCount === 0;
}

function companyHasCollapsedPositions(company) {
  return state.collapsedCompanies.has(companySortKey(company));
}

function companyCityLabels(company) {
  if (Array.isArray(company.cities) && company.cities.length) {
    return company.cities;
  }
  const single = (company.city || "").trim();
  if (!single) return [];
  return single.split(",").map((part) => part.trim()).filter(Boolean);
}

function companyLocationLabels(company) {
  if (Array.isArray(company.locations) && company.locations.length) {
    return company.locations.map(
      (loc) => loc.label || `${loc.city} (${loc.country_label || loc.country})`
    );
  }
  return companyCityLabels(company);
}

function formatCompanyCities(company) {
  const labels = companyLocationLabels(company);
  return labels.length ? labels.join(" · ") : "Set locations";
}

export function filterCompanies() {
  const q = $("search").value.trim().toLowerCase();
  return state.allCompanies.filter((c) => {
    if ($("hideEmpty")?.checked && companyHasNoVisibleJobs(c)) return false;
    if ($("hideCollapsedCompanies")?.checked && companyHasCollapsedPositions(c)) return false;
    if (!q) return true;
    const hay = [
      c.name,
      c.city,
      ...companyCityLabels(c),
      ...companyLocationLabels(c),
      c.country_label,
      ...(c.jobs || []).map((j) => j.title),
      ...(c.not_for_me_jobs || c.hidden_jobs || []).map((j) => j.title),
      ...(c.rejected_jobs || []).map((j) => j.title),
    ].join(" ").toLowerCase();
    return hay.includes(q);
  });
}

export function getDisplayCompanies() {
  return sortCompaniesList(filterCompanies());
}

function hasAtsScore(job) {
  return job?.ats_score != null && job?.ats_score !== "";
}

export function sortJobsForDisplay(jobs) {
  const list = jobs || [];
  if (!list.length) return list;

  const scored = [];
  const unscored = [];
  for (const job of list) {
    if (hasAtsScore(job)) scored.push(job);
    else unscored.push(job);
  }

  scored.sort((a, b) => Number(b.ats_score) - Number(a.ats_score));
  return [...scored, ...unscored];
}

function statCard(value, label, { accent = false, muted = false } = {}) {
  const valueCls = [
    accent ? " stat-value--accent" : "",
    muted ? " stat-value--muted" : "",
  ].join("");
  return `
    <div class="stat">
      <div class="value${valueCls}">${value}</div>
      <div class="label">${escapeHtml(label)}</div>
    </div>
  `;
}

export function renderStats(stats) {
  const appliedToday = stats.applied_today_jobs || [];
  const appliedTodayDetail = appliedToday.length
    ? `<ul class="stats-applied-today-list">${appliedToday.map((job) => `
        <li>
          <span class="stats-applied-today-company">${escapeHtml(job.company || "Company")}</span>
          ${job.title ? `<span class="stats-applied-today-title">${escapeHtml(job.title)}</span>` : ""}
        </li>`).join("")}</ul>`
    : `<p class="stats-applied-today-empty">No applications recorded today.</p>`;

  $("stats").innerHTML = `
    <div class="stats-dashboard">
      <section class="stats-group">
        <div class="stats-row">
          ${statCard(stats.total_jobs, "Open roles", { accent: true })}
          ${statCard(stats.companies_with_jobs, "Companies")}
          ${statCard(stats.latest_fetch_new_jobs ?? 0, "New last fetch")}
          ${statCard(escapeHtml(formatActivityBadge(stats.latest_job_fetch || "")) || "—", "Last fetch", { muted: true })}
        </div>
      </section>
      <section class="stats-group">
        <div class="stats-row">
          <div class="stat stat-applied-today">
            <div class="value stat-value--accent">${stats.positions_applied_today ?? 0}</div>
            <div class="label">Applied today</div>
            ${appliedTodayDetail}
          </div>
          ${statCard(stats.positions_applied ?? 0, "Applied total")}
          ${statCard(stats.applied ?? 0, "Companies applied")}
          ${statCard(stats.positions_rejected ?? 0, "Rejections")}
          ${statCard(stats.not_for_me ?? 0, "Hidden")}
          ${statCard(stats.visa_sponsored, "Visa / relocation")}
          ${statCard(stats.fetch_problems ?? 0, "Fetch issues")}
        </div>
      </section>
    </div>
  `;
}


export const HIDE_REASONS = [
  { id: "not_for_me", label: "Not for me", desc: "Role doesn't fit your goals", tone: "not-for-me" },
  { id: "wrong_location", label: "Wrong location", desc: "City or region isn't relevant", tone: "wrong-location" },
  { id: "no_relocation", label: "No relocation", desc: "No visa or relocation support", tone: "no-relocation" },
];

export function notForMeReasonMeta(reason) {
  const hit = HIDE_REASONS.find((r) => r.id === reason);
  if (hit) return { label: hit.label, badgeCls: hit.tone };
  return { label: HIDE_REASONS[0].label, badgeCls: HIDE_REASONS[0].tone };
}

export function renderCompanies() {
  syncBoardView();
}
export function toggleCompanyCollapse(key) {
  if (state.collapsedCompanies.has(key)) {
    state.collapsedCompanies.delete(key);
  } else {
    state.collapsedCompanies.add(key);
  }
  saveCollapsedCompanies();
  renderCompanies();
}

export function toggleShowNotForMe(key) {
  if (state.showNotForMeCompanies.has(key)) {
    state.showNotForMeCompanies.delete(key);
  } else {
    state.showNotForMeCompanies.add(key);
    state.collapsedCompanies.delete(key);
    saveCollapsedCompanies();
  }
  saveShowNotForMeCompanies();
  renderCompanies();
}

export function toggleShowRejected(key) {
  if (state.showRejectedCompanies.has(key)) {
    state.showRejectedCompanies.delete(key);
  } else {
    state.showRejectedCompanies.add(key);
    state.collapsedCompanies.delete(key);
    saveCollapsedCompanies();
  }
  saveShowRejectedCompanies();
  renderCompanies();
}

function touchFetchingCompanyTimestamp(companyKey) {
  if (!companyKey) return;
  const company = state.boardCatalog.find((c) => companySortKey(c) === companyKey);
  if (!company) return;
  const ts = new Date().toISOString().replace(/\.\d{3}Z$/, "+00:00");
  company.updated = ts;
  company.newest_job_fetched = ts;
}

export function setFetchBusy(busy, companyKey = null, { countryScope = false } = {}) {
  if (!busy) {
    state.fetchBusy = false;
    state.countryFetchActive = false;
    state.fetchingCompanyKey = null;
    state.fetchJobSummary = null;
    state.serverFetchRunning = false;
    $("addCompanyBtn").disabled = false;
    updateFetchHeaderUI();
    syncBoardView();
    return;
  }

  freezeCompanyOrder();
  if (busy && companyKey) {
    touchFetchingCompanyTimestamp(companyKey);
  }
  if (countryScope) {
    state.countryFetchActive = true;
    state.fetchBusy = false;
    state.fetchingCompanyKey = null;
  } else {
    state.fetchBusy = true;
    state.countryFetchActive = false;
    state.fetchingCompanyKey = companyKey || null;
  }
  state.serverFetchRunning = true;
  $("addCompanyBtn").disabled = !countryScope && state.fetchBusy;
  updateFetchHeaderUI();
  syncBoardView();
}

export function syncFetchJobSummary(st) {
  state.serverFetchRunning = Boolean(st?.running);
  const progress = st?.progress || {};
  state.fetchJobSummary = {
    current: progress.current || 0,
    total: progress.total || (st?.company ? 1 : 0),
    company: progress.company || st?.company || null,
    country: st?.country || null,
    countryLabel: st?.country ? countryLabelFromId(st.country) : "",
    activityMessage: (st?.activity?.message || "").trim(),
    newJobs: Math.max(0, Number(st?.new_jobs_total) || 0),
  };
  state.lastFetchStatus = st;
  // Only refresh the header chip on each poll tick. The board data does not
  // change during polling (it reloads once at completion), so re-rendering the
  // whole company list here just replays the card entrance animation and makes
  // cards visibly jump. The board is re-rendered by setFetchBusy / loadJobs.
  updateFetchHeaderUI();
}

function countryLabelFromId(countryId) {
  const opt = [...($("country")?.options || [])].find((o) => o.value === countryId);
  return opt?.textContent?.trim() || countryId || "";
}

export {
  updateFetchHeaderUI,
  openFetchPanel,
  hideFetchPanel,
  showFetchPanel,
  updateFetchProgress,
  setFetchPanelRunning,
  hideFetchCompletion,
  updateFetchRunMeta,
  showFetchCompletion,
  finishFetchPanel,
  appendFetchLog,
  updateFetchActivity,
  clearFetchReviewContent,
  clearFetchReview,
  setFetchReviewFeedbackDone,
  setFetchReviewFooterPending,
  showFetchReviewFeedback,
  renderFetchReview,
  toggleFetchReviewFilteredExpanded,
  setFetchLogMode,
  normalizeReviewJobs,
  setFetchCancelPending,
  patchRunningFetchPanel,
  showFetchNotice,
} from "./fetch-render.js";
