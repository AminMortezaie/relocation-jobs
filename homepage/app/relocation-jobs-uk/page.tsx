import type { Metadata } from "next";
import { Header } from "@/components/Header";
import { Footer } from "@/components/Footer";
import { Card } from "@/components/ui/Card";

export const metadata: Metadata = {
  title: "Visa-Sponsored Software Jobs in the UK",
  description:
    "Find software engineering jobs in the United Kingdom with visa sponsorship. Browse companies hiring in London, Manchester, and beyond. Tech jobs with skilled worker visa support.",
  openGraph: {
    title: "Visa-Sponsored Software Jobs in the UK | Relocation Jobs",
    description:
      "Software engineering roles in the United Kingdom with visa sponsorship. Browse London, Manchester, and Edinburgh companies hiring international engineers.",
    url: "https://kuchup.com/relocation-jobs-uk",
    siteName: "Relocation Jobs",
    type: "website",
  },
};

export default function UkPage() {
  return (
    <div className="min-h-screen">
      <div className="mx-auto max-w-site px-4 pb-8 pt-5 sm:px-5">
        <Header />
        <main className="mx-auto mt-12 max-w-2xl">
          <h1 className="text-fluid-hero text-text">
            Visa-Friendly Software Jobs in the United Kingdom
          </h1>
          <p className="mt-4 text-sm leading-relaxed text-muted">
            London remains one of the world&apos;s largest tech hubs, and UK
            companies frequently sponsor Skilled Worker visas for software
            engineers. Beyond London, Manchester, Edinburgh, and Bristol have
            thriving tech ecosystems with strong hiring demand.
          </p>

          <section className="mt-10 space-y-5">
            <h2 className="text-lg font-semibold text-text">Key tech hubs</h2>
            <ul className="space-y-3 text-sm text-muted">
              <li><strong className="text-text">London</strong> — Fintech, Big Tech, and a dense SaaS ecosystem.</li>
              <li><strong className="text-text">Manchester</strong> — Growing startup scene, e-commerce, and media-tech.</li>
              <li><strong className="text-text">Edinburgh</strong> — Fintech, AI, and gaming studios.</li>
              <li><strong className="text-text">Bristol</strong> — Deep tech, aerospace-adjacent software, and semiconductor.</li>
            </ul>
          </section>

          <section className="mt-10 space-y-5">
            <h2 className="text-lg font-semibold text-text">Visa pathways</h2>
            <Card className="px-5 py-4">
              <p className="text-sm leading-relaxed text-muted">
                The Skilled Worker visa is the primary route for software
                engineers. Companies need a sponsor licence, and most UK tech
                employers on Relocation Jobs already hold one. The Global Talent
                visa is also available for exceptional engineers.
              </p>
            </Card>
          </section>

          <section className="mt-10 space-y-5">
            <h2 className="text-lg font-semibold text-text">What you&apos;ll find on Relocation Jobs</h2>
            <ul className="space-y-2 text-sm text-muted">
              <li>Companies actively hiring software engineers in the UK</li>
              <li>Visa-friendly roles flagged per job opening</li>
              <li>Fresh data scraped every 6 hours from career pages</li>
              <li>Track applications and manage your search in one board</li>
            </ul>
          </section>

          <div className="mt-10 text-center">
            <a
              href="/panel?country=uk"
              className="btn-primary inline-flex rounded-full px-6 py-3 text-sm font-semibold text-white"
            >
              Browse UK companies
            </a>
          </div>
        </main>
        <Footer />
      </div>
    </div>
  );
}
