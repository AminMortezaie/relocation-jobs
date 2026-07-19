const ITEMS = [
  { icon: "check", text: "Free to use" },
  { icon: "shield", text: "No spam applications sent on your behalf, ever" },
  { icon: "lock", text: "Your tracking data stays private" },
  { icon: "globe", text: "Works across Germany, Netherlands, Ireland, and more" },
] as const;

export function ReassuranceStrip() {
  return (
    <section className="section-compact" aria-label="Trust">
      <div className="grid grid-cols-1 gap-3 border-y border-border-subtle py-4 sm:grid-cols-2 lg:grid-cols-4 lg:gap-x-6">
        {ITEMS.map((item) => (
          <div key={item.text} className="inline-flex items-start gap-2.5 text-text-muted">
            <ReassuranceIcon type={item.icon} />
            <p className="text-sm font-medium leading-snug">{item.text}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

function ReassuranceIcon({ type }: { type: (typeof ITEMS)[number]["icon"] }) {
  const className = "h-4 w-4 shrink-0 text-accent-primary";

  if (type === "check") {
    return (
      <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
        <path d="M20 6L9 17l-5-5" />
      </svg>
    );
  }
  if (type === "shield") {
    return (
      <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      </svg>
    );
  }
  if (type === "lock") {
    return (
      <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
        <rect x="5" y="11" width="14" height="10" rx="2" />
        <path d="M8 11V8a4 4 0 0 1 8 0v3" />
      </svg>
    );
  }
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <circle cx="12" cy="12" r="9" />
      <path d="M2 12h20M12 2a15 15 0 0 1 0 20M12 2a15 15 0 0 0 0 20" />
    </svg>
  );
}
