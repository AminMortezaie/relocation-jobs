import { Button } from "@/components/ui/Button";

const POINTS = [
  "Load job context and JD text from your Kuchup catalog",
  "Run a gated CV reframe in Claude or Cursor — you approve each phase",
  "Keep tailored LaTeX and PDFs in the company workspace",
  "You submit. Kuchup never auto-applies.",
] as const;

export function McpFeature() {
  return (
    <section
      id="mcp"
      className="landing-band landing-band-mcp"
      aria-labelledby="mcp-feature-heading"
    >
      <div className="landing-shell section-major mcp-feature">
        <header className="mcp-feature-intro">
          <p className="section-kicker">Claude &amp; Cursor MCP</p>
          <h2
            id="mcp-feature-heading"
            className="text-section-display text-text-primary"
          >
            Tailor every application with your agent — connected to Kuchup.
          </h2>
          <p className="section-lede">
            Connect the Kuchup MCP server so Claude or Cursor can work against
            your real board, masters, and project evidence. Preparation stays in
            your workspace; submission stays with you.
          </p>
        </header>

        <ul className="mcp-feature-points">
          {POINTS.map((point) => (
            <li key={point}>{point}</li>
          ))}
        </ul>

        <div className="mcp-feature-actions">
          <Button as="a" href="/mcp" variant="primary">
            Explore MCP
          </Button>
          <Button as="a" href="/apply" variant="secondary">
            Connect in workspace
          </Button>
        </div>
      </div>
    </section>
  );
}
