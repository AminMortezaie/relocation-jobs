/** HTML rendering for stats, companies, and job rows. */

import { state, findCompany } from "./state.js";
import { $, escapeHtml, escapeAttr, formatAppliedLabel, formatAppliedHistoryTitle, formatActivityBadge, formatFetchDuration, parseFetchTimestamp, elapsedSecondsBetween, elapsedSecondsSince, atsScoreTone } from "./utils.js";
import {
  saveCollapsedCompanies,
  saveShowNotForMeCompanies,
  saveShowRejectedCompanies,
} from "./storage.js";

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


function renderAtsScoreWidget(j) {
  const hasScore = j.ats_score != null && j.ats_score !== "";
  const score = hasScore ? Number(j.ats_score) : 70;
  const tone = hasScore ? atsScoreTone(score) : "";
  const triggerInner = hasScore
    ? `<span class="ats-score-ring" style="--ats-pct: ${score}"><span class="ats-score-num">${score}</span></span>`
    : `<span class="ats-score-ring ats-score-ring--empty" aria-hidden="true">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M12 5v14M5 12h14"/>
        </svg>
      </span><span class="ats-score-trigger-text">ATS</span>`;
  const clearBtn = hasScore
    ? `<button type="button" class="ats-score-clear-btn link-btn">Remove score</button>`
    : "";
  return `
    <div class="ats-score-wrap">
      <button
        type="button"
        class="ats-score-trigger${hasScore ? ` ats-has-score ${tone}` : " ats-empty"}"
        aria-expanded="false"
        aria-haspopup="dialog"
        title="${hasScore ? `ATS score ${score} — click to edit` : "Set ATS resume match score"}"
      >
        ${triggerInner}
      </button>
      <div class="ats-score-popover" hidden role="dialog" aria-label="ATS score for ${escapeAttr(j.title)}">
        <div class="ats-score-popover-head">
          <span class="ats-score-popover-title">Resume ATS match</span>
          <button type="button" class="ats-score-close" aria-label="Close">×</button>
        </div>
        <div class="ats-score-preview-wrap ${hasScore ? atsScoreTone(score) : "ats-mid"}">
          <div class="ats-score-ring-preview" style="--ats-pct: ${score}">
            <span class="ats-score-preview">${score}</span>
          </div>
          <div class="ats-score-manual">
            <input
              type="number"
              class="ats-score-number"
              min="0"
              max="100"
              step="1"
              value="${score}"
              aria-label="ATS score"
            />
            <span class="ats-score-manual-unit">/ 100</span>
          </div>
        </div>
        <div class="ats-score-slider-wrap">
          <input
            type="range"
            class="ats-score-slider"
            min="0"
            max="100"
            step="1"
            value="${score}"
            aria-label="ATS score slider"
          />
          <div class="ats-score-slider-labels"><span>0</span><span>50</span><span>100</span></div>
        </div>
        <div class="ats-score-quick" role="group" aria-label="Quick scores">
          ${[40, 60, 75, 90].map((n) => `
            <button type="button" class="ats-quick-chip" data-score="${n}">${n}</button>
          `).join("")}
        </div>
        <div class="ats-score-popover-foot">
          <button type="button" class="ats-score-save-btn">Save score</button>
          ${clearBtn}
        </div>
      </div>
    </div>
  `;
}

