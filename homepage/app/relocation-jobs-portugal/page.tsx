import type { Metadata } from "next";
import { Header } from "@/components/Header";
import { Footer } from "@/components/Footer";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";

export const metadata: Metadata = {
  title: "Visa-Sponsored Software Jobs in Portugal",
  description:
    "Find software engineering jobs in Portugal with visa sponsorship. Browse companies hiring in Lisbon, Porto, and beyond. Tech jobs with D7 or tech visa support.",
  openGraph: {
    title: "Visa-Sponsored Software Jobs in Portugal | Relocation Jobs",
    description:
      "Software engineering roles in Portugal with visa support. Browse Lisbon and Porto companies hiring international engineers. Growing tech hub with competitive compensation.",
    url: "https://kuchup.com/relocation-jobs-portugal",
    siteName: "Relocation Jobs",
    type: "website",
  },
};

export default function PortugalPage() {
  return (
    <div className="min-h-screen">
      <div className="mx-auto max-w-site px-4 pb-8 pt-5 sm:px-5">
        <Header />
        <main className="mx-auto mt-12 max-w-2xl">
          <h1 className="text-fluid-hero text-text-primary">
            Visa-Friendly Software Jobs in Portugal
          </h1>
          <p className="mt-4 text-base leading-relaxed text-text-secondary">
            Portugal is one of Europe&apos;s fastest-growing tech destinations.
            With a relatively low cost of living, a favorable visa regime for
            digital workers (D7, tech visa), and a growing startup and scale-up
            scene in Lisbon and Porto, it has become a go-to market for
            international software engineers.
          </p>

          <section className="mt-10 space-y-5">
            <h2 className="font-display text-2xl font-bold text-text-primary">Key tech hubs</h2>
            <ul className="space-y-3 text-sm text-text-secondary">
              <li><strong className="text-text-primary">Lisbon</strong> — Scale-up capital, strong in fintech, SaaS, and remote-first companies.</li>
              <li><strong className="text-text-primary">Porto</strong> — Engineering hubs for global companies, strong in Java, .NET, and DevOps.</li>
              <li><strong className="text-text-primary">Braga / Coimbra</strong> — Growing satellite hubs with university talent pipelines.</li>
            </ul>
          </section>

          <section className="mt-10 space-y-5">
            <h2 className="font-display text-2xl font-bold text-text-primary">Visa pathways</h2>
            <Card className="px-5 py-4">
              <p className="text-sm leading-relaxed text-text-secondary">
                The D7 visa is popular for remote workers and freelancers, while
                the Tech Visa program helps companies fast-track sponsored hires.
                Portugal also offers a startup visa for entrepreneurs. Many
                international companies with Portuguese offices handle
                relocation end-to-end.
              </p>
            </Card>
          </section>

          <section className="mt-10 space-y-5">
            <h2 className="font-display text-2xl font-bold text-text-primary">What you&apos;ll find on Relocation Jobs</h2>
            <ul className="space-y-2 text-sm text-text-secondary">
              <li>Companies actively hiring software engineers in Portugal</li>
              <li>Visa-friendly roles flagged per job opening</li>
              <li>Fresh data scraped every 6 hours from career pages</li>
              <li>Track applications and manage your search in one board</li>
            </ul>
          </section>

          <div className="mt-10 text-center">
            <Button as="a" href="/panel?country=portugal" variant="primary">
              Browse Portugal companies
            </Button>
          </div>
        </main>
        <Footer />
      </div>
    </div>
  );
}
