import CompanyCard from "./CompanyCard";
import BoardSkeleton from "./BoardSkeleton";

export default function App({ view }) {
  if (view.loading) {
    return <BoardSkeleton />;
  }

  if (!view.companies?.length) {
    return (
      <div className="empty empty--branded">
        <div className="empty-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="11" r="8" />
            <path d="M4 11h16" />
            <path d="M12 3a8 8 0 0 1 0 16" />
            <path d="M12 3a8 8 0 0 0 0 16" />
            <rect x="8.5" y="15.5" width="7" height="5" rx="1" fill="currentColor" stroke="none" />
            <path d="M10 15.5V14a2 2 0 0 1 4 0v1.5" />
          </svg>
        </div>
        <p className="empty-title">No companies on this page</p>
        <p className="empty-hint text-sm text-muted">
          Try another country or adjust your visa and location filters.
        </p>
      </div>
    );
  }

  return view.companies.map((company) => (
    <CompanyCard
      key={`${company.country}:${company.name}`}
      company={company}
      ui={view.ui}
    />
  ));
}
