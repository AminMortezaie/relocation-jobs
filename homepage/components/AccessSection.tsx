import { Button } from "@/components/ui/Button";

const PREVIEW_ITEMS = [
  "Search the public catalog",
  "Browse country entry points",
  "Preview companies and current role counts",
] as const;

const WORKSPACE_ITEMS = [
  "Open the full company board",
  "Track personal application status",
  "Keep role-specific CV and cover-letter files",
  "Use the gated application-preparation workflow",
] as const;

export function AccessSection() {
  return (
    <section id="access" className="landing-band landing-band-access" aria-labelledby="access-heading">
      <div className="landing-shell section-major">
        <header className="access-intro">
          <p className="section-kicker">Start in public, continue in private</p>
          <h2 id="access-heading" className="text-section-display text-text-primary">
            Explore first. Build your workspace when the search becomes real.
          </h2>
          <p className="section-lede">
            The public preview helps you understand the market before creating
            an account. Sign in when you are ready to keep decisions and
            application material together.
          </p>
        </header>

        <div className="access-grid">
          <article className="access-panel">
            <p className="access-label">Public preview</p>
            <h3>Search without signing in</h3>
            <p>See whether Kuchup covers the roles and countries relevant to your move.</p>
            <ul>
              {PREVIEW_ITEMS.map((item) => <li key={item}>{item}</li>)}
            </ul>
            <Button as="a" href="#search" variant="secondary">Search the catalog</Button>
          </article>

          <article className="access-panel access-panel-primary">
            <p className="access-label">Personal workspace</p>
            <h3>Carry the role through to application</h3>
            <p>Your tracking and documents stay connected to the company and position.</p>
            <ul>
              {WORKSPACE_ITEMS.map((item) => <li key={item}>{item}</li>)}
            </ul>
            <Button as="a" href="/panel" variant="primary">Open the workspace</Button>
          </article>
        </div>

        <p className="access-note">
          The public preview is free. Commercial pricing for expanded access
          has not been announced. <a href="/pricing">See access details →</a>
        </p>
      </div>
    </section>
  );
}
