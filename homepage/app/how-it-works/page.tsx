import type { Metadata } from "next";
import { Header } from "@/components/Header";
import { Footer } from "@/components/Footer";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";

export const metadata: Metadata = {
  title: "How It Works",
  description:
    "Relocation Jobs tracks visa-friendly software engineering roles across Europe. Search the public preview, then sign in to track applications, manage company workspaces, and tailor your CV per job.",
  openGraph: {
    title: "How It Works | Relocation Jobs",
    description:
      "Search the public preview, sign in to track applications and manage your job search across Germany, Netherlands, UK, Portugal, and Ireland.",
    url: "https://kuchup.com/how-it-works",
    siteName: "Relocation Jobs",
    type: "website",
  },
};

export default function HowItWorksPage() {
  return (
    <div className="min-h-screen">
      <div className="mx-auto max-w-site px-4 pb-8 pt-5 sm:px-5">
        <Header />
        <main className="mx-auto mt-12 max-w-2xl">
          <h1 className="text-fluid-hero text-text-primary">How It Works</h1>
          <p className="mt-4 text-base leading-relaxed text-text-secondary">
            Relocation Jobs is a curated search tool for software engineers
            looking for visa-sponsored roles in Europe. We scrape company career
            pages every 6 hours so you see openings as they appear — not
            listings syndicated from aggregators.
          </p>

          <section className="mt-10 space-y-6">
            <Card className="px-5 py-6">
              <h2 className="font-display text-xl font-bold text-text-primary">
                1. Browse the public preview
              </h2>
              <p className="mt-2 text-sm leading-relaxed text-text-secondary">
                See which countries and companies are actively hiring. The
                homepage shows a live overview of supported countries and sampled
                company preview cards — no sign-in required.
              </p>
            </Card>

            <Card className="px-5 py-6">
              <h2 className="font-display text-xl font-bold text-text-primary">
                2. Sign in to unlock tracking
              </h2>
              <p className="mt-2 text-sm leading-relaxed text-text-secondary">
                Once you sign in, the full board is available: company-level
                tracking, per-user state for every role, apply/reject/not-for-me
                buckets, and a company workspace to store CVs and application
                documents.
              </p>
            </Card>

            <Card className="px-5 py-6">
              <h2 className="font-display text-xl font-bold text-text-primary">
                3. Tailor your CV per job
              </h2>
              <p className="mt-2 text-sm leading-relaxed text-text-secondary">
                Use the built-in reframe pipeline to align your CV with specific
                job descriptions. Project masters, cover letters, and LaTeX
                exports — all inside the workspace.
              </p>
            </Card>

            <Card className="px-5 py-6">
              <h2 className="font-display text-xl font-bold text-text-primary">
                4. Stay current
              </h2>
              <p className="mt-2 text-sm leading-relaxed text-text-secondary">
                The catalog refreshes automatically every 6 hours. New roles from
                company career pages appear in the board the same day. No stale
                syndicated listings.
              </p>
            </Card>
          </section>

          <div className="mt-10 text-center">
            <Button as="a" href="/panel" variant="primary">
              Sign in to start tracking
            </Button>
          </div>
        </main>
        <Footer />
      </div>
    </div>
  );
}
