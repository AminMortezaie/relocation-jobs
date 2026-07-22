import type { Metadata } from "next";
import { Header } from "@/components/Header";
import { Footer } from "@/components/Footer";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";

const FLOW_STEPS = [
  {
    title: "Pin roles worth applying to",
    body: "On the board, mark jobs as pinned or looking to apply. Those roles become the queue your agent can load — with company, title, and catalog job description.",
  },
  {
    title: "Reframe with checkpoints",
    body: "In Claude or Cursor, the agent runs a gated CV reframe: one phase at a time, with your approval before the next. Masters and project evidence stay in your workspace.",
  },
  {
    title: "Review the PDF, then you submit",
    body: "Tailored LaTeX lands in the company workspace. Re-render the PDF on the panel, check every claim, and upload it yourself. Kuchup never auto-applies.",
  },
] as const;

const CAPABILITIES = [
  {
    title: "Queue and job context",
    body: "List pinned roles, load JD text from the catalog, and keep tracking flags in sync with the panel.",
  },
  {
    title: "Masters and reframe pipeline",
    body: "Store master resumes and project evidence, then run ordered pipeline prompts with go-ahead checkpoints.",
  },
  {
    title: "CV and cover letter PDFs",
    body: "Save tailored LaTeX, validate structure against your master, and render PDFs in the company workspace.",
  },
  {
    title: "Catalog helpers",
    body: "Add companies or positions, attach job descriptions, and mark a role applied when you have submitted.",
  },
] as const;

const FAQ_ITEMS = [
  {
    question: "What is MCP?",
    answer:
      "Model Context Protocol lets Claude, Cursor, and similar clients call tools on a server you connect. Kuchup’s MCP server exposes your board, resumes, and application artifacts so the agent can prepare materials — not browse the open web for you.",
  },
  {
    question: "Do I need Claude or Cursor?",
    answer:
      "Yes for the interactive reframe flow. Connect the remote MCP URL in Claude (custom connectors, including mobile) or Cursor. You still use the Kuchup panel to track roles and preview PDFs.",
  },
  {
    question: "Is my data private?",
    answer:
      "Application profile, master resumes, project masters, and tailored documents are stored per user in Postgres. Nothing sensitive is committed to the public repository. Access to MCP requires your account (OAuth or a personal API token from Connect MCP).",
  },
  {
    question: "Will it submit applications for me?",
    answer:
      "No. Kuchup prepares tailored CVs and cover letters and updates tracking when you ask. You review the PDF and submit on the employer’s site yourself.",
  },
] as const;

export const metadata: Metadata = {
  title: "MCP for Claude and Cursor",
  description:
    "Connect Kuchup’s MCP server to Claude or Cursor to tailor CVs for visa-sponsored software roles. Load job context from the catalog, run a gated reframe pipeline, and keep PDFs in your workspace — without auto-apply.",
  openGraph: {
    title: "MCP for Claude and Cursor | Relocation Jobs",
    description:
      "Claude MCP and Cursor MCP for job applications: queue roles, reframe your CV with approval checkpoints, and render PDFs in Kuchup.",
    url: "https://kuchup.com/mcp",
    siteName: "Relocation Jobs",
    type: "website",
  },
};

