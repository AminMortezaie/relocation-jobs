const EVIDENCE = [
  { value: "25", label: "ATS types supported" },
  { value: "6h", label: "Catalog refresh cycle" },
  { value: "Direct", label: "Company career-page sources" },
] as const;

export function EvidenceRail() {
  return (
    <section className="landing-shell evidence-rail" aria-label="How Kuchup keeps the catalog useful">
      {EVIDENCE.map((item) => (
        <div key={item.label} className="evidence-item">
          <strong>{item.value}</strong>
          <span>{item.label}</span>
        </div>
      ))}
    </section>
  );
}
