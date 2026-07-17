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
          <img src="/static/icons/kuchup-bird.png" alt="" width="48" height="45" />
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
