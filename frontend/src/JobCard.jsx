import { memo } from "react";
import {
  formatActivityBadge,
  formatAppliedHistoryTitle,
  formatAppliedLabel,
  jobActivityTs,
  newestStatusDate,
} from "./format";
import { notForMeReasonMeta } from "./constants";
import AtsScoreWidget from "./widgets/AtsScoreWidget";
import HideReasonPicker from "./widgets/HideReasonPicker";
import ReferralWidget from "./widgets/ReferralWidget";

function JobCityBadge({ job }) {
  const label = (job.job_city || job.location || "").trim();
  if (!label) return null;
  return <span className="badge job-city">{label}</span>;
}

function TitleRow({ job }) {
  return (
    <div className="position-title-row">
      <a className="job-title" href={job.url} target="_blank" rel="noopener noreferrer">{job.title}</a>
      <JobCityBadge job={job} />
    </div>
  );
}

function OpenJobCard({ job }) {
  const appliedHistory = job.applied_history || [];
  const appliedEvents = job.applied_events || [];
  const latestApplied = newestStatusDate(appliedHistory, job.applied_date || "");
  const appliedLabel = formatAppliedLabel({ date: latestApplied, at: job.applied_at || "" });
  const appliedTitle = formatAppliedHistoryTitle(appliedEvents.length ? appliedEvents : appliedHistory);
  const posCls = [
    job.applied ? " position-applied" : "",
    job.waiting_referral ? " position-waiting-referral" : "",
    job.looking_to_apply && !job.applied ? " position-looking-to-apply" : "",
    job.seen ? " position-seen" : "",
  ].join("");

  return (
    <div
      className={`position-card${posCls}`}
      data-country={job.country}
      data-company={job.company}
      data-url={job.url}
      data-idempotency-key={job.idempotency_key || ""}
    >
      <div className="position-top">
        <div className="position-head">
          <TitleRow job={job} />
          <div className="position-badges">
            {job.visa_sponsorship === true ? <span className="badge visa">Visa / relocation</span> : null}
            {job.applied ? (
              <span className="badge applied" title={appliedTitle ? `Applied on: ${appliedTitle}` : undefined}>
                {appliedLabel}
              </span>
            ) : null}
            {!job.applied && latestApplied ? (
              <span
                className="badge applied"
                title={formatAppliedHistoryTitle(appliedEvents.length ? appliedEvents : appliedHistory)}
              >
                {formatAppliedLabel({ date: latestApplied, at: job.applied_at || "" }, { before: true })}
              </span>
            ) : null}
            {job.waiting_referral && job.referral_linkedin_url ? (
              <a className="badge referral" href={job.referral_linkedin_url} target="_blank" rel="noopener noreferrer">Referrer</a>
            ) : job.waiting_referral ? (
              <span className="badge referral">Waiting referral</span>
            ) : null}
            {job.looking_to_apply && !job.applied ? (
              <span className="badge looking-to-apply">
                Looking to apply{job.looking_to_apply_date ? ` · ${job.looking_to_apply_date}` : ""}
              </span>
            ) : null}
            {job.seen ? (
              <span className="badge seen">Saw before{job.seen_date ? ` · ${job.seen_date}` : ""}</span>
            ) : null}
            <span className="badge date">{formatActivityBadge(jobActivityTs(job))}</span>
          </div>
        </div>
        <div className="position-side"><AtsScoreWidget job={job} /></div>
      </div>
      <div className="position-actions">
        {job.applied ? (
          <button type="button" className="applied-btn active" data-applied="1" title={appliedTitle ? `Applied on: ${appliedTitle}` : "Clear applied mark"}>
            {appliedLabel}
          </button>
        ) : (
          <button type="button" className="applied-btn" data-applied="0" title="Mark that you applied">I applied</button>
        )}
        <button type="button" className="rejected-btn" data-rejected="0" title="Mark that you got a rejection">Got rejection</button>
        {!job.applied && (
          job.looking_to_apply ? (
            <button type="button" className="looking-to-apply-btn active" data-looking="1" title="Clear looking-to-apply mark">
              Looking to apply{job.looking_to_apply_date ? ` · ${job.looking_to_apply_date}` : ""}
            </button>
          ) : (
            <button type="button" className="looking-to-apply-btn" data-looking="0" title="Mark as interested in applying">Looking to apply</button>
          )
        )}
        {job.seen ? (
          <button type="button" className="saw-before-btn active" data-seen="1" title="Clear saw-before mark">
            Saw before{job.seen_date ? ` · ${job.seen_date}` : ""}
          </button>
        ) : (
          <button type="button" className="saw-before-btn" data-seen="0" title="Mark that you saw this position before">Saw before</button>
        )}
        <ReferralWidget job={job} />
        {!job.applied ? <HideReasonPicker /> : null}
      </div>
    </div>
  );
}

