import { HIDE_REASONS, notForMeReasonMeta } from "../constants";

export default function HideReasonPicker({ currentReason = "" }) {
  const active = currentReason ? notForMeReasonMeta(currentReason) : null;
  const triggerTone = active?.badgeCls || "not-for-me";
  const triggerLabel = active ? active.label : "Not for me";
  const popoverTitle = currentReason ? "Change category" : "Why hide this role?";

  return (
    <div className="hide-reason-wrap" data-current-reason={currentReason || ""}>
      <button
        type="button"
        className={`hide-reason-trigger hide-reason-trigger--${triggerTone}`}
        aria-expanded="false"
        aria-haspopup="menu"
        title={currentReason ? "Change hide category" : "Hide this role"}
      >
        {triggerLabel}
        <svg className="hide-reason-chevron" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true">
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>
      <div className="hide-reason-popover" hidden role="menu" aria-label={popoverTitle}>
        <p className="hide-reason-popover-title">{popoverTitle}</p>
        <div className="hide-reason-options">
          {HIDE_REASONS.map((r) => {
            const isCurrent = Boolean(currentReason) && r.id === currentReason;
            return (
              <button
                key={r.id}
                type="button"
                className={`hide-reason-option hide-reason-option--${r.tone}${isCurrent ? " is-current" : ""}`}
                data-reason={r.id}
                role="menuitem"
                aria-current={isCurrent ? "true" : undefined}
              >
                <span className="hide-reason-option-dot" aria-hidden="true" />
                <span className="hide-reason-option-text">
                  <span className="hide-reason-option-label">{r.label}</span>
                  <span className="hide-reason-option-desc">{r.desc}</span>
                </span>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
