function pageRange(current, total) {
  if (total <= 7) {
    return Array.from({ length: total }, (_, i) => i + 1);
  }
  const pages = new Set([1, total, current, current - 1, current + 1]);
  const sorted = [...pages].filter((p) => p >= 1 && p <= total).sort((a, b) => a - b);
  const out = [];
  for (let i = 0; i < sorted.length; i += 1) {
    if (i > 0 && sorted[i] - sorted[i - 1] > 1) out.push("…");
    out.push(sorted[i]);
  }
  return out;
}

export default function BoardPagination({ pagination }) {
  if (!pagination || pagination.totalPages <= 1) return null;

  const { page, totalPages, totalCompanies, pageSize, loading } = pagination;
  const start = totalCompanies ? (page - 1) * pageSize + 1 : 0;
  const end = totalCompanies ? Math.min(page * pageSize, totalCompanies) : 0;

  return (
    <nav className="board-pagination" aria-label="Board pages">
      <p className="board-pagination-summary">
        {totalCompanies
          ? `Page ${page} of ${totalPages} · ${start}–${end} of ${totalCompanies} companies`
          : `Page ${page} of ${totalPages}`}
      </p>
      <div className="board-pagination-controls">
        <button
          type="button"
          className="filter-btn board-page-nav"
          disabled={loading || page <= 1}
          onClick={() => window.relocationJobs?.goToBoardPage?.(page - 1)}
        >
          Previous
        </button>
        {pageRange(page, totalPages).map((item, idx) => (
          typeof item === "number" ? (
            <button
              key={`page-${item}`}
              type="button"
              className={`filter-btn board-page-num${item === page ? " is-active" : ""}`}
              disabled={loading || item === page}
              aria-current={item === page ? "page" : undefined}
              onClick={() => window.relocationJobs?.goToBoardPage?.(item)}
            >
              {item}
            </button>
          ) : (
            <span key={`gap-${idx}`} className="board-page-gap" aria-hidden="true">{item}</span>
          )
        ))}
        <button
          type="button"
          className="filter-btn board-page-nav"
          disabled={loading || page >= totalPages}
          onClick={() => window.relocationJobs?.goToBoardPage?.(page + 1)}
        >
          Next
        </button>
      </div>
    </nav>
  );
}
