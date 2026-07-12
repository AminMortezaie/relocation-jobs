import type { Metadata } from "next";
import { Header } from "@/components/Header";
import { Footer } from "@/components/Footer";
import { Card } from "@/components/ui/Card";

export const metadata: Metadata = {
  title: "Pricing",
  description:
    "Plans and packages for Relocation Jobs — the curation-first visa-sponsored software role tracker. Free preview available; full board access and workspace tools coming soon.",
  openGraph: {
    title: "Pricing | Relocation Jobs",
    description:
      "Free public preview available. Paid plans for full board access, company workspaces, and CV reframe tools coming soon.",
    url: "https://kuchup.com/pricing",
    siteName: "Relocation Jobs",
    type: "website",
  },
};

export default function PricingPage() {
  return (
    <div className="min-h-screen">
      <div className="mx-auto max-w-site px-4 pb-8 pt-5 sm:px-5">
        <Header />
        <main className="mx-auto mt-12 max-w-2xl">
          <h1 className="text-fluid-hero text-text">Plans & Pricing</h1>
          <p className="mt-4 text-sm leading-relaxed text-muted">
            Relocation Jobs is in active development. The public preview is free
            for everyone. Paid packages for full board access, company workspace
            tools, and CV reframe pipeline are being designed.
          </p>

          <div className="mt-10 grid gap-5 sm:grid-cols-2">
            <Card className="px-5 py-6">
              <h2 className="text-lg font-semibold text-text">Free Preview</h2>
              <p className="mt-1 text-2xl font-bold text-text">$0</p>
              <ul className="mt-4 space-y-2 text-sm text-muted">
                <li>Public catalog overview</li>
                <li>Company preview cards</li>
                <li>Country-level stats</li>
                <li>Search public preview</li>
              </ul>
              <a
                href="/"
                className="btn-primary mt-6 inline-flex rounded-full px-4 py-2 text-sm font-semibold text-white"
              >
                Browse preview
              </a>
            </Card>

            <Card className="px-5 py-6" accentBar>
              <h2 className="text-lg font-semibold text-text">Full Access</h2>
              <p className="mt-1 text-2xl font-bold text-text">Coming soon</p>
              <ul className="mt-4 space-y-2 text-sm text-muted">
                <li>Full company board</li>
                <li>Per-user apply/reject tracking</li>
                <li>Company workspace + documents</li>
                <li>Tailored CV reframe pipeline</li>
                <li>Cover letter generation</li>
              </ul>
              <a
                href="/panel"
                className="btn-primary mt-6 inline-flex rounded-full px-4 py-2 text-sm font-semibold text-white"
              >
                Sign in for early access
              </a>
            </Card>
          </div>

          <p className="mt-8 text-center text-xs text-muted">
            Pricing details will be announced when the full access plan launches.
            Current users get grandfathered access.
          </p>
        </main>
        <Footer />
      </div>
    </div>
  );
}
