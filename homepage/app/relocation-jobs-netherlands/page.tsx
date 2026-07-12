import type { Metadata } from "next";
import { Header } from "@/components/Header";
import { Footer } from "@/components/Footer";
import { Card } from "@/components/ui/Card";

export const metadata: Metadata = {
  title: "Visa-Sponsored Software Jobs in the Netherlands",
  description:
    "Find software engineering jobs in the Netherlands with visa sponsorship. Browse companies hiring in Amsterdam, Utrecht, and Eindhoven. Relocation-friendly roles for international engineers.",
  openGraph: {
    title: "Visa-Sponsored Software Jobs in the Netherlands | Relocation Jobs",
    description:
      "Software engineering roles in the Netherlands with visa sponsorship. Browse Amsterdam, Utrecht, and Eindhoven companies hiring international engineers.",
    url: "https://kuchup.com/relocation-jobs-netherlands",
    siteName: "Relocation Jobs",
    type: "website",
  },
};

export default function NetherlandsPage() {
  return (
    <div className="min-h-screen">
      <div className="mx-auto max-w-site px-4 pb-8 pt-5 sm:px-5">
        <Header />
        <main className="mx-auto mt-12 max-w-2xl">
          <h1 className="text-fluid-hero text-text">
            Visa-Friendly Software Jobs in the Netherlands
          </h1>
          <p className="mt-4 text-sm leading-relaxed text-muted">
            The Netherlands is a top destination for software engineers seeking
            relocation. The 30% tax ruling, English-friendly work culture, and
            strong tech sector — particularly in Amsterdam — make it one of
            Europe&apos;s most accessible markets for international talent.
          </p>

          <section className="mt-10 space-y-5">
            <h2 className="text-lg font-semibold text-text">Key tech hubs</h2>
            <ul className="space-y-3 text-sm text-muted">
              <li><strong className="text-text">Amsterdam</strong> — Fintech, SaaS, and Big Tech EMEA headquarters.</li>
              <li><strong className="text-text">Utrecht</strong> — Software platforms and gaming.</li>
              <li><strong className="text-text">Eindhoven</strong> — High-tech hardware-software integration and chip-adjacent roles.</li>
              <li><strong className="text-text">Rotterdam / The Hague</strong> — Port logistics, energy tech, and govtech.</li>
            </ul>
          </section>

          <section className="mt-10 space-y-5">
            <h2 className="text-lg font-semibold text-text">Visa pathways</h2>
            <Card className="px-5 py-4">
              <p className="text-sm leading-relaxed text-muted">
                The highly skilled migrant visa (kennismigrant) is the standard
                route for tech workers. Companies must be a recognized sponsor,
                and most employers on Relocation Jobs meet this requirement. The
                30% tax reimbursement makes the effective take-home pay
                significantly higher.
              </p>
            </Card>
          </section>

          <section className="mt-10 space-y-5">
            <h2 className="text-lg font-semibold text-text">What you&apos;ll find on Relocation Jobs</h2>
            <ul className="space-y-2 text-sm text-muted">
              <li>Companies actively hiring software engineers in the Netherlands</li>
              <li>Visa-friendly roles flagged per job opening</li>
              <li>Fresh data scraped every 6 hours from career pages</li>
              <li>Track applications and manage your search in one board</li>
            </ul>
          </section>

          <div className="mt-10 text-center">
            <a
              href="/panel?country=netherlands"
              className="btn-primary inline-flex rounded-full px-6 py-3 text-sm font-semibold text-white"
            >
              Browse Netherlands companies
            </a>
          </div>
        </main>
        <Footer />
      </div>
    </div>
  );
}
