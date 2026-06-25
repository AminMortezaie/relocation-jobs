import { memo } from "react";
import { companyActivityTs, formatActivityBadge, formatAppliedLabel } from "./format";
import { sortJobsForDisplay } from "./sort";
import JobCard from "./JobCard";

function companyKey(company) {
  return `${company.country}:${company.name}`;
}

function companyLocationLabels(company) {
  if (Array.isArray(company.locations) && company.locations.length) {
    return company.locations.map(
      (loc) => loc.label || `${loc.city} (${loc.country_label || loc.country})`,
    );
  }
  if (Array.isArray(company.cities) && company.cities.length) return company.cities;
  const single = (company.city || "").trim();
  if (!single) return [];
  return single.split(",").map((part) => part.trim()).filter(Boolean);
}

function formatCompanyCities(company) {
  const labels = companyLocationLabels(company);
  return labels.length ? labels.join(" · ") : "Set locations";
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
  const locationPayload = Array.isArray(company.locations) && company.locations.length
    ? company.locations
    : cityLabels.map((city) => ({ city }));
  const notForMeJobs = company.not_for_me_jobs || company.hidden_jobs || [];
  const notForMeCount = notForMeJobs.length;
  const rejectedCount = (company.rejected_jobs || []).length;
  const showingNotForMe = showNotForMeSet.has(keyStr);
  const showingRejected = showRejectedSet.has(keyStr) || ui.positionRejectedOnly;
  const isFetching = ui.fetchingCompanyKey === keyStr;
  const countLabel = company.job_count === 1 ? "1 role" : `${company.job_count} roles`;
  const appliedCount = company.positions_applied_all ?? company.positions_applied ?? 0;
  const openJobs = sortJobsForDisplay(company.jobs || []);

  return (
    <article
      className={`company-card${companyCls}${isCollapsed ? " collapsed" : ""}`}
      data-country={company.country}
      data-company={company.name}
    >
      <div className="company-header">
        <div>
          <div className="company-name-row">
            <div className="company-name">{company.name}</div>
            <button
              type="button"
              className="edit-name-btn"
              data-country={company.country}
              data-country-label={company.country_label || ""}
              data-company={company.name}
              title="Rename this company"
            >
              Rename
            </button>
          </div>
          <div className="company-meta">
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
              {formatCompanyCities(company)}
            </button>
            <span>{company.country_label}</span>
            <span>{countLabel}</span>
          </div>
          {company.careers_url ? (
            <div className="careers-row">
              <a className="job-title" href={company.careers_url} target="_blank" rel="noopener noreferrer" style={{ fontSize: "0.8rem", fontWeight: 500 }}>
                Careers page
              </a>
              <button
                type="button"
                className="edit-careers-btn"
                data-country={company.country}
                data-country-label={company.country_label || ""}
                data-company={company.name}
                data-url={company.careers_url}
                title="Fix wrong careers URL"
              >
                Edit URL
              </button>
            </div>
          ) : (
            <div className="careers-row">
              <span className="job-meta">No careers URL</span>
              <button
                type="button"
                className="edit-careers-btn"
                data-country={company.country}
                data-country-label={company.country_label || ""}
                data-company={company.name}
                data-url=""
                title="Add careers URL"
              >
                Edit URL
              </button>
            </div>
          )}
          <div className="company-toolbar">
            {company.awaiting_response ? (
              <button type="button" className="awaiting-response-btn active" data-awaiting="1" title="Clear awaiting-response mark">
                Awaiting response{company.awaiting_response_date ? ` · ${company.awaiting_response_date}` : ""}
              </button>
            ) : (
              <button type="button" className="awaiting-response-btn" data-awaiting="0" title="Waiting on application response(s) before applying to other roles here">
                Awaiting response
              </button>
            )}
            {notForMeCount > 0 ? (
              <button
                type="button"
                className={`show-not-for-me-btn${showingNotForMe ? " active" : ""}`}
                data-company-key={keyStr}
                title="Show jobs marked Not for me"
              >
                {showingNotForMe
                  ? "Hide not for me jobs"
                  : `Show ${notForMeCount} not for me job${notForMeCount === 1 ? "" : "s"}`}
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
                  ? "Hide rejected jobs"
                  : `Show ${rejectedCount} rejected job${rejectedCount === 1 ? "" : "s"}`}
              </button>
            ) : null}
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
              title="Remove this company from the list"
            >
              Remove
            </button>
          </div>
        </div>
        <div className="company-header-side">
          <button type="button" className="collapse-company-btn" title="Hide or show roles under this company">
            {isCollapsed ? "Show positions" : "Hide positions"}
          </button>
          <span className="badge country">{company.country_label}</span>
          {company.company_applied ? (
            <span className="badge applied">
              {appliedCount > 1
                ? `${appliedCount} roles applied`
                : formatAppliedLabel({
                    date: company.company_applied_date || "",
                    at: company.company_applied_at || "",
                  })}
            </span>
          ) : null}
          {company.awaiting_response ? (
            <span className="badge awaiting-response">
              Awaiting response{company.awaiting_response_date ? ` · ${company.awaiting_response_date}` : ""}
            </span>
          ) : null}
          <span className="badge date">{formatActivityBadge(companyActivityTs(company))}</span>
        </div>
      </div>
      <div className="positions">
        {!isCollapsed && openJobs.length ? (
          openJobs.map((job) => <JobCard key={job.idempotency_key || job.url} job={job} variant="open" />)
        ) : !isCollapsed ? (
          <div className="position-card"><span className="job-meta">{emptyMessage(company, ui)}</span></div>
        ) : null}
        {!isCollapsed && showingRejected && rejectedCount > 0 ? (
          <>
            <div className="rejected-jobs-heading">Rejected jobs</div>
            {sortJobsForDisplay(company.rejected_jobs || []).map((job) => (
              <JobCard key={`r-${job.idempotency_key || job.url}`} job={job} variant="rejected" />
            ))}
          </>
        ) : null}
        {!isCollapsed && showingNotForMe && notForMeCount > 0 ? (
          <>
            <div className="not-for-me-jobs-heading">Not for me jobs</div>
            {sortJobsForDisplay(notForMeJobs).map((job) => (
              <JobCard key={`n-${job.idempotency_key || job.url}`} job={job} variant="not_for_me" />
            ))}
          </>
        ) : null}
      </div>
    </article>
  );
}

export default memo(CompanyCard);
