const STEPS = [
  {
    title: "Browse the public catalog",
    body: "Search supported countries and preview companies hiring for relevant software roles.",
  },
  {
    title: "Save the roles that fit",
    body: "Sign in when you want the full board, personal status tracking, and company workspaces.",
  },
  {
    title: "Prepare with MCP for one job at a time",
    body: "Connect Claude or Cursor to Kuchup MCP. Bring the JD, master CV, and project evidence together — then review the tailored PDF yourself.",
  },
  {
    title: "Return to a current search",
    body: "The catalog refreshes every six hours, while your decisions and documents stay attached to the work.",
  },
] as const;

export function HomeWorkflow() {
  return (
    <section id="how-it-works" className="landing-band" aria-labelledby="workflow-heading">
      <div className="landing-shell section-major">
        <div className="workflow-home-head">
          <div>
            <p className="section-kicker">How it works</p>
            <h2 id="workflow-heading" className="text-section-display text-text-primary">
              A repeatable path, not another tab to manage.
            </h2>
          </div>
          <div className="workflow-home-links">
            <a href="/how-it-works" className="text-link">
              Read the full workflow <span aria-hidden="true">→</span>
            </a>
            <a href="/mcp" className="text-link">
              Claude &amp; Cursor MCP <span aria-hidden="true">→</span>
            </a>
          </div>
        </div>

        <ol className="workflow-home-list">
          {STEPS.map((step, index) => (
            <li key={step.title}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              <div>
                <h3>{step.title}</h3>
                <p>{step.body}</p>
              </div>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
