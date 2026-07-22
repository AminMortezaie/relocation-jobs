import { Pill } from "@/components/ui/Pill";

const CHAPTERS = [
  {
    number: "01",
    id: "discover",
    eyebrow: "Discover",
    title: "Start with roles worth your attention.",
    body: "Search a country-aware catalog built from company career pages. Kuchup keeps the source and refresh cycle visible, so you can spend time evaluating the role instead of rebuilding the list.",
  },
  {
    number: "02",
    id: "track",
    eyebrow: "Track",
    title: "Keep every decision in context.",
    body: "Move a role from consideration to applied, awaiting response, or not for me. Your personal state stays attached to the company and position instead of disappearing into a spreadsheet.",
  },
  {
    number: "03",
    id: "prepare",
    eyebrow: "Prepare",
    title: "Build the application from evidence.",
    body: "Connect Claude or Cursor to Kuchup MCP. The agent loads the JD from your catalog, reframes against your master CV and project evidence with your approval, then leaves tailored PDFs in the workspace — you submit.",
  },
] as const;

export function ProductJourney() {
  return (
    <section id="product" className="landing-band" aria-labelledby="journey-heading">
      <div className="landing-shell section-major">
        <header className="journey-intro">
          <p className="section-kicker">One continuous workspace</p>
          <h2 id="journey-heading" className="text-section-display text-text-primary">
            The search moves forward without losing the thread.
          </h2>
          <p className="section-lede">
            Kuchup follows the work from the first promising role to an
            application you are ready to send.
          </p>
        </header>

        <div className="journey-stack">
          {CHAPTERS.map((chapter) => (
            <article key={chapter.id} id={chapter.id} className="journey-chapter">
              <div className="journey-copy">
                <span className="journey-number">{chapter.number}</span>
                <p className="section-kicker">{chapter.eyebrow}</p>
                <h3>{chapter.title}</h3>
                <p>{chapter.body}</p>
              </div>
              <div className="journey-visual">
                {chapter.id === "discover" ? <DiscoverView /> : null}
                {chapter.id === "track" ? <TrackView /> : null}
                {chapter.id === "prepare" ? <PrepareView /> : null}
              </div>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

function DiscoverView() {
  return (
    <div className="product-frame" aria-label="Example of discovering roles in the Kuchup catalog">
      <div className="product-frame-bar">
        <strong>Role catalog</strong>
        <span>Updated 2h ago</span>
      </div>
      <div className="product-filter-row" aria-hidden="true">
        <span>Backend</span>
        <span>Germany</span>
        <span>All locations</span>
      </div>
      <div className="product-company">
        <div>
          <p className="product-company-name">Example company</p>
          <span>Berlin · Career page</span>
        </div>
        <Pill variant="country">Germany</Pill>
      </div>
      <div className="product-role">
        <div>
          <strong>Senior Backend Engineer</strong>
          <span>Platform · Full time</span>
        </div>
        <Pill variant="visa">Relocation focus</Pill>
      </div>
      <div className="product-role">
        <div>
          <strong>Software Engineer, Infrastructure</strong>
          <span>Cloud systems · Full time</span>
        </div>
        <span className="product-source">Direct source ↗</span>
      </div>
    </div>
  );
}

function TrackView() {
  return (
    <div className="product-frame" aria-label="Example of tracking an application in Kuchup">
      <div className="product-frame-bar">
        <strong>Your application path</strong>
        <span>Private workspace</span>
      </div>
      <div className="tracking-path">
        <div className="tracking-step is-complete">
          <span />
          <div>
            <strong>Looking to apply</strong>
            <p>Role saved with the company</p>
          </div>
        </div>
        <div className="tracking-step is-current">
          <span />
          <div>
            <strong>Applied</strong>
            <p>CV and application date attached</p>
          </div>
        </div>
        <div className="tracking-step">
          <span />
          <div>
            <strong>Awaiting response</strong>
            <p>The next decision stays visible</p>
          </div>
        </div>
      </div>
      <div className="tracking-pills" aria-label="Other available tracking states">
        <Pill variant="looking">Pinned</Pill>
        <Pill variant="not-for-me">Not for me</Pill>
        <Pill variant="rejected">Rejected</Pill>
      </div>
    </div>
  );
}

function PrepareView() {
  return (
    <div className="product-frame" aria-label="Example of preparing application documents in Kuchup">
      <div className="product-frame-bar">
        <strong>Application workspace</strong>
        <span>Review required</span>
      </div>
      <div className="prepare-document">
        <div className="prepare-heading">
          <span>JD mirror</span>
          <Pill variant="looking">In review</Pill>
        </div>
        <div className="prepare-line is-long" />
        <div className="prepare-line" />
        <div className="prepare-evidence">
          <span>MCP · Claude / Cursor</span>
          <strong>Project master · API platform</strong>
          <p>Agent reframes from verified project context — you approve each phase.</p>
        </div>
        <div className="prepare-actions">
          <span>Tailored CV</span>
          <span>Cover letter</span>
          <strong>You approve before use</strong>
        </div>
      </div>
    </div>
  );
}
