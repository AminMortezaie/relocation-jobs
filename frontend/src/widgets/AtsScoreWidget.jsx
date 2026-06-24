import { atsScoreTone } from "../format.js";

export default function AtsScoreWidget({ job }) {
  const hasScore = job.ats_score != null && job.ats_score !== "";
  const score = hasScore ? Number(job.ats_score) : 70;
  const tone = hasScore ? atsScoreTone(score) : "";

  return (
    <div className="ats-score-wrap">
      <button
        type="button"
        className={`ats-score-trigger${hasScore ? ` ats-has-score ${tone}` : " ats-empty"}`}
        aria-expanded="false"
        aria-haspopup="dialog"
        title={hasScore ? `ATS score ${score} — click to edit` : "Set ATS resume match score"}
      >
        {hasScore ? (
          <span className="ats-score-ring" style={{ "--ats-pct": score }}>
            <span className="ats-score-num">{score}</span>
          </span>
        ) : (
          <>
            <span className="ats-score-ring ats-score-ring--empty" aria-hidden="true">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M12 5v14M5 12h14" />
              </svg>
            </span>
            <span className="ats-score-trigger-text">ATS</span>
          </>
        )}
      </button>
      <div className="ats-score-popover" hidden role="dialog" aria-label={`ATS score for ${job.title}`}>
        <div className="ats-score-popover-head">
          <span className="ats-score-popover-title">Resume ATS match</span>
          <button type="button" className="ats-score-close" aria-label="Close">×</button>
        </div>
        <div className={`ats-score-preview-wrap ${hasScore ? atsScoreTone(score) : "ats-mid"}`}>
          <div className="ats-score-ring-preview" style={{ "--ats-pct": score }}>
            <span className="ats-score-preview">{score}</span>
          </div>
          <div className="ats-score-manual">
            <input
              type="number"
              className="ats-score-number"
              min="0"
              max="100"
              step="1"
              defaultValue={score}
              aria-label="ATS score"
            />
            <span className="ats-score-manual-unit">/ 100</span>
          </div>
        </div>
        <div className="ats-score-slider-wrap">
          <input
            type="range"
            className="ats-score-slider"
            min="0"
            max="100"
            step="1"
            defaultValue={score}
            aria-label="ATS score slider"
          />
          <div className="ats-score-slider-labels"><span>0</span><span>50</span><span>100</span></div>
        </div>
        <div className="ats-score-quick" role="group" aria-label="Quick scores">
          {[40, 60, 75, 90].map((n) => (
            <button key={n} type="button" className="ats-quick-chip" data-score={n}>{n}</button>
          ))}
        </div>
        <div className="ats-score-popover-foot">
          <button type="button" className="ats-score-save-btn">Save score</button>
          {hasScore ? <button type="button" className="ats-score-clear-btn link-btn">Remove score</button> : null}
        </div>
      </div>
    </div>
  );
}
