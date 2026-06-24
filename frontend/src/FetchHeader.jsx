function FetchHeader({ header = {} }) {
  if (!header.controlsEnabled) return null;

  if (header.showButton) {
    return (
      <button
        type="button"
        className={`header-secondary-btn${header.countryRequired ? " fetch-country-required" : ""}`}
        title={header.buttonTitle || "Fetch jobs for the selected country and ATS filter"}
        onClick={(e) => {
          e.stopPropagation();
          window.relocationJobs?.fetchActions?.startFetch?.();
        }}
      >
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
          <path d="M21 12a9 9 0 1 1-3-6.7" />
          <path d="M21 3v6h-6" />
        </svg>
        <span className="header-btn-text">Fetch</span>
      </button>
    );
  }

  if (!header.showChip) return null;

  return (
    <button
      type="button"
      className="header-secondary-btn fetch-progress-chip"
      title={header.chipTitle || "View fetch progress"}
      aria-label={header.chipTitle || "View fetch progress"}
      onClick={(e) => {
        e.stopPropagation();
        window.relocationJobs?.fetchActions?.openProgress?.();
      }}
    >
      <span className="fetch-progress-chip-meter" aria-hidden="true">
        <span
          className="fetch-progress-chip-fill"
          style={{ width: `${header.pct || 4}%` }}
        />
      </span>
      <span className="header-btn-text">{header.metaText || "Fetching…"}</span>
      <svg className="fetch-progress-chip-chevron" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
        <path d="M9 18l6-6-6-6" />
      </svg>
    </button>
  );
}

export default FetchHeader;