function renderWaitingReferralWidget(j) {
  const active = Boolean(j.waiting_referral);
  const linkedin = (j.referral_linkedin_url || "").trim();
  const dateSuffix = j.waiting_referral_date ? ` · ${escapeHtml(j.waiting_referral_date)}` : "";
  return `
    <div class="referral-wrap">
      <button
        type="button"
        class="referral-btn${active ? " active" : ""}"
        aria-expanded="false"
        aria-haspopup="dialog"
        title="${active ? "Edit referrer LinkedIn" : "Waiting for someone to refer you"}"
      >
        Waiting referral${active ? dateSuffix : ""}
      </button>
      <div class="referral-popover" hidden role="dialog" aria-label="Referrer LinkedIn for ${escapeAttr(j.title)}">
        <div class="referral-popover-head">
          <span class="referral-popover-title">Referrer LinkedIn</span>
          <button type="button" class="referral-close" aria-label="Close">×</button>
        </div>
        <p class="referral-popover-hint">Profile of the person you asked to refer you.</p>
        <input
          type="url"
          class="referral-linkedin-input"
          placeholder="https://www.linkedin.com/in/username"
          value="${escapeAttr(linkedin)}"
          spellcheck="false"
        />
        <div class="referral-popover-foot">
          <button type="button" class="referral-save-btn">Save</button>
          ${active ? `<button type="button" class="referral-clear-btn link-btn">Clear status</button>` : ""}
        </div>
      </div>
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

function renderHideReasonPicker(currentReason = "") {
  const active = currentReason ? notForMeReasonMeta(currentReason) : null;
  const triggerTone = active?.badgeCls || "not-for-me";
  const triggerLabel = active ? active.label : "Not for me";
  const popoverTitle = currentReason ? "Change category" : "Why hide this role?";
  const options = HIDE_REASONS.map((r) => {
    const isCurrent = Boolean(currentReason) && r.id === currentReason;
    return `
      <button
        type="button"
        class="hide-reason-option hide-reason-option--${r.tone}${isCurrent ? " is-current" : ""}"
        data-reason="${r.id}"
        role="menuitem"
        ${isCurrent ? 'aria-current="true"' : ""}
      >
        <span class="hide-reason-option-dot" aria-hidden="true"></span>
        <span class="hide-reason-option-text">
          <span class="hide-reason-option-label">${escapeHtml(r.label)}</span>
          <span class="hide-reason-option-desc">${escapeHtml(r.desc)}</span>
        </span>
      </button>
    `;
  }).join("");

  return `
    <div class="hide-reason-wrap" data-current-reason="${escapeAttr(currentReason || "")}">
      <button
        type="button"
        class="hide-reason-trigger hide-reason-trigger--${triggerTone}"
        aria-expanded="false"
        aria-haspopup="menu"
        title="${currentReason ? "Change hide category" : "Hide this role"}"
      >
        ${escapeHtml(triggerLabel)}
        <svg class="hide-reason-chevron" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" aria-hidden="true">
          <path d="M6 9l6 6 6-6"/>
        </svg>
      </button>
      <div class="hide-reason-popover" hidden role="menu" aria-label="${escapeAttr(popoverTitle)}">
        <p class="hide-reason-popover-title">${escapeHtml(popoverTitle)}</p>
        <div class="hide-reason-options">${options}</div>
      </div>
    </div>
  `;
}

function newestStatusDate(dates, fallback = "") {
  const list = (dates || []).filter(Boolean).map((d) => String(d).trim()).filter(Boolean);
  const fb = (fallback || "").trim();
  if (fb) list.push(fb);
  list.sort();
  return list.length ? list[list.length - 1] : "";
}

function statusHistoryLabel(kind, dates, currentDate = "") {
  const newest = newestStatusDate(dates, currentDate);
  if (!newest) return kind;
  return `${kind} · ${newest}`;
}

function statusHistoryTitle(dates) {
  const list = (dates || []).filter(Boolean);
  return list.length ? `${list.join(", ")}` : "";
}

function renderJobCityBadge(j) {
  const label = (j.job_city || j.location || "").trim();
  if (!label) return "";
  return `<span class="badge job-city">${escapeHtml(label)}</span>`;
}

function renderPositionTitleRow(j) {
  return `
    <div class="position-title-row">
      <a class="job-title" href="${escapeAttr(j.url)}" target="_blank" rel="noopener">${escapeHtml(j.title)}</a>
      ${renderJobCityBadge(j)}
    </div>`;
}

function renderPosition(j) {
  const visa = j.visa_sponsorship === true
    ? '<span class="badge visa">Visa / relocation</span>'
    : "";
  const posCls = [
    j.applied ? " position-applied" : "",
    j.waiting_referral ? " position-waiting-referral" : "",
    j.looking_to_apply && !j.applied ? " position-looking-to-apply" : "",
    j.seen ? " position-seen" : "",
  ].join("");
  const appliedHistory = j.applied_history || [];
  const appliedEvents = j.applied_events || [];
  const latestApplied = newestStatusDate(appliedHistory, j.applied_date || "");
  const appliedLabel = formatAppliedLabel({ date: latestApplied, at: j.applied_at || "" });
  const appliedTitle = formatAppliedHistoryTitle(appliedEvents.length ? appliedEvents : appliedHistory);
  const appliedBtn = j.applied
    ? `<button type="button" class="applied-btn active" data-applied="1" title="${escapeAttr(appliedTitle ? `Applied on: ${appliedTitle}` : "Clear applied mark")}">${escapeHtml(appliedLabel)}</button>`
    : `<button type="button" class="applied-btn" data-applied="0" title="Mark that you applied">I applied</button>`;
  const rejectedBtn = `<button type="button" class="rejected-btn" data-rejected="0" title="Mark that you got a rejection">Got rejection</button>`;
  const lookingToApplyBtn = j.looking_to_apply
    ? `<button type="button" class="looking-to-apply-btn active" data-looking="1" title="Clear looking-to-apply mark">Looking to apply${j.looking_to_apply_date ? ` · ${escapeHtml(j.looking_to_apply_date)}` : ""}</button>`
    : `<button type="button" class="looking-to-apply-btn" data-looking="0" title="Mark as interested in applying">Looking to apply</button>`;
  const sawBeforeBtn = j.seen
    ? `<button type="button" class="saw-before-btn active" data-seen="1" title="Clear saw-before mark">Saw before${j.seen_date ? ` · ${escapeHtml(j.seen_date)}` : ""}</button>`
    : `<button type="button" class="saw-before-btn" data-seen="0" title="Mark that you saw this position before">Saw before</button>`;
  const hideBtns = j.applied ? "" : renderHideReasonPicker();
  const statusBadges = [
    visa,
    j.applied
      ? `<span class="badge applied"${appliedTitle ? ` title="${escapeAttr(`Applied on: ${appliedTitle}`)}"` : ""}>${escapeHtml(appliedLabel)}</span>`
      : "",
    !j.applied && latestApplied
      ? `<span class="badge applied" title="${escapeAttr(formatAppliedHistoryTitle(appliedEvents.length ? appliedEvents : appliedHistory))}">${escapeHtml(formatAppliedLabel({ date: latestApplied, at: j.applied_at || "" }, { before: true }))}</span>`
      : "",
    j.waiting_referral && j.referral_linkedin_url
      ? `<a class="badge referral" href="${escapeAttr(j.referral_linkedin_url)}" target="_blank" rel="noopener">Referrer</a>`
      : (j.waiting_referral ? `<span class="badge referral">Waiting referral</span>` : ""),
    j.looking_to_apply && !j.applied ? `<span class="badge looking-to-apply">Looking to apply${j.looking_to_apply_date ? ` · ${escapeHtml(j.looking_to_apply_date)}` : ""}</span>` : "",
    j.seen ? `<span class="badge seen">Saw before${j.seen_date ? ` · ${escapeHtml(j.seen_date)}` : ""}</span>` : "",
    `<span class="badge date">${escapeHtml(formatActivityBadge(jobActivityTs(j)))}</span>`,
  ].filter(Boolean).join("");

  return `
    <div class="position-card${posCls}" data-country="${escapeAttr(j.country)}" data-company="${escapeAttr(j.company)}" data-url="${escapeAttr(j.url)}" data-idempotency-key="${escapeAttr(j.idempotency_key || "")}">
      <div class="position-top">
        <div class="position-head">
          ${renderPositionTitleRow(j)}
          <div class="position-badges">${statusBadges}</div>
        </div>
        <div class="position-side">${renderAtsScoreWidget(j)}</div>
      </div>
      <div class="position-actions">
        ${appliedBtn}
        ${rejectedBtn}
        ${j.applied ? "" : lookingToApplyBtn}
        ${sawBeforeBtn}
        ${renderWaitingReferralWidget(j)}
        ${hideBtns}
      </div>
    </div>
  `;
}

function renderRejectedJob(j) {
  const visa = j.visa_sponsorship === true
    ? '<span class="badge visa">Visa / relocation</span>'
    : "";
  const rejectedHistory = j.rejected_history || [];
  const appliedHistory = j.applied_history || [];
  const appliedEvents = j.applied_events || [];
  const latestRejected = newestStatusDate(rejectedHistory, j.rejected_date || "");
  const latestApplied = newestStatusDate(appliedHistory, j.applied_date || "");
  const rejectedLabel = latestRejected ? `Rejected · ${latestRejected}` : "Rejected";
  const rejectedTitle = statusHistoryTitle(rejectedHistory);
  const appliedTitle = formatAppliedHistoryTitle(appliedEvents.length ? appliedEvents : appliedHistory);
  const statusBadges = [
    `<span class="badge rejected"${rejectedTitle ? ` title="${escapeAttr(`Rejected on: ${rejectedTitle}`)}"` : ""}>${escapeHtml(rejectedLabel)}</span>`,
    latestApplied
      ? `<span class="badge applied" title="${escapeAttr(appliedTitle)}">${escapeHtml(formatAppliedLabel({ date: latestApplied, at: j.applied_at || "" }))}</span>`
      : "",
    visa,
    j.seen ? `<span class="badge seen">Saw before${j.seen_date ? ` · ${escapeHtml(j.seen_date)}` : ""}</span>` : "",
    `<span class="badge date">${escapeHtml(formatActivityBadge(jobActivityTs(j)))}</span>`,
  ].filter(Boolean).join("");
  return `
    <div class="position-card rejected-role${j.seen ? " position-seen" : ""}" data-country="${escapeAttr(j.country)}" data-company="${escapeAttr(j.company)}" data-url="${escapeAttr(j.url)}" data-idempotency-key="${escapeAttr(j.idempotency_key || "")}">
      <div class="position-top">
        <div class="position-head">
          ${renderPositionTitleRow(j)}
          <div class="position-badges">${statusBadges}</div>
        </div>
        <div class="position-side">${renderAtsScoreWidget(j)}</div>
      </div>
      <div class="position-actions">
        <button type="button" class="reapply-btn" title="Return to open positions so you can apply again">Reapply</button>
      </div>
    </div>
  `;
}

function renderNotForMeJob(j) {
  const visa = j.visa_sponsorship === true
    ? '<span class="badge visa">Visa / relocation</span>'
    : "";
  const taggedDate = j.not_for_me_date ? ` · ${escapeHtml(j.not_for_me_date)}` : "";
  const { label: hideLabel, badgeCls: hideBadgeCls } = notForMeReasonMeta(j.not_for_me_reason);
  const statusBadges = [
    `<span class="badge ${hideBadgeCls}">${escapeHtml(hideLabel)}${taggedDate}</span>`,
    visa,
    `<span class="badge date">${escapeHtml(formatActivityBadge(jobActivityTs(j)))}</span>`,
  ].filter(Boolean).join("");
  return `
    <div class="position-card not-for-me-role" data-country="${escapeAttr(j.country)}" data-company="${escapeAttr(j.company)}" data-url="${escapeAttr(j.url)}">
      <div class="position-top">
        <div class="position-head">
          ${renderPositionTitleRow(j)}
          <div class="position-badges">${statusBadges}</div>
        </div>
        <div class="position-side">${renderAtsScoreWidget(j)}</div>
      </div>
      <div class="position-actions">
        ${renderHideReasonPicker(j.not_for_me_reason || "not_for_me")}
        <button type="button" class="restore-job-btn" title="Move back to applicable roles">Restore</button>
      </div>
    </div>
  `;
}

export function renderCompanies() {
  const list = $("jobs");
  const filtered = getDisplayCompanies();
  if (!filtered.length) {
    list.innerHTML = `<div class="empty">No companies match your filters. Try another country or click <strong>Fetch new jobs</strong>.</div>`;
    return;
  }
  list.innerHTML = filtered.map((c) => {
    const companyCls = [
      c.company_applied ? " company-applied" : "",
      c.awaiting_response ? " company-awaiting-response" : "",
      c.fetch_problem ? " fetch-problem" : "",
      c.fetch_ok && !c.fetch_problem ? " fetch-ok" : "",
    ].join("");
    const careers = c.careers_url
      ? `<div class="careers-row">
          <a class="job-title" href="${escapeAttr(c.careers_url)}" target="_blank" rel="noopener" style="font-size:0.8rem;font-weight:500">Careers page</a>
          <button type="button" class="edit-careers-btn" data-country="${escapeAttr(c.country)}" data-country-label="${escapeAttr(c.country_label || "")}" data-company="${escapeAttr(c.name)}" data-url="${escapeAttr(c.careers_url)}" title="Fix wrong careers URL">Edit URL</button>
        </div>`
      : `<div class="careers-row">
          <span class="job-meta">No careers URL</span>
          <button type="button" class="edit-careers-btn" data-country="${escapeAttr(c.country)}" data-country-label="${escapeAttr(c.country_label || "")}" data-company="${escapeAttr(c.name)}" data-url="" title="Add careers URL">Edit URL</button>
        </div>`;
    const rejectedCount = (c.rejected_jobs || []).length;
    const emptyMsg = c.job_count === 0
      ? (c.stored_job_count > 0
          ? (c.positions_not_for_me >= c.stored_job_count
              ? "All roles marked not for me — click <strong>Show not for me jobs</strong> below."
              : (rejectedCount >= c.stored_job_count
                  ? "All roles marked rejected — click <strong>Show rejected jobs</strong> below."
                  : (c.positions_hidden_by_visa > 0 && $("visaOnly").checked
                      ? "No visa / relocation roles in cache for this company."
                      : "No roles match your current filters.")))
          : "No jobs yet — click <strong>Fetch jobs</strong>.")
      : "No matching roles (try turning off visa filter).";
    const jobsHtml = sortJobsForDisplay(c.jobs).map(renderPosition).join("");
    const companyKeyStr = `${c.country}:${c.name}`;
    const notForMeCount = (c.not_for_me_jobs || c.hidden_jobs || []).length;
    const showingNotForMe = state.showNotForMeCompanies.has(companyKeyStr);
    const notForMeBtn = notForMeCount > 0
      ? `<button type="button" class="show-not-for-me-btn${showingNotForMe ? " active" : ""}" data-company-key="${escapeAttr(companyKeyStr)}" title="Show jobs marked Not for me">${showingNotForMe ? "Hide not for me jobs" : `Show ${notForMeCount} not for me job${notForMeCount === 1 ? "" : "s"}`}</button>`
      : "";
    const notForMeHtml = showingNotForMe && notForMeCount > 0
      ? `<div class="not-for-me-jobs-heading">Not for me jobs</div>${sortJobsForDisplay(c.not_for_me_jobs || c.hidden_jobs || []).map(renderNotForMeJob).join("")}`
      : "";
    const rejectionsOnly = $("positionRejectedOnly")?.checked;
    const showingRejected = state.showRejectedCompanies.has(companyKeyStr) || rejectionsOnly;
    const rejectedBtn = rejectedCount > 0
      ? `<button type="button" class="show-rejected-btn${showingRejected ? " active" : ""}" data-company-key="${escapeAttr(companyKeyStr)}" title="Show jobs marked rejected">${showingRejected ? "Hide rejected jobs" : `Show ${rejectedCount} rejected job${rejectedCount === 1 ? "" : "s"}`}</button>`
      : "";
    const rejectedHtml = showingRejected && rejectedCount > 0
      ? `<div class="rejected-jobs-heading">Rejected jobs</div>${sortJobsForDisplay(c.rejected_jobs || []).map(renderRejectedJob).join("")}`
      : "";
    const countLabel = c.job_count === 1 ? "1 role" : `${c.job_count} roles`;
    const appliedCount = c.positions_applied_all ?? c.positions_applied ?? 0;
    const appliedBadge = c.company_applied
      ? `<span class="badge applied">${
          appliedCount > 1
            ? `${appliedCount} roles applied`
            : escapeHtml(formatAppliedLabel({
                date: c.company_applied_date || "",
                at: c.company_applied_at || "",
              }))
        }</span>`
      : "";
    const awaitingBadge = c.awaiting_response
      ? `<span class="badge awaiting-response">Awaiting response${c.awaiting_response_date ? ` · ${escapeHtml(c.awaiting_response_date)}` : ""}</span>`
      : "";
    const awaitingResponseBtn = c.awaiting_response
      ? `<button type="button" class="awaiting-response-btn active" data-awaiting="1" title="Clear awaiting-response mark">Awaiting response${c.awaiting_response_date ? ` · ${escapeHtml(c.awaiting_response_date)}` : ""}</button>`
      : `<button type="button" class="awaiting-response-btn" data-awaiting="0" title="Waiting on application response(s) before applying to other roles here">Awaiting response</button>`;
    const isFetching = state.fetchingCompanyKey === companyKeyStr;
    const isCollapsed = state.collapsedCompanies.has(companyKeyStr);
    const cityLabels = companyLocationLabels(c);
    const cityDisplay = formatCompanyCities(c);
    const locationPayload = Array.isArray(c.locations) && c.locations.length
      ? c.locations
      : cityLabels.map((city) => ({ city }));
    return `
      <article class="company-card${companyCls}${isCollapsed ? " collapsed" : ""}" data-country="${escapeAttr(c.country)}" data-company="${escapeAttr(c.name)}">
        <div class="company-header">
          <div>
            <div class="company-name-row">
              <div class="company-name">${escapeHtml(c.name)}</div>
              <button type="button" class="edit-name-btn" data-country="${escapeAttr(c.country)}" data-country-label="${escapeAttr(c.country_label || "")}" data-company="${escapeAttr(c.name)}" title="Rename this company">Rename</button>
            </div>
            <div class="company-meta">
              <button type="button" class="edit-city-btn" data-country="${escapeAttr(c.country)}" data-country-label="${escapeAttr(c.country_label || "")}" data-company="${escapeAttr(c.name)}" data-locations="${escapeAttr(JSON.stringify(locationPayload))}" data-has-cities="${cityLabels.length ? "true" : "false"}" title="Set or change company locations">${escapeHtml(cityDisplay)}</button>
              <span>${escapeHtml(c.country_label)}</span>
              <span>${escapeHtml(countLabel)}</span>
            </div>
            ${careers}
            <div class="company-toolbar">
              ${awaitingResponseBtn}
              ${notForMeBtn}
              ${rejectedBtn}
              ${state.scrapeConfig.scrape_enabled !== false ? `<button type="button" class="fetch-company-btn" data-country="${escapeAttr(c.country)}" data-company="${escapeAttr(c.name)}" ${state.serverFetchRunning ? "disabled" : ""}>${isFetching ? "Fetching…" : "Fetch jobs"}</button>` : ""}
              <button type="button" class="remove-company-btn" data-country="${escapeAttr(c.country)}" data-company="${escapeAttr(c.name)}" title="Remove this company from the list">Remove</button>
            </div>
          </div>
          <div class="company-header-side">
            <button type="button" class="collapse-company-btn" title="Hide or show roles under this company">${isCollapsed ? "Show positions" : "Hide positions"}</button>
            <span class="badge country">${escapeHtml(c.country_label)}</span>
            ${appliedBadge}
            ${awaitingBadge}
            <span class="badge date">${escapeHtml(formatActivityBadge(companyActivityTs(c)))}</span>
          </div>
        </div>
        <div class="positions">${jobsHtml || `<div class="position-card"><span class="job-meta">${emptyMsg}</span></div>`}${rejectedHtml}${notForMeHtml}</div>
      </article>
    `;
  }).join("");
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
  const company = state.allCompanies.find((c) => companySortKey(c) === companyKey);
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
    renderCompanies();
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
  renderCompanies();
}

export function updateFetchHeaderUI() {
  const fetchBtn = $("fetchCountryBtn");
  const chip = $("fetchProgressChip");
  const meta = $("fetchProgressChipMeta");
  const fill = $("fetchProgressChipFill");
  if (!fetchBtn || !chip) return;

  const controlsEnabled = Boolean(state.fetchControlsEnabled);
  const active = state.serverFetchRunning || state.countryFetchActive || state.fetchBusy;

  if (!controlsEnabled) {
    fetchBtn.hidden = true;
    chip.hidden = true;
    return;
  }

  if (!active) {
    fetchBtn.hidden = false;
    chip.hidden = true;
    fetchBtn.title = "Fetch jobs for the selected country and ATS filter";
    return;
  }

  fetchBtn.hidden = true;
  chip.hidden = false;

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

  if (meta) meta.textContent = metaText;
  if (fill) fill.style.width = `${Math.max(4, pct)}%`;
  chip.title = chipTitle;
  chip.setAttribute("aria-label", chipTitle);
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

function fetchReviewEl(id) {
  return document.getElementById(id);
}

const JUNK_REVIEW_TITLE = /^(show\s+\d+\s+more|load\s+more|view\s+all(\s+jobs)?|see\s+all(\s+jobs)?)$/i;
const JUNK_REVIEW_URL = /\/jobs\/show_more\b/i;

function isJunkReviewJob(title, url) {
  const t = (title || "").trim();
  const u = (url || "").trim();
  return JUNK_REVIEW_URL.test(u) || JUNK_REVIEW_TITLE.test(t);
}

function normalizeReviewJobs(jobs) {
  const seen = new Set();
  const out = [];
  for (const job of jobs || []) {
    const url = String(job?.url || "").trim();
    if (!url || seen.has(url)) continue;
    const title = String(job?.title || "").trim();
    if (isJunkReviewJob(title, url)) continue;
    seen.add(url);
    out.push({
      title: title || url,
      url,
      filter_reason: String(job?.filter_reason || "").trim(),
    });
  }
  return out;
}

const FETCH_REVIEW_LIST_PREVIEW = 10;

function renderFilteredReviewList(filteredList, filtered, { expanded = false } = {}) {
  if (!filteredList) return;

  const showAll = expanded || filtered.length <= FETCH_REVIEW_LIST_PREVIEW;
  const visible = showAll ? filtered : filtered.slice(0, FETCH_REVIEW_LIST_PREVIEW);
  const hiddenCount = Math.max(0, filtered.length - visible.length);
  const expandBtn = fetchReviewEl("fetchReviewExpandBtn");

  filteredList.innerHTML = visible.map((job, idx) => `
    <li class="fetch-review-item">
      <label>
        <input type="checkbox" class="fetch-review-check" data-idx="${idx}" />
        <span class="fetch-review-item-body">
          ${renderReviewJobLink(job)}
          ${renderReviewJobReason(job)}
        </span>
      </label>
    </li>`).join("");
  filteredList._jobs = filtered;
  filteredList.dataset.expanded = showAll ? "1" : "0";

  if (!expandBtn) return;
  if (hiddenCount > 0) {
    expandBtn.hidden = false;
    expandBtn.textContent = `Show ${hiddenCount} more`;
  } else if (showAll && filtered.length > FETCH_REVIEW_LIST_PREVIEW) {
    expandBtn.hidden = false;
    expandBtn.textContent = "Show less";
  } else {
    expandBtn.hidden = true;
    expandBtn.textContent = "";
  }
}

export function toggleFetchReviewFilteredExpanded() {
  const filteredList = fetchReviewEl("fetchReviewFilteredList");
  if (!filteredList?._jobs?.length) return;
  const expanded = filteredList.dataset.expanded !== "1";
  renderFilteredReviewList(filteredList, filteredList._jobs, { expanded });
}

function renderReviewJobLink(job) {
  const title = escapeHtml(job.title || job.url || "Untitled role");
  const url = escapeAttr(job.url || "#");
  return `<a href="${url}" target="_blank" rel="noopener">${title}</a>`;
}

function renderReviewJobReason(job) {
  const reason = (job.filter_reason || "").trim();
  if (!reason) return "";
  return `<span class="fetch-review-reason">${escapeHtml(reason)}</span>`;
}

function hideFetchReviewFooter() {
  const footer = fetchReviewEl("fetchPanelFooter");
  const feedbackWrap = fetchReviewEl("fetchReviewFeedback");
  if (footer) footer.hidden = true;
  if (feedbackWrap) feedbackWrap.classList.remove("is-pending", "is-resolved");
}

export function clearFetchReviewContent() {
  const reviewEl = fetchReviewEl("fetchReview");
  if (reviewEl) reviewEl.hidden = true;
  const log = fetchReviewEl("fetchLog");
  if (log) log.hidden = false;
  const included = fetchReviewEl("fetchReviewIncluded");
  const includedList = fetchReviewEl("fetchReviewIncludedList");
  const filteredList = fetchReviewEl("fetchReviewFilteredList");
  const filteredTitle = fetchReviewEl("fetchReviewFilteredTitle");
  const includedTitle = fetchReviewEl("fetchReviewIncludedTitle");
  const hint = fetchReviewEl("fetchReviewHint");
  const addBtn = fetchReviewEl("fetchReviewAddBtn");
  const expandBtn = fetchReviewEl("fetchReviewExpandBtn");
  if (included) included.hidden = true;
  if (addBtn) addBtn.hidden = true;
  if (expandBtn) {
    expandBtn.hidden = true;
    expandBtn.textContent = "";
  }
  if (filteredTitle) filteredTitle.textContent = "Filtered out";
  if (includedTitle) includedTitle.textContent = "Matched";
  if (hint) {
    hint.textContent = "Roles on the careers page that did not match your filters. Select any to add manually.";
  }
  if (includedList) includedList.innerHTML = "";
  if (filteredList) {
    filteredList.innerHTML = "";
    delete filteredList.dataset.expanded;
    delete filteredList._jobs;
  }
}

export function clearFetchReview() {
  clearFetchReviewContent();
  hideFetchReviewFooter();
  resetFetchReviewFeedbackPrompt();
  state.fetchReviewFeedback = null;
}

const FETCH_REVIEW_OK_ICON = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" aria-hidden="true"><path d="M20 6 9 17l-5-5"/></svg>`;
const FETCH_REVIEW_PROBLEM_ICON = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg>`;

export function setFetchReviewFeedbackDone(status) {
  const feedbackWrap = fetchReviewEl("fetchReviewFeedback");
  const feedbackPrompt = fetchReviewEl("fetchReviewFeedbackPrompt");
  const feedbackResult = fetchReviewEl("fetchReviewFeedbackResult");
  if (feedbackWrap) {
    feedbackWrap.classList.remove("is-pending");
    feedbackWrap.classList.add("is-resolved");
  }
  if (feedbackPrompt) {
    feedbackPrompt.hidden = true;
    feedbackPrompt.setAttribute("aria-hidden", "true");
  }
  if (!feedbackResult) return;
  const isOk = status === "ok";
  feedbackResult.className = `fetch-review-feedback-result is-${isOk ? "ok" : "problem"}`;
  feedbackResult.innerHTML = `
    <span class="fetch-review-feedback-icon" aria-hidden="true">${isOk ? FETCH_REVIEW_OK_ICON : FETCH_REVIEW_PROBLEM_ICON}</span>
    <span class="fetch-review-feedback-text">${isOk ? "Fetch confirmed OK" : "Marked as fetch problem"}</span>
  `;
  feedbackResult.hidden = false;
  feedbackResult.removeAttribute("aria-hidden");
}

function resetFetchReviewFeedbackPrompt(prompt = "Did the fetch work correctly?") {
  const feedbackWrap = fetchReviewEl("fetchReviewFeedback");
  const feedbackLabel = fetchReviewEl("fetchReviewFeedbackLabel");
  const feedbackPrompt = fetchReviewEl("fetchReviewFeedbackPrompt");
  const feedbackResult = fetchReviewEl("fetchReviewFeedbackResult");
  const okBtn = fetchReviewEl("fetchReviewOkBtn");
  const problemBtn = fetchReviewEl("fetchReviewProblemBtn");
  if (feedbackWrap) feedbackWrap.classList.remove("is-resolved", "is-pending");
  if (feedbackLabel) feedbackLabel.textContent = prompt;
  if (feedbackPrompt) {
    feedbackPrompt.hidden = false;
    feedbackPrompt.removeAttribute("aria-hidden");
  }
  if (feedbackResult) {
    feedbackResult.hidden = true;
    feedbackResult.setAttribute("aria-hidden", "true");
    feedbackResult.innerHTML = "";
    feedbackResult.className = "fetch-review-feedback-result";
  }
  if (okBtn) okBtn.disabled = false;
  if (problemBtn) problemBtn.disabled = false;
}

function applyStoredFetchReviewFeedback(country, company) {
  const saved = state.fetchReviewFeedback;
  if (saved?.country === country && saved?.company === company && saved?.status) {
    setFetchReviewFeedbackDone(saved.status);
    return true;
  }
  return false;
}

function setFetchReviewAddVisible(visible) {
  const addBtn = fetchReviewEl("fetchReviewAddBtn");
  if (addBtn) addBtn.hidden = !visible;
}

function setFetchReviewFooterButtons(country, company) {
  const okBtn = fetchReviewEl("fetchReviewOkBtn");
  const problemBtn = fetchReviewEl("fetchReviewProblemBtn");
  if (okBtn) {
    okBtn.dataset.country = country || "";
    okBtn.dataset.company = company || "";
    okBtn.disabled = false;
  }
  if (problemBtn) {
    problemBtn.dataset.country = country || "";
    problemBtn.dataset.company = company || "";
    problemBtn.disabled = false;
  }
}

export function setFetchReviewFooterPending({ country, company, prompt = "Fetch in progress…" } = {}) {
  const footer = fetchReviewEl("fetchPanelFooter");
  const feedbackWrap = fetchReviewEl("fetchReviewFeedback");
  const feedbackLabel = fetchReviewEl("fetchReviewFeedbackLabel");
  const feedbackPrompt = fetchReviewEl("fetchReviewFeedbackPrompt");
  const feedbackResult = fetchReviewEl("fetchReviewFeedbackResult");
  if (!footer || !feedbackWrap) return;

  footer.hidden = false;
  feedbackWrap.classList.add("is-pending");
  feedbackWrap.classList.remove("is-resolved");
  if (feedbackLabel) feedbackLabel.textContent = prompt;
  if (feedbackPrompt) {
    feedbackPrompt.hidden = false;
    feedbackPrompt.removeAttribute("aria-hidden");
  }
  if (feedbackResult) {
    feedbackResult.hidden = true;
    feedbackResult.setAttribute("aria-hidden", "true");
    feedbackResult.innerHTML = "";
    feedbackResult.className = "fetch-review-feedback-result";
  }
  setFetchReviewFooterButtons(country, company);
}

function updateFetchReviewFooter({ country, company, showFeedback = false, prompt } = {}) {
  const footer = fetchReviewEl("fetchPanelFooter");
  const feedbackWrap = fetchReviewEl("fetchReviewFeedback");
  if (!feedbackWrap) return;

  if (!showFeedback) {
    hideFetchReviewFooter();
    return;
  }

  if (footer) footer.hidden = false;
  feedbackWrap.classList.remove("is-pending");

  setFetchReviewFooterButtons(country, company);

  if (!applyStoredFetchReviewFeedback(country, company)) {
    resetFetchReviewFeedbackPrompt(prompt);
  }
}

export function showFetchReviewFeedback({ country, company, failed = false } = {}) {
  if (!country || !company) {
    clearFetchReview();
    return;
  }
  const reviewEl = fetchReviewEl("fetchReview");
  const log = fetchReviewEl("fetchLog");
  if (reviewEl) reviewEl.hidden = false;
  if (log) log.hidden = true;
  setFetchReviewAddVisible(false);
  updateFetchReviewFooter({
    country,
    company,
    showFeedback: true,
    prompt: failed
      ? "Fetch finished with errors. Did it load roles correctly?"
      : "Did the fetch work correctly?",
  });
}

export function renderFetchReview(review, { country, company, missingReview = false } = {}) {
  const reviewEl = fetchReviewEl("fetchReview");
  if (!reviewEl || !country || !company) {
    clearFetchReview();
    return;
  }

  const included = normalizeReviewJobs(review?.included);
  const filtered = normalizeReviewJobs(review?.filtered);

  reviewEl.hidden = false;
  const log = fetchReviewEl("fetchLog");
  if (log) log.hidden = true;

  const hint = fetchReviewEl("fetchReviewHint");
  const includedSection = fetchReviewEl("fetchReviewIncluded");
  const includedList = fetchReviewEl("fetchReviewIncludedList");
  const includedTitle = fetchReviewEl("fetchReviewIncludedTitle");
  const filteredTitle = fetchReviewEl("fetchReviewFilteredTitle");
  const filteredList = fetchReviewEl("fetchReviewFilteredList");
  const addBtn = fetchReviewEl("fetchReviewAddBtn");

  if (missingReview) {
    if (hint) {
      hint.textContent = "Role review is unavailable. Restart the panel server, then fetch again.";
    }
    if (includedSection) includedSection.hidden = true;
    if (filteredTitle) filteredTitle.textContent = "Filtered out";
    if (filteredList) {
      filteredList.innerHTML = `<li class="fetch-review-item"><span class="job-meta">No review data</span></li>`;
    }
    setFetchReviewAddVisible(false);
    updateFetchReviewFooter({ country, company, showFeedback: true });
    return;
  }

  if (!included.length && !filtered.length) {
    if (hint) {
      const co = findCompany(country, company);
      const ats = (co?.ats_type || "").trim();
      hint.textContent = ats && ats !== "generic"
        ? `No matching roles found using the ${ats} board. The page may be empty or your filters are strict.`
        : "No roles could be loaded. The ATS is likely misdetected (not generic) — use Edit URL or mark a fetch problem.";
    }
    if (includedSection) includedSection.hidden = true;
    if (filteredTitle) filteredTitle.textContent = "Filtered out (0)";
    if (filteredList) {
      filteredList.innerHTML = `<li class="fetch-review-item"><span class="job-meta">None found</span></li>`;
    }
    setFetchReviewAddVisible(false);
    updateFetchReviewFooter({ country, company, showFeedback: true });
    return;
  }

  if (hint) {
    hint.textContent = filtered.length
      ? "These roles were on the careers page but did not match your filters. Each line shows why. Select any to add manually."
      : "All roles on the careers page matched your filters.";
  }

  if (filteredTitle) filteredTitle.textContent = `Filtered out (${filtered.length})`;
  if (filtered.length && filteredList) {
    const expanded = filteredList.dataset.expanded === "1";
    renderFilteredReviewList(filteredList, filtered, { expanded });
    filteredList.dataset.country = country;
    filteredList.dataset.company = company;
    if (addBtn) {
      addBtn.disabled = false;
      addBtn.hidden = false;
    }
  } else {
    setFetchReviewAddVisible(false);
    if (filteredList) {
      filteredList.innerHTML = `<li class="fetch-review-item"><span class="job-meta">None</span></li>`;
    }
  }

  if (included.length) {
    if (includedSection) includedSection.hidden = false;
    if (includedTitle) includedTitle.textContent = `Matched (${included.length})`;
    if (includedList) {
      includedList.innerHTML = included.map((job) => `
        <li class="fetch-review-item">${renderReviewJobLink(job)}</li>`).join("");
    }
  } else if (includedSection) {
    includedSection.hidden = true;
    if (includedList) includedList.innerHTML = "";
  }

  updateFetchReviewFooter({
    country,
    company,
    showFeedback: true,
  });
}

export function setFetchLogMode(singleCompany) {
  const logEl = $("fetchLog");
  if (!logEl) return;
  logEl.classList.toggle("fetch-log-active", Boolean(singleCompany));
}

export function openFetchPanel() {
  const backdrop = $("fetchPanelBackdrop");
  backdrop.classList.add("open");
  backdrop.setAttribute("aria-hidden", "false");
  document.body.classList.add("fetch-modal-open");
}

export function showFetchPanel({ title, subtitle, singleCompany = false, country = null, company = null, reopen = false } = {}) {
  openFetchPanel();

  if (reopen) {
    state.fetchPanelSingle = Boolean(singleCompany);
    $("fetchCancelBtn").hidden = false;
    $("fetchCancelBtn").disabled = false;
    $("fetchCancelBtn").textContent = "Cancel";
    $("fetchCloseBtn").hidden = false;
    return;
  }

  state.fetchPanelSingle = Boolean(singleCompany);
  clearFetchReviewContent();
  hideFetchReviewFooter();
  state.fetchReviewFeedback = null;
  $("fetchTitle").textContent = title || "Fetching companies";
  $("fetchSubtitle").textContent = subtitle || "Starting…";
  const logEl = $("fetchLog");
  const activityEl = $("fetchActivity");
  logEl.hidden = singleCompany;
  logEl.textContent = singleCompany ? "Waiting for scrape to start…\n" : "Starting…\n";
  if (activityEl) {
    activityEl.hidden = !singleCompany;
    const stepEl = $("fetchActivityStep");
    const detailEl = $("fetchActivityDetail");
    const listEl = $("fetchActivityLog");
    if (stepEl) stepEl.textContent = "Starting…";
    if (detailEl) {
      detailEl.textContent = "";
      detailEl.hidden = true;
    }
    if (listEl) listEl.innerHTML = "";
  }
  setFetchLogMode(singleCompany);
  $("fetchCancelBtn").hidden = false;
  $("fetchCancelBtn").disabled = false;
  $("fetchCancelBtn").textContent = "Cancel";
  $("fetchCancelBtn").title = singleCompany
    ? "Stop this fetch immediately"
    : "Stop fetching remaining companies";
  $("fetchCloseBtn").hidden = false;

  const progressWrap = $("fetchProgressWrap");
  if (singleCompany) {
    progressWrap.hidden = true;
    if (country && company) {
      setFetchReviewFooterPending({ country, company });
    }
  } else {
    progressWrap.hidden = false;
    updateFetchProgress({ current: 0, total: 0, company: null, running: true });
  }
}

export function hideFetchPanel() {
  const backdrop = $("fetchPanelBackdrop");
  backdrop.classList.remove("open");
  backdrop.setAttribute("aria-hidden", "true");
  document.body.classList.remove("fetch-modal-open");
  clearFetchReview();
  updateFetchHeaderUI();
}

export function updateFetchProgress({
  current = 0,
  total = 0,
  company = null,
  status = "",
  running = false,
  cancelled = false,
  newJobsTotal = 0,
}) {
  const progressWrap = $("fetchProgressWrap");
  progressWrap.hidden = false;

  const safeTotal = Math.max(0, total || 0);
  const safeCurrent = Math.max(0, current || 0);
  const displayCurrent =
    running && status === "fetching" && safeTotal > 1 && safeCurrent < safeTotal
      ? safeCurrent + 1
      : safeCurrent;
  const pct = safeTotal > 0
    ? (running && status !== "done"
        ? Math.min(99, Math.round((displayCurrent / safeTotal) * 100))
        : Math.min(100, Math.round((displayCurrent / safeTotal) * 100)))
    : (running ? 0 : (cancelled ? safeCurrent : 100));

  const newJobs = Math.max(0, Number(newJobsTotal) || 0);
  const newJobsSuffix = newJobs > 0 ? ` · ${newJobs} new` : "";
  $("fetchProgressLabel").textContent = safeTotal > 0
    ? `${safeCurrent} / ${safeTotal} companies${newJobsSuffix}`
    : (running ? "Preparing…" : (newJobs > 0 ? `${newJobs} new roles` : "Done"));
  $("fetchProgressPct").textContent = `${pct}%`;
  $("fetchProgressBar").style.width = `${pct}%`;
  $("fetchProgressTrack").setAttribute("aria-valuenow", String(pct));

  const companyEl = $("fetchCurrentCompany");
  if (company && status === "fetching") {
    companyEl.textContent = `Fetching: ${company}`;
  } else if (company && status === "done") {
    companyEl.textContent = `Completed: ${company}`;
  } else if (status === "saving") {
    companyEl.textContent = "Saving to database…";
  } else if (company) {
    companyEl.textContent = company;
  } else if (running) {
    companyEl.textContent = safeTotal > 0 ? "Waiting for next company…" : "";
  } else if (cancelled) {
    companyEl.textContent = "Stopped — progress saved for completed companies.";
  } else {
    companyEl.textContent = "";
  }
}

export function setFetchPanelRunning(running) {
  $("fetchCancelBtn").hidden = !running;
  if (!running) {
    $("fetchCancelBtn").disabled = false;
    $("fetchCancelBtn").textContent = "Cancel";
  }
}

export function hideFetchCompletion() {
  const el = $("fetchCompletion");
  if (el) el.hidden = true;
}

export function updateFetchRunMeta(st, { running = false, fetchRun = null } = {}) {
  const wrap = $("fetchCompletion");
  const labelEl = $("fetchCompletionLabel");
  if (!wrap) return;

  const startedAt = fetchRun?.started_at || st?.started_at || "";
  if (!startedAt && !fetchRun) {
    hideFetchCompletion();
    return;
  }

  wrap.hidden = false;
  if (labelEl) labelEl.textContent = running ? "Current run" : "Last run";

  const startedEl = $("fetchCompletionStarted");
  const finishedEl = $("fetchCompletionFinished");
  const durationEl = $("fetchCompletionDuration");
  const newJobsEl = $("fetchCompletionNewJobs");

  if (startedEl) startedEl.textContent = formatActivityBadge(startedAt);

  const newJobs = Math.max(
    0,
    Number(fetchRun?.new_jobs ?? st?.new_jobs_total) || 0,
  );
  if (newJobsEl) {
    newJobsEl.textContent = newJobs === 1 ? "1 role" : `${newJobs} roles`;
  }

  if (running) {
    if (finishedEl) finishedEl.textContent = "In progress…";
    const elapsed = elapsedSecondsSince(startedAt);
    if (durationEl) {
      durationEl.textContent = elapsed != null ? formatFetchDuration(elapsed) : "—";
    }
    return;
  }

  const finishedAt = fetchRun?.finished_at || st?.finished_at || "";
  if (finishedEl) {
    finishedEl.textContent = finishedAt
      ? formatActivityBadge(finishedAt)
      : "—";
  }
  const duration = fetchRun?.duration_seconds
    ?? elapsedSecondsBetween(startedAt, finishedAt)
    ?? null;
  if (durationEl) {
    durationEl.textContent = duration != null ? formatFetchDuration(duration) : "—";
  }
}

export function showFetchCompletion(run) {
  updateFetchRunMeta(null, { running: false, fetchRun: run });
}

export function finishFetchPanel({
  title,
  subtitle,
  cancelled = false,
  failed = false,
  singleCompany = false,
  fetchRun = null,
  fetchStatus = null,
}) {
  $("fetchTitle").textContent = title || (cancelled ? "Fetch cancelled" : "Fetch complete");
  $("fetchSubtitle").textContent = subtitle || "";
  updateFetchRunMeta(fetchStatus, { running: false, fetchRun });
  setFetchPanelRunning(false);
  state.fetchPanelSingle = false;
  setFetchLogMode(false);
  $("fetchProgressWrap").hidden = singleCompany;
  if (cancelled) {
    $("fetchCurrentCompany").textContent = "Stopped — progress saved for completed companies.";
  }
  if (failed && !cancelled) {
    $("fetchSubtitle").textContent = subtitle || "Check the log for details.";
  }
}

export function appendFetchLog(lines) {
  const log = $("fetchLog");
  log.textContent = lines;
  log.scrollTop = log.scrollHeight;
}

export function updateFetchActivity(st) {
  const wrap = $("fetchActivity");
  const stepEl = $("fetchActivityStep");
  const detailEl = $("fetchActivityDetail");
  const listEl = $("fetchActivityLog");
  if (!wrap) return;

  if (!st?.running) {
    wrap.hidden = true;
    return;
  }

  wrap.hidden = false;
  const current = st.activity || {};
  const history = Array.isArray(st.activity_log) ? st.activity_log : [];
  const message = (current.message || "").trim() || "Working…";
  const detail = (current.detail || "").trim();

  if (stepEl) stepEl.textContent = message;
  if (detailEl) {
    detailEl.textContent = detail;
    detailEl.hidden = !detail;
  }
  if (listEl) {
    const items = history.length ? history : [{ message, detail }];
    listEl.innerHTML = items.slice(-6).map((entry) => {
      const msg = escapeHtml((entry.message || "").trim());
      const meta = (entry.detail || "").trim();
      return `<li><span class="fetch-activity-log-text">${msg}</span>${
        meta ? `<span class="fetch-activity-log-meta">${escapeHtml(meta)}</span>` : ""
      }</li>`;
    }).join("");
  }
}
