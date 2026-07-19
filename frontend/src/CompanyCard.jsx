import { memo, useEffect, useRef, useState } from "react";
import { companyWorkspacePath } from "./companyWorkspace";
import { companyActivityTs, formatActivityBadge, formatAppliedLabel } from "./format";
import { sortJobsForDisplay } from "./sort";
import JobCard from "./JobCard";

const MOBILE_BOARD_MQ = "(max-width: 720px)";
const ROLE_PREVIEW_LIMIT = 3;

function companyKey(company) {
  return `${company.country}:${company.name}`;
}

function useMobileBoard() {
  const [isMobile, setIsMobile] = useState(() =>
    typeof window !== "undefined" ? window.matchMedia(MOBILE_BOARD_MQ).matches : false,
  );
  useEffect(() => {
    const mq = window.matchMedia(MOBILE_BOARD_MQ);
    const sync = () => setIsMobile(mq.matches);
    sync();
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, []);
  return isMobile;
}

function prefersReducedMotion() {
  return typeof window !== "undefined"
    && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function formatCompactDateTime(value) {
  const match = String(value || "").match(/^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}:\d{2}))?/);
  if (!match) return value || "";
  const month = new Intl.DateTimeFormat("en", { month: "short", timeZone: "UTC" })
    .format(new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, 1)));
  return `${month} ${Number(match[3])}${match[4] ? ` · ${match[4]}` : ""}`;
}

/** Slice a job list for mobile preview; returns visible jobs + hidden count. */
function previewJobs(jobs, { isMobile, expanded }) {
  if (!isMobile || expanded || jobs.length <= ROLE_PREVIEW_LIMIT) {
    return { visible: jobs, hiddenCount: 0 };
  }
  return {
    visible: jobs.slice(0, ROLE_PREVIEW_LIMIT),
    hiddenCount: jobs.length - ROLE_PREVIEW_LIMIT,
  };
}

function ExpandRolesBtn({ hiddenCount, expanded, onExpand, onCollapse }) {
  if (expanded) {
    return (
      <button
        type="button"
        className="expand-roles-btn"
        onClick={onCollapse}
        title="Show fewer roles"
      >
        Show less
      </button>
    );
  }
  if (hiddenCount <= 0) return null;
  return (
    <button
      type="button"
      className="expand-roles-btn"
      onClick={onExpand}
      title={`Show ${hiddenCount} more role${hiddenCount === 1 ? "" : "s"}`}
    >
      {`Show ${hiddenCount} more role${hiddenCount === 1 ? "" : "s"}`}
    </button>
  );
}

const CITY_SEP = " · ";

function splitLocationText(text) {
  const trimmed = (text || "").trim();
  if (!trimmed) return [];
  if (trimmed.includes(CITY_SEP)) {
    return trimmed.split(CITY_SEP).map((part) => part.trim()).filter(Boolean);
  }
  return trimmed.split(",").map((part) => part.trim()).filter(Boolean);
}

function flattenJoinedLabels(labels) {
  const out = [];
  for (const label of labels) {
    const parts = splitLocationText(label);
    if (parts.length) out.push(...parts);
  }
  return out;
}

function dedupeLocationLabels(labels) {
  const seen = new Set();
  const out = [];
  for (const label of labels) {
    const trimmed = (label || "").trim();
    if (!trimmed) continue;
    const key = trimmed.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(trimmed);
  }
  return out;
}

function companyLocationLabels(company) {
  if (Array.isArray(company.locations) && company.locations.length) {
    const labels = company.locations.map(
      (loc) => loc.label || `${loc.city} (${loc.country_label || loc.country})`,
    );
    return dedupeLocationLabels(flattenJoinedLabels(labels));
  }
  if (Array.isArray(company.cities) && company.cities.length) {
    const labels = dedupeLocationLabels(flattenJoinedLabels(company.cities));
    if (labels.length) return labels;
  }
  return dedupeLocationLabels(splitLocationText(company.city));
}

const CITY_PREVIEW_LIMIT = 3;

