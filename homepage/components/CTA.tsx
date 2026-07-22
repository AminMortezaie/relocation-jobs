import { Button } from "@/components/ui/Button";

export function CTA() {
  return (
    <section className="landing-close" aria-labelledby="cta-heading">
      <div className="landing-shell landing-close-inner">
        <div>
          <p className="section-kicker">Take the next step</p>
          <h2 id="cta-heading" className="text-section-display text-text-primary">
            The move is complex. Your search does not have to be.
          </h2>
          <p>
            Start with the public catalog, carry the roles that matter into
            one workspace, and connect Claude or Cursor via MCP when you are
            ready to prepare.
          </p>
        </div>
        <div className="landing-close-actions">
          <Button as="a" href="/panel" variant="primary">Open the board</Button>
          <Button as="a" href="/mcp" variant="secondary">Explore MCP</Button>
          <a href="#search" className="text-link">Return to search <span aria-hidden="true">↑</span></a>
        </div>
      </div>
    </section>
  );
}
