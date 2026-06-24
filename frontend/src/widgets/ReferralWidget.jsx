export default function ReferralWidget({ job }) {
  const active = Boolean(job.waiting_referral);
  const linkedin = (job.referral_linkedin_url || "").trim();
  const dateSuffix = job.waiting_referral_date ? ` · ${job.waiting_referral_date}` : "";

  return (
    <div className="referral-wrap">
      <button
        type="button"
        className={`referral-btn${active ? " active" : ""}`}
        aria-expanded="false"
        aria-haspopup="dialog"
        title={active ? "Edit referrer LinkedIn" : "Waiting for someone to refer you"}
      >
        Waiting referral{active ? dateSuffix : ""}
      </button>
      <div className="referral-popover" hidden role="dialog" aria-label={`Referrer LinkedIn for ${job.title}`}>
        <div className="referral-popover-head">
          <span className="referral-popover-title">Referrer LinkedIn</span>
          <button type="button" className="referral-close" aria-label="Close">×</button>
        </div>
        <p className="referral-popover-hint">Profile of the person you asked to refer you.</p>
        <input
          type="url"
          className="referral-linkedin-input"
          placeholder="https://www.linkedin.com/in/username"
          defaultValue={linkedin}
          spellCheck="false"
        />
        <div className="referral-popover-foot">
          <button type="button" className="referral-save-btn">Save</button>
          {active ? <button type="button" className="referral-clear-btn link-btn">Clear status</button> : null}
        </div>
      </div>
    </div>
  );
}
