const FRAGMENTS = [
  "Career sites",
  "Sponsorship clues",
  "Application status",
  "CV versions",
] as const;

export function RelocationProblem() {
  return (
    <section className="landing-band landing-band-sky" aria-labelledby="problem-heading">
      <div className="landing-shell section-major problem-layout">
        <div className="problem-copy">
          <p className="section-kicker">The problem is not ambition</p>
          <h2 id="problem-heading" className="text-section-display text-text-primary">
            A relocation search breaks into too many pieces.
          </h2>
          <p className="section-lede">
            The role lives on one company site. Sponsorship context lives
            somewhere else. Your decisions sit in a spreadsheet, while every
            application creates another document to manage.
          </p>
        </div>

        <div className="fragment-path" aria-label="Disconnected parts brought into one workflow">
          <div className="fragment-list">
            {FRAGMENTS.map((fragment) => (
              <span key={fragment}>{fragment}</span>
            ))}
          </div>
          <div className="fragment-destination">
            <span className="fragment-line" aria-hidden="true" />
            <div>
              <p>Kuchup brings the thread together</p>
              <strong>Find → decide → prepare</strong>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
