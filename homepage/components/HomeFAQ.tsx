const QUESTIONS = [
  {
    question: "Does every role guarantee visa sponsorship?",
    answer: "No. Kuchup focuses the search on relocation-friendly companies and highlights available sponsorship signals, but eligibility depends on the role, country, company policy, and your circumstances. Always confirm the current job description before applying.",
  },
  {
    question: "Where do the jobs come from?",
    answer: "The catalog is built from company career pages. Kuchup detects the employer's applicant-tracking system and reads current openings from that source instead of relying on a syndicated job-board feed.",
  },
  {
    question: "How current is the catalog?",
    answer: "The production catalog is scheduled to refresh every six hours. A role can still change between refreshes, so the company career page remains the final source of truth.",
  },
  {
    question: "Will Kuchup apply for me?",
    answer: "No. Kuchup helps you discover, track, and prepare. You review the application material and choose when and where to submit it.",
  },
  {
    question: "What can I use without signing in?",
    answer: "You can search the public preview, explore supported countries, and inspect sample company results. Sign in to use the full board, personal tracking, company workspaces, and application documents.",
  },
] as const;

export function HomeFAQ() {
  return (
    <section className="landing-band landing-band-sky" aria-labelledby="faq-heading">
      <div className="landing-shell section-major faq-layout">
        <header>
          <p className="section-kicker">Clear before you commit</p>
          <h2 id="faq-heading" className="text-section-display text-text-primary">
            Questions a careful job seeker should ask.
          </h2>
        </header>
        <div className="faq-list">
          {QUESTIONS.map((item) => (
            <details key={item.question}>
              <summary>
                <span>{item.question}</span>
                <span className="faq-marker" aria-hidden="true">+</span>
              </summary>
              <p>{item.answer}</p>
            </details>
          ))}
        </div>
      </div>
    </section>
  );
}
