import type { Metadata } from "next";
import { Header } from "@/components/Header";
import { Footer } from "@/components/Footer";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";

export const metadata: Metadata = {
  title: "Visa-Sponsored Software Jobs in Ireland",
  description:
    "Find software engineering jobs in Ireland with visa sponsorship. Browse companies hiring in Dublin, Cork, and Galway. Relocation-friendly roles for international engineers.",
  openGraph: {
    title: "Visa-Sponsored Software Jobs in Ireland | Relocation Jobs",
    description:
      "Software engineering roles in Ireland with visa sponsorship. Browse Dublin, Cork, and remote-friendly companies hiring international engineers.",
    url: "https://kuchup.com/relocation-jobs-ireland",
    siteName: "Relocation Jobs",
    type: "website",
  },
};

export default function IrelandPage() {
  return (
    <div className="min-h-screen">
      <div className="mx-auto max-w-site px-4 pb-8 pt-5 sm:px-5">
        <Header />
        <main className="mx-auto mt-12 max-w-2xl">
          <h1 className="text-fluid-hero text-text-primary">
            Visa-Friendly Software Jobs in Ireland
          </h1>
          <p className="mt-4 text-base leading-relaxed text-text-secondary">
            Ireland is a major European tech hub for international engineers.
            Multinationals and scale-ups in Dublin actively sponsor Critical Skills
            Employment Permits, and English-speaking workplaces make relocation
            smoother for many candidates.
          </p>

          <section className="mt-10 space-y-5">
            <h2 className="font-display text-2xl font-bold text-text-primary">Key tech hubs</h2>
            <ul className="space-y-3 text-sm text-text-secondary">
              <li>
                <strong className="text-text-primary">Dublin</strong> — Largest
                cluster: cloud, fintech, SaaS, and enterprise software.
              </li>
              <li>
                <strong className="text-text-primary">Cork</strong> — Growing
                engineering base with pharma-adjacent tech and product teams.
              </li>
              <li>
                <strong className="text-text-primary">Galway</strong> — Medtech,
                medical devices, and product engineering roles.
              </li>
              <li>
                <strong className="text-text-primary">Limerick</strong> — Hardware,
                manufacturing tech, and shared-services engineering.
              </li>
            </ul>
          </section>

          <section className="mt-10 space-y-5">
            <h2 className="font-display text-2xl font-bold text-text-primary">Visa pathways</h2>
            <Card className="px-5 py-4">
              <p className="text-sm leading-relaxed text-text-secondary">
                The Critical Skills Employment Permit is the most common route for
                software engineers on Ireland&apos;s shortage list. Employers may
                also use the General Employment Permit. Most companies on
                Relocation Jobs flag visa sponsorship in their openings.
              </p>
            </Card>
          </section>

          <section className="mt-10 space-y-5">
            <h2 className="font-display text-2xl font-bold text-text-primary">
              What you&apos;ll find on Relocation Jobs
            </h2>
            <ul className="space-y-2 text-sm text-text-secondary">
              <li>Companies actively hiring software engineers in Ireland</li>
              <li>Visa-friendly roles flagged per job opening</li>
              <li>Fresh data scraped every 6 hours from career pages</li>
              <li>Track applications and manage your search in one board</li>
            </ul>
          </section>

          <div className="mt-10 text-center">
            <Button as="a" href="/panel?country=ireland" variant="primary">
              Browse Ireland companies
            </Button>
          </div>
        </main>
        <Footer />
      </div>
    </div>
  );
}
