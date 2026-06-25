import CompanyCard from "./CompanyCard";
import BoardSkeleton from "./BoardSkeleton";

export default function App({ view }) {
  if (view.loading) {
    return <BoardSkeleton />;
  }

  if (!view.companies?.length) {
    return (
      <div className="empty">
        No companies match your filters on this page. Try another page or adjust filters.
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