function formatCityLabels(labels, { expanded = false } = {}) {
  if (!labels.length) return { text: "Set locations", truncated: false, hiddenCount: 0 };
  if (expanded || labels.length <= CITY_PREVIEW_LIMIT) {
    return { text: labels.join(" · "), truncated: false, hiddenCount: 0 };
  }
  return {
    text: labels.slice(0, CITY_PREVIEW_LIMIT).join(" · "),
    truncated: true,
    hiddenCount: labels.length - CITY_PREVIEW_LIMIT,
  };
}

function emptyMessage(company, ui) {
  const rejectedCount = (company.rejected_jobs || []).length;
  if (company.job_count !== 0) return "No matching roles (try turning off visa filter).";
  if (company.stored_job_count > 0) {
    if (company.positions_not_for_me >= company.stored_job_count) {
      return "All roles marked not for me — click Show not for me jobs below.";
    }
    if (rejectedCount >= company.stored_job_count) {
      return "All roles marked rejected — click Show rejected jobs below.";
    }
    if (company.positions_hidden_by_visa > 0 && ui.visaOnly) {
      return "No visa / relocation roles in cache for this company.";
    }
    return "No roles match your current filters.";
  }
  return "No jobs yet — click Fetch jobs.";
}

function CompanyCard({ company, ui }) {
  const cardRef = useRef(null);
  const [citiesExpanded, setCitiesExpanded] = useState(false);
  const [rolesExpanded, setRolesExpanded] = useState(false);
  const isMobile = useMobileBoard();
  const keyStr = companyKey(company);
  const collapsedSet = new Set(ui.collapsed || []);
  const showNotForMeSet = new Set(ui.showNotForMe || []);
  const showRejectedSet = new Set(ui.showRejected || []);
  const isCollapsed = collapsedSet.has(keyStr);
  const companyCls = [
    company.company_applied ? " company-applied" : "",
    company.awaiting_response ? " company-awaiting-response" : "",
    company.fetch_problem ? " fetch-problem" : "",
    company.fetch_ok && !company.fetch_problem ? " fetch-ok" : "",
  ].join("");
  const cityLabels = companyLocationLabels(company);
  const cityDisplay = formatCityLabels(cityLabels, { expanded: citiesExpanded });
  const locationPayload = Array.isArray(company.locations) && company.locations.length
    ? company.locations
    : cityLabels.map((city) => ({ city }));
  const notForMeJobs = company.not_for_me_jobs || company.hidden_jobs || [];
  const notForMeCount = notForMeJobs.length;
  const rejectedJobs = sortJobsForDisplay(company.rejected_jobs || []);
  const rejectedCount = rejectedJobs.length;
  const showingNotForMe = showNotForMeSet.has(keyStr);
  const showingRejected = showRejectedSet.has(keyStr) || ui.positionRejectedOnly;
  const isFetching = ui.fetchingCompanyKey === keyStr;
  const countLabel = company.job_count === 1 ? "1 role" : `${company.job_count} roles`;
  const appliedCount = company.positions_applied_all ?? company.positions_applied ?? 0;
  const companyAppliedAt = formatAppliedLabel({
    date: company.company_applied_date || "",
    at: company.company_applied_at || "",
  }).replace(/^Applied\s*·?\s*/, "");
  const companyAppliedAtCompact = formatCompactDateTime(
    company.company_applied_date || companyAppliedAt,
  );
  const openJobs = sortJobsForDisplay(company.jobs || []);
  const sortedNotForMe = sortJobsForDisplay(notForMeJobs);
  const openPreview = previewJobs(openJobs, { isMobile, expanded: rolesExpanded });
  const rejectedPreview = previewJobs(rejectedJobs, { isMobile, expanded: rolesExpanded });
  const notForMePreview = previewJobs(sortedNotForMe, { isMobile, expanded: rolesExpanded });
  const rolesTruncatable = isMobile && (
    openJobs.length > ROLE_PREVIEW_LIMIT
    || (showingRejected && rejectedJobs.length > ROLE_PREVIEW_LIMIT)
    || (showingNotForMe && sortedNotForMe.length > ROLE_PREVIEW_LIMIT)
  );
  const rolesHiddenCount = openPreview.hiddenCount
    + (showingRejected ? rejectedPreview.hiddenCount : 0)
    + (showingNotForMe ? notForMePreview.hiddenCount : 0);
  const workspaceHref = companyWorkspacePath(company.country, company.name);
  const tailoredCount = openJobs.filter(
    (job) => job.has_pdf || job.has_tailored_tex || job.has_cover_letter_pdf || job.has_cover_letter_tex,
  ).length;

  const collapseRolesPreview = () => {
    setRolesExpanded(false);
    const el = cardRef.current;
    if (!el) return;
    el.scrollIntoView({
      block: "nearest",
      behavior: prefersReducedMotion() ? "auto" : "smooth",
    });
  };

  return (
    <article
      ref={cardRef}
      className={`company-card${companyCls}${isCollapsed ? " collapsed" : ""}`}
      data-country={company.country}
      data-company={company.name}
    >
      <div className="company-header">
        <div className="company-header-main">
          <div className="company-name-row">
            <a className="company-name company-name-link" href={workspaceHref} title="Open application workspace">
              {company.name}
            </a>
          </div>
          <div className="company-meta">
            <div className="company-locations-wrap">
              <button
                type="button"
                className="edit-city-btn"
                data-country={company.country}
                data-country-label={company.country_label || ""}
                data-company={company.name}
                data-locations={JSON.stringify(locationPayload)}
                data-has-cities={cityLabels.length ? "true" : "false"}
                title="Set or change company locations"
              >
                {cityDisplay.text}
              </button>
              {cityDisplay.truncated ? (
                <button
                  type="button"
                  className="expand-cities-btn"
                  onClick={() => setCitiesExpanded(true)}
                  title="Show all locations"
                >
                  +{cityDisplay.hiddenCount} more
                </button>
              ) : citiesExpanded && cityLabels.length > CITY_PREVIEW_LIMIT ? (
                <button
                  type="button"
                  className="expand-cities-btn"
                  onClick={() => setCitiesExpanded(false)}
                  title="Show fewer locations"
                >
                  Show less
                </button>
              ) : null}
            </div>
            <span>{company.country_label}</span>
            <span>{countLabel}</span>
            <span className="company-activity">
              {formatActivityBadge(companyActivityTs(company))}
            </span>
            {tailoredCount > 0 ? (
              <a className="company-cv-summary" href={workspaceHref} title="View tailored CVs and cover letters">
                {tailoredCount} application doc{tailoredCount === 1 ? "" : "s"}
              </a>
            ) : null}
          </div>
          {company.careers_url ? (
            <div className="careers-row">
              <a className="job-title job-title--secondary" href={company.careers_url} target="_blank" rel="noopener noreferrer">
                Careers page
              </a>
            </div>
          ) : (
            <span className="company-no-careers">No careers URL</span>
          )}
          <div className="company-status-row">
            {company.company_applied ? (
              <span className="badge applied">
                <span className="company-status-label">
                  {appliedCount > 1 ? `${appliedCount} roles applied` : "Applied"}
                </span>
                {companyAppliedAtCompact ? (
                  <span className="company-status-date">{companyAppliedAtCompact}</span>
                ) : null}
              </span>
            ) : null}
            {company.awaiting_response ? (
              <button type="button" className="awaiting-response-btn active" data-awaiting="1" aria-pressed="true" title="Clear awaiting-response status">
                <span className="company-status-label">Awaiting</span>
                {company.awaiting_response_date ? (
                  <span className="company-status-date">
                    {formatCompactDateTime(company.awaiting_response_date)}
                  </span>
                ) : null}
              </button>
            ) : (
              <button type="button" className="awaiting-response-btn" data-awaiting="0" aria-pressed="false" title="Mark this company as awaiting a response">
                <span className="company-status-label">Mark awaiting</span>
              </button>
            )}
          </div>
          <div className="company-list-toggles" aria-label="Archived role groups">
            {notForMeCount > 0 ? (
              <button
                type="button"
                className={`show-not-for-me-btn${showingNotForMe ? " active" : ""}`}
                data-company-key={keyStr}
                title="Show jobs marked Not for me"
              >
                {showingNotForMe
                  ? "Hide not for me"
                  : `Not for me (${notForMeCount})`}
              </button>
            ) : null}
            {rejectedCount > 0 ? (
              <button
                type="button"
                className={`show-rejected-btn${showingRejected ? " active" : ""}`}
                data-company-key={keyStr}
                title="Show jobs marked rejected"
              >
                {showingRejected
                  ? "Hide rejected"
                  : `Rejected (${rejectedCount})`}
              </button>
            ) : null}
          </div>
        </div>
        <div className="company-header-actions">
          <details className="company-more">
            <summary className="icon-action-btn" aria-label={`More actions for ${company.name}`} title="More company actions">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                <circle cx="5" cy="12" r="1.8" />
                <circle cx="12" cy="12" r="1.8" />
                <circle cx="19" cy="12" r="1.8" />
              </svg>
            </summary>
            <div className="company-more-menu" aria-label="Company actions">
              <button
                type="button"
                className="edit-name-btn"
                data-country={company.country}
                data-country-label={company.country_label || ""}
                data-company={company.name}
              >
                Rename company
              </button>
              <button
                type="button"
                className="edit-careers-btn"
                data-country={company.country}
                data-country-label={company.country_label || ""}
                data-company={company.name}
                data-url={company.careers_url || ""}
              >
                {company.careers_url ? "Edit careers URL" : "Add careers URL"}
              </button>
              {ui.scrapeEnabled ? (
              <button
                type="button"
                className="fetch-company-btn"
                data-country={company.country}
                data-company={company.name}
                disabled={ui.serverFetchRunning}
                onClick={(e) => {
                  e.stopPropagation();
                  window.relocationJobs?.fetchActions?.fetchCompany?.(
                    company.country,
                    company.name,
                  );
                }}
              >
                {isFetching ? "Fetching…" : "Fetch jobs"}
              </button>
              ) : null}
              <button
                type="button"
                className="remove-company-btn"
                data-country={company.country}
                data-company={company.name}
              >
                Remove company
              </button>
            </div>
          </details>
          <button
            type="button"
            className="collapse-company-btn icon-action-btn"
            title={isCollapsed ? "Show positions" : "Hide positions"}
            aria-label={isCollapsed ? `Show positions for ${company.name}` : `Hide positions for ${company.name}`}
            aria-expanded={!isCollapsed}
          >
            <svg className="collapse-company-chevron" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.25" aria-hidden="true">
              <path d="m6 9 6 6 6-6" />
            </svg>
          </button>
        </div>
      </div>
      <div className="positions">
        {!isCollapsed && openJobs.length ? (
          openPreview.visible.map((job) => (
            <JobCard
              key={job.idempotency_key || job.url}
              job={job}
              company={company}
              variant="open"
            />
          ))
        ) : !isCollapsed ? (
          <div className="position-card position-card-empty">
            <p className="empty-hint text-sm text-muted">{emptyMessage(company, ui)}</p>
          </div>
        ) : null}
        {!isCollapsed && showingRejected && rejectedCount > 0 ? (
          <>
            <div className="rejected-jobs-heading">Rejected jobs</div>
            {rejectedPreview.visible.map((job) => (
              <JobCard
                key={`r-${job.idempotency_key || job.url}`}
                job={job}
                company={company}
                variant="rejected"
              />
            ))}
          </>
        ) : null}
        {!isCollapsed && showingNotForMe && notForMeCount > 0 ? (
          <>
            <div className="not-for-me-jobs-heading">Not for me jobs</div>
            {notForMePreview.visible.map((job) => (
              <JobCard
                key={`n-${job.idempotency_key || job.url}`}
                job={job}
                company={company}
                variant="not_for_me"
              />
            ))}
          </>
        ) : null}
        {!isCollapsed && rolesTruncatable ? (
          <ExpandRolesBtn
            hiddenCount={rolesHiddenCount}
            expanded={rolesExpanded}
            onExpand={() => setRolesExpanded(true)}
            onCollapse={collapseRolesPreview}
          />
        ) : null}
      </div>
    </article>
  );
}

export default memo(CompanyCard);
