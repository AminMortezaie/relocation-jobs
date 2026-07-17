import type { Metadata } from "next";
import { Header } from "@/components/Header";
import { Footer } from "@/components/Footer";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";

export const metadata: Metadata = {
  title: "Visa-Sponsored Software Jobs in Germany",
  description:
    "Find software engineering jobs in Germany with visa sponsorship. Browse companies hiring in Berlin, Munich, and beyond. Relocation-friendly roles for international engineers.",
  openGraph: {
    title: "Visa-Sponsored Software Jobs in Germany | Relocation Jobs",
    description:
      "Software engineering roles in Germany with visa sponsorship. Browse Berlin, Munich, and remote-friendly companies hiring international engineers.",
    url: "https://kuchup.com/relocation-jobs-germany",
    siteName: "Relocation Jobs",
    type: "website",
  },
};

export default function GermanyPage() {
  return (
    <div className="min-h-screen">
      <div className="mx-auto max-w-site px-4 pb-8 pt-5 sm:px-5">
        <Header />
        <main className="mx-auto mt-12 max-w-2xl">
          <h1 className="text-fluid-hero text-text-primary">
            Visa-Friendly Software Jobs in Germany
          </h1>
          <p className="mt-4 text-base leading-relaxed text-text-secondary">
            Germany is one of Europe&apos;s strongest markets for visa-sponsored
            tech roles. With the EU Blue Card, a growing startup scene in Berlin,
            and established tech hubs in Munich and Hamburg, companies actively
            recruit software engineers from abroad.
          </p>

          <section className="mt-10 space-y-5">
            <h2 className="font-display text-2xl font-bold text-text-primary">Key tech hubs</h2>
            <ul className="space-y-3 text-sm text-text-secondary">
              <li><strong className="text-text-primary">Berlin</strong> — Startup capital, strong in fintech, e-commerce, and mobility.</li>
              <li><strong className="text-text-primary">Munich</strong> — Enterprise software, automotive tech, and SaaS.</li>
              <li><strong className="text-text-primary">Hamburg</strong> — E-commerce, logistics, and media technology.</li>
              <li><strong className="text-text-primary">Cologne / Dusseldorf</strong> — Media, telecom, and insurance tech.</li>
            </ul>
          </section>

          <section className="mt-10 space-y-5">
            <h2 className="font-display text-2xl font-bold text-text-primary">Visa pathways</h2>
            <Card className="px-5 py-4">
              <p className="text-sm leading-relaxed text-text-secondary">
                The EU Blue Card is the most common route for skilled software
                engineers. Germany also offers the Chancenkarte (Opportunity Card)
                for job seekers and the IT specialist visa for experienced
                professionals without a formal degree. Most employers on
                Relocation Jobs list visa sponsorship in their openings.
              </p>
            </Card>
          </section>

          <section className="mt-10 space-y-5">
            <h2 className="font-display text-2xl font-bold text-text-primary">What you&apos;ll find on Relocation Jobs</h2>
            <ul className="space-y-2 text-sm text-text-secondary">
              <li>Companies actively hiring software engineers in Germany</li>
              <li>Visa-friendly roles flagged per job opening</li>
              <li>Fresh data scraped every 6 hours from career pages</li>
              <li>Track applications and manage your search in one board</li>
            </ul>
          </section>

          <div className="mt-10 text-center">
            <Button as="a" href="/panel?country=germany" variant="primary">
              Browse Germany companies
            </Button>
          </div>
        </main>
        <Footer />
      </div>
    </div>
  );
}