function RejectedJobCard({ job }) {
  const rejectedHistory = job.rejected_history || [];
  const appliedHistory = job.applied_history || [];
  const appliedEvents = job.applied_events || [];
  const latestRejected = newestStatusDate(rejectedHistory, job.rejected_date || "");
  const latestApplied = newestStatusDate(appliedHistory, job.applied_date || "");
  const rejectedLabel = latestRejected ? `Rejected · ${latestRejected}` : "Rejected";
  const rejectedTitle = rejectedHistory.filter(Boolean).join(", ");
  const appliedTitle = formatAppliedHistoryTitle(appliedEvents.length ? appliedEvents : appliedHistory);

  return (
    <div
      className={`position-card rejected-role${job.seen ? " position-seen" : ""}`}
      data-country={job.country}
      data-company={job.company}
      data-url={job.url}
      data-idempotency-key={job.idempotency_key || ""}
    >
      <div className="position-top">
        <div className="position-head">
          <TitleRow job={job} />
          <div className="position-badges">
            <span className="badge rejected" title={rejectedTitle ? `Rejected on: ${rejectedTitle}` : undefined}>{rejectedLabel}</span>
            {latestApplied ? (
              <span className="badge applied" title={appliedTitle}>{formatAppliedLabel({ date: latestApplied, at: job.applied_at || "" })}</span>
            ) : null}
            {job.visa_sponsorship === true ? <span className="badge visa">Visa / relocation</span> : null}
            {job.seen ? <span className="badge seen">Saw before{job.seen_date ? ` · ${job.seen_date}` : ""}</span> : null}
            <span className="badge date">{formatActivityBadge(jobActivityTs(job))}</span>
          </div>
        </div>
        <div className="position-side"><AtsScoreWidget job={job} /></div>
      </div>
      <div className="position-actions">
        <button type="button" className="reapply-btn" title="Return to open positions so you can apply again">Reapply</button>
      </div>
    </div>
  );
}

function NotForMeJobCard({ job }) {
  const taggedDate = job.not_for_me_date ? ` · ${job.not_for_me_date}` : "";
  const { label: hideLabel, badgeCls: hideBadgeCls } = notForMeReasonMeta(job.not_for_me_reason);

  return (
    <div
      className="position-card not-for-me-role"
      data-country={job.country}
      data-company={job.company}
      data-url={job.url}
    >
      <div className="position-top">
        <div className="position-head">
          <TitleRow job={job} />
          <div className="position-badges">
            <span className={`badge ${hideBadgeCls}`}>{hideLabel}{taggedDate}</span>
            {job.visa_sponsorship === true ? <span className="badge visa">Visa / relocation</span> : null}
            <span className="badge date">{formatActivityBadge(jobActivityTs(job))}</span>
          </div>
        </div>
        <div className="position-side"><AtsScoreWidget job={job} /></div>
      </div>
      <div className="position-actions">
        <HideReasonPicker currentReason={job.not_for_me_reason || "not_for_me"} />
        <button type="button" className="restore-job-btn" title="Move back to applicable roles">Restore</button>
      </div>
    </div>
  );
}

function JobCard({ job, variant }) {
  if (variant === "rejected") return <RejectedJobCard job={job} />;
  if (variant === "not_for_me") return <NotForMeJobCard job={job} />;
  return <OpenJobCard job={job} />;
}

export default memo(JobCard);