export default function McpPage() {
  const faqJsonLd = {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: FAQ_ITEMS.map((item) => ({
      "@type": "Question",
      name: item.question,
      acceptedAnswer: {
        "@type": "Answer",
        text: item.answer,
      },
    })),
  };

  return (
    <div className="min-h-screen">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(faqJsonLd) }}
      />
      <div className="mx-auto max-w-site px-4 pb-8 pt-5 sm:px-5">
        <Header />
        <main className="mx-auto mt-12 max-w-2xl">
          <p className="section-kicker">Kuchup MCP</p>
          <h1 className="text-fluid-hero text-text-primary">
            MCP for job applications
          </h1>
          <p className="mt-4 text-base leading-relaxed text-text-secondary">
            Connect Claude or Cursor to Kuchup so your agent can load real job
            context from the catalog, reframe your CV with your approval, and
            leave tailored PDFs in your workspace — ready for you to send.
          </p>
          <div className="mt-6 flex flex-wrap items-center gap-3">
            <Button as="a" href="/apply" variant="primary">
              Connect in workspace
            </Button>
            <Button as="a" href="/how-it-works" variant="secondary">
              How the product works
            </Button>
          </div>

          <section className="mt-12" aria-labelledby="what-it-does-heading">
            <h2
              id="what-it-does-heading"
              className="font-display text-2xl font-semibold text-text-primary"
            >
              What it does
            </h2>
            <p className="mt-3 text-sm leading-relaxed text-text-secondary">
              The MCP assistant prepares application material. It does not
              submit forms, scrape employer sites in chat, or invent experience
              you have not approved.
            </p>
            <ol className="workflow mt-8">
              {FLOW_STEPS.map((step, index) => (
                <li key={step.title} className="workflow-step">
                  <span className="workflow-number" aria-hidden="true">
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <Card className="workflow-card px-5 py-6">
                    <p className="workflow-label">Step {index + 1}</p>
                    <h3 className="font-display text-xl font-semibold text-text-primary">
                      {step.title}
                    </h3>
                    <p className="mt-2 text-sm leading-relaxed text-text-secondary">
                      {step.body}
                    </p>
                  </Card>
                </li>
              ))}
            </ol>
          </section>

          <section className="mt-12" aria-labelledby="connect-heading">
            <h2
              id="connect-heading"
              className="font-display text-2xl font-semibold text-text-primary"
            >
              How to connect
            </h2>
            <Card className="mt-5 px-5 py-6">
              <p className="text-sm leading-relaxed text-text-secondary">
                Production endpoint (Streamable HTTP + OAuth):
              </p>
              <p className="mt-3 break-all font-mono text-sm font-medium text-text-primary">
                https://mcp.kuchup.com/mcp
              </p>
              <p className="mt-4 text-sm leading-relaxed text-text-secondary">
                Add that URL as a Claude custom connector or Cursor MCP server.
                Sign in when prompted, or create an API token under{" "}
                <strong className="font-semibold text-text-primary">
                  Connect MCP
                </strong>{" "}
                on the Application data page after you sign in.
              </p>
              <p className="mt-3 text-sm leading-relaxed text-text-secondary">
                Power users can also run a local stdio MCP server against their
                own account for Claude Desktop on a laptop.
              </p>
              <Button as="a" href="/apply" variant="secondary" className="mt-5">
                Open Application data
              </Button>
            </Card>
          </section>

          <section className="mt-12" aria-labelledby="capabilities-heading">
            <h2
              id="capabilities-heading"
              className="font-display text-2xl font-semibold text-text-primary"
            >
              Capabilities
            </h2>
            <div className="mt-5 grid gap-4 sm:grid-cols-2">
              {CAPABILITIES.map((item) => (
                <Card key={item.title} className="px-5 py-5">
                  <h3 className="font-display text-lg font-semibold text-text-primary">
                    {item.title}
                  </h3>
                  <p className="mt-2 text-sm leading-relaxed text-text-secondary">
                    {item.body}
                  </p>
                </Card>
              ))}
            </div>
          </section>

          <section className="mt-12" aria-labelledby="mcp-faq-heading">
            <h2
              id="mcp-faq-heading"
              className="font-display text-2xl font-semibold text-text-primary"
            >
              Questions
            </h2>
            <div className="faq-list mt-5">
              {FAQ_ITEMS.map((item) => (
                <details key={item.question}>
                  <summary>
                    <span>{item.question}</span>
                    <span className="faq-marker" aria-hidden="true">
                      +
                    </span>
                  </summary>
                  <p>{item.answer}</p>
                </details>
              ))}
            </div>
          </section>

          <div className="mt-12 flex flex-wrap items-center justify-center gap-3 text-center">
            <Button as="a" href="/panel" variant="primary">
              Sign in to the board
            </Button>
            <Button as="a" href="/apply" variant="secondary">
              Set up MCP
            </Button>
          </div>
        </main>
        <Footer />
      </div>
    </div>
  );
}
