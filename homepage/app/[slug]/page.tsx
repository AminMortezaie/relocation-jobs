import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Header } from "@/components/Header";
import { Footer } from "@/components/Footer";
import { Button } from "@/components/ui/Button";
import { COUNTRY_LABELS, countryLabel } from "@/lib/countries";

type PageProps = {
  params: Promise<{ slug: string }>;
};

function countryKeyFromSlug(slug: string): string | null {
  const prefix = "relocation-jobs-";
  if (!slug.startsWith(prefix)) {
    return null;
  }
  const key = slug.slice(prefix.length);
  return key && countryLabel(key) ? key : null;
}

export function generateStaticParams() {
  return Object.keys(COUNTRY_LABELS).map((country) => ({
    slug: `relocation-jobs-${country}`,
  }));
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { slug } = await params;
  const country = countryKeyFromSlug(slug);
  if (!country) {
    return { title: "Not found" };
  }
  const label = countryLabel(country)!;
  const title = `Visa-Sponsored Software Jobs in ${label}`;
  const description = `Find software engineering jobs in ${label} with visa sponsorship. Browse relocation-friendly companies hiring international engineers.`;
  return {
    title,
    description,
    openGraph: {
      title: `${title} | Relocation Jobs`,
      description,
      url: `https://kuchup.com/relocation-jobs-${country}`,
      siteName: "Relocation Jobs",
      type: "website",
    },
  };
}

export default async function CountryJobsPage({ params }: PageProps) {
  const { slug } = await params;
  const country = countryKeyFromSlug(slug);
  if (!country) {
    notFound();
  }
  const label = countryLabel(country)!;

  return (
    <div className="min-h-screen">
      <div className="mx-auto max-w-site px-4 pb-8 pt-5 sm:px-5">
        <Header />
        <main className="mx-auto mt-12 max-w-2xl">
          <h1 className="text-fluid-hero text-text-primary">
            Visa-Friendly Software Jobs in {label}
          </h1>
          <p className="mt-4 text-base leading-relaxed text-text-secondary">
            Browse visa-sponsored software engineering roles in {label}. Relocation
            Jobs tracks companies that hire internationally and refresh career-page
            data regularly so you can focus on applying.
          </p>
          <div className="mt-10 text-center">
            <Button as="a" href={`/panel?country=${country}`} variant="primary">
              Browse {label} companies
            </Button>
          </div>
        </main>
        <Footer />
      </div>
    </div>
  );
}
