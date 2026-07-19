const PRINCIPLES = [
  {
    title: "You decide what moves forward",
    body: "Kuchup does not mass-apply or submit an application on your behalf.",
  },
  {
    title: "Evidence before polish",
    body: "CV reframing uses your master material and project evidence; it should never invent experience.",
  },
  {
    title: "Review is part of the workflow",
    body: "Tailored documents stay in a gated process so you can approve the content before use.",
  },
  {
    title: "Your tracking is your own",
    body: "Personal application states are kept as a per-user layer over the shared job catalog.",
  },
] as const;

export function TrustPrinciples() {
  return (
    <section className="landing-band trust-band" aria-labelledby="trust-heading">
      <div className="landing-shell section-major trust-layout">
        <header>
          <p className="section-kicker">Built around your agency</p>
          <h2 id="trust-heading" className="text-section-display text-text-primary">
            Assistance without taking the wheel.
          </h2>
        </header>
        <div className="trust-list">
          {PRINCIPLES.map((principle) => (
            <article key={principle.title}>
              <span aria-hidden="true">✓</span>
              <div>
                <h3>{principle.title}</h3>
                <p>{principle.body}</p>
              </div>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
