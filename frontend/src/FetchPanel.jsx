import { useEffect, useMemo, useState } from "react";

const PREVIEW = 10;

function FetchPanel({ panel = {} }) {
  const [selected, setSelected] = useState(new Set());
  const open = Boolean(panel.open);

  useEffect(() => {
    document.body.classList.toggle("fetch-modal-open", open);
    return () => document.body.classList.remove("fetch-modal-open");
  }, [open]);

  useEffect(() => {
    setSelected(new Set());
  }, [panel.review?.country, panel.review?.company, panel.review?.filtered]);

  const filteredVisible = useMemo(() => {
    const filtered = panel.review?.filtered || [];
    if (panel.review?.filteredExpanded || filtered.length <= PREVIEW) return filtered;
    return filtered.slice(0, PREVIEW);
  }, [panel.review?.filtered, panel.review?.filteredExpanded]);

  const hiddenCount = Math.max(0, (panel.review?.filtered?.length || 0) - filteredVisible.length);

  if (!open) return null;

  const actions = window.relocationJobs?.fetchActions || {};
  const review = panel.review || {};
  const countryResults = panel.countryResults || {};
  const footer = panel.footer || {};
  const progress = panel.progress || {};
  const activity = panel.activity || {};
  const log = panel.log || {};
  const completion = panel.completion || {};

  function toggleJob(idx) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  }

  async function onAddSelected() {
    const jobs = (review.filtered || []).filter((_, idx) => selected.has(idx));
    await actions.addSelectedReviewJobs?.(review.country, review.company, jobs);
  }

  return (
    <div
      className="dialog-backdrop fetch-panel-backdrop open"
      aria-hidden="false"
      onClick={(e) => {
        if (e.target === e.currentTarget) actions.closePanel?.();
      }}
    >
      <div className="fetch-panel" role="dialog" aria-modal="true" aria-labelledby="fetchTitle">
        <div className="fetch-panel-top">
          <div className="fetch-panel-title-wrap">
            <h2 className="fetch-panel-title" id="fetchTitle">{panel.title}</h2>
            <p className="fetch-panel-subtitle" id="fetchSubtitle">{panel.subtitle}</p>
            {!completion.hidden ? (
              <div className="fetch-completion" id="fetchCompletion">
                <p className="fetch-completion-label">{completion.label}</p>
                <dl className="fetch-completion-grid">
                  <div><dt>Started</dt><dd>{completion.started}</dd></div>
                  <div><dt>Finished</dt><dd>{completion.finished}</dd></div>
                  <div><dt>Duration</dt><dd>{completion.duration}</dd></div>
                  <div><dt>New roles</dt><dd>{completion.newJobs}</dd></div>
                </dl>
              </div>
            ) : null}
          </div>
          <div className="fetch-panel-actions">
            {!panel.cancelHidden ? (
              <button
                type="button"
                className="fetch-cancel-btn"
                disabled={panel.cancelDisabled}
                title={panel.cancelTitle || "Stop fetching"}
                onClick={() => actions.cancelFetch?.()}
              >
                {panel.cancelText || "Cancel"}
              </button>
            ) : null}
            {!panel.closeHidden ? (
              <button
                type="button"
                className="fetch-close-btn"
                aria-label="Close panel"
                onClick={() => actions.closePanel?.()}
              >
                ×
              </button>
            ) : null}
          </div>
        </div>

        <div className="fetch-panel-body">
          {!panel.progressWrapHidden ? (
            <div className="fetch-progress-wrap">
              <div className="fetch-progress-meta">
                <span>{progress.label}</span>
                <span>{progress.pct}%</span>
              </div>
              <div
                className="fetch-progress-track"
                role="progressbar"
                aria-valuemin="0"
                aria-valuemax="100"
                aria-valuenow={progress.pct}
              >
                <div className="fetch-progress-bar" style={{ width: `${progress.pct}%` }} />
              </div>
              {progress.companyLine ? (
                <p className="fetch-current-company">{progress.companyLine}</p>
              ) : null}
            </div>
          ) : null}

          {!activity.hidden ? (
            <div className="fetch-activity">
              <div className="fetch-activity-current">
                <span className="fetch-activity-pulse" aria-hidden="true" />
                <div className="fetch-activity-copy">
                  <p className="fetch-activity-step">{activity.step}</p>
                  {activity.detail ? (
                    <p className="fetch-activity-detail">{activity.detail}</p>
                  ) : null}
                </div>
              </div>
              {activity.items?.length ? (
                <ol className="fetch-activity-log">
                  {activity.items.map((entry, idx) => (
                    <li key={`${entry.message}-${idx}`}>
                      <span className="fetch-activity-log-text">{entry.message}</span>
                      {entry.detail ? (
                        <span className="fetch-activity-log-meta">{entry.detail}</span>
                      ) : null}
                    </li>
                  ))}
                </ol>
              ) : null}
            </div>
          ) : null}

          {countryResults.visible ? (
            <div className="fetch-country-results">
              <div className="fetch-country-results-head">
                <h3 className="fetch-review-heading">
                  New roles found ({countryResults.totalNewJobs || 0})
                </h3>
                <p className="fetch-country-results-sub">
                  {countryResults.companies.length === 1
                    ? "1 company with new roles"
                    : `${countryResults.companies.length} companies with new roles`}
                </p>
              </div>
              <div className="fetch-country-results-list">
                {countryResults.companies.map((entry) => (
                  <section key={entry.company} className="fetch-country-results-company">
                    <h4 className="fetch-country-results-company-name">
                      {entry.company}
                      <span className="fetch-country-results-count">
                        {entry.new_count === 1 ? "1 new role" : `${entry.new_count} new roles`}
                      </span>
                    </h4>
                    {entry.jobs?.length ? (
                      <ul className="fetch-review-list">
                        {entry.jobs.map((job) => (
                          <li key={job.url || job.title} className="fetch-review-item">
                            <a href={job.url} target="_blank" rel="noopener noreferrer">
                              {job.title || job.url}
                            </a>
                          </li>
                        ))}
                      </ul>
                    ) : null}
                  </section>
                ))}
              </div>
            </div>
          ) : null}

          {review.visible ? (
            <div className="fetch-review">
              {review.hint ? <p className="fetch-review-hint">{review.hint}</p> : null}
              <div className="fetch-review-section">
                <div className="fetch-review-section-head">
                  <h3 className="fetch-review-heading">
                    {review.filtered?.length
                      ? `Filtered out (${review.filtered.length})`
                      : "Filtered out (0)"}
                  </h3>
                  {review.addBtnVisible ? (
                    <button
                      type="button"
                      className="fetch-review-add-btn"
                      onClick={onAddSelected}
                    >
                      Add selected
                    </button>
                  ) : null}
                </div>
                <ul className="fetch-review-list fetch-review-checklist">
                  {filteredVisible.length ? filteredVisible.map((job, idx) => (
                    <li key={job.url || idx} className="fetch-review-item">
                      <label>
                        <input
                          type="checkbox"
                          className="fetch-review-check"
                          checked={selected.has(idx)}
                          onChange={() => toggleJob(idx)}
                        />
                        <span className="fetch-review-item-body">
                          <a href={job.url} target="_blank" rel="noopener noreferrer">
                            {job.title || job.url}
                          </a>
                          {job.filter_reason ? (
                            <span className="fetch-review-reason">{job.filter_reason}</span>
                          ) : null}
                        </span>
                      </label>
                    </li>
                  )) : (
                    <li className="fetch-review-item">
                      <span className="job-meta">{review.missingReview ? "No review data" : "None"}</span>
                    </li>
                  )}
                </ul>
                {!review.expandHidden ? (
                  <button
                    type="button"
                    className="fetch-review-expand-btn"
                    onClick={() => actions.toggleReviewExpand?.()}
                  >
                    {review.expandLabel}
                  </button>
                ) : null}
              </div>
              {review.included?.length ? (
                <div className="fetch-review-section">
                  <h3 className="fetch-review-heading">Matched ({review.included.length})</h3>
                  <ul className="fetch-review-list">
                    {review.included.map((job) => (
                      <li key={job.url} className="fetch-review-item">
                        <a href={job.url} target="_blank" rel="noopener noreferrer">
                          {job.title || job.url}
                        </a>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
          ) : null}

          {!log.hidden ? (
            <pre className={`fetch-log${log.active ? " fetch-log-active" : ""}`}>{log.text}</pre>
          ) : null}
        </div>

        {!footer.hidden ? (
          <div className="fetch-panel-footer">
            <div className={`fetch-review-feedback${footer.pending ? " is-pending" : ""}${footer.resolved ? " is-resolved" : ""}`}>
              {!footer.resolved ? (
                <div className="fetch-review-feedback-prompt">
                  <span className="fetch-review-feedback-label">{footer.prompt}</span>
                  <div className="fetch-review-feedback-actions">
                    <button
                      type="button"
                      className="fetch-review-ok-btn"
                      disabled={footer.okDisabled}
                      onClick={() => actions.submitReviewFeedback?.(footer.country, footer.company, "ok")}
                    >
                      Yes, looks good
                    </button>
                    <button
                      type="button"
                      className="fetch-review-problem-btn"
                      disabled={footer.problemDisabled}
                      onClick={() => actions.submitReviewFeedback?.(footer.country, footer.company, "problem")}
                    >
                      No, fetch problem
                    </button>
                  </div>
                </div>
              ) : (
                <div className={`fetch-review-feedback-result is-${footer.resolvedStatus === "ok" ? "ok" : "problem"}`}>
                  <span className="fetch-review-feedback-text">
                    {footer.resolvedStatus === "ok" ? "Fetch confirmed OK" : "Marked as fetch problem"}
                  </span>
                </div>
              )}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

export default FetchPanel;
