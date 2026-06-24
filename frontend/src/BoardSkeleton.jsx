export default function BoardSkeleton() {
  const cards = Array.from({ length: 4 }, (_, i) => (
    <div key={i} className="skeleton-card">
      <div className="skeleton-card-header">
        <div className="skeleton-block skeleton-name" />
        <div className="skeleton-badges">
          <div className="skeleton-block skeleton-badge" />
          <div className="skeleton-block skeleton-badge" />
        </div>
      </div>
      <hr className="skeleton-divider" />
      <div className="skeleton-jobs">
        <div className="skeleton-block skeleton-job" />
        <div className="skeleton-block skeleton-job skeleton-job--short" />
      </div>
    </div>
  ));

  return <>{cards}</>;
}
