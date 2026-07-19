"use client";

import { useEffect, useState } from "react";
import { useSearchFlow } from "@/components/SearchFlowContext";
import { Card } from "@/components/ui/Card";
import { Pill } from "@/components/ui/Pill";
import { filtersToQuery, panelHref } from "@/lib/search";

type PreviewCompany = {
  name: string;
  country: string;
  country_label: string;
  city?: string;
  job_count: number;
  visa_job_count: number;
  latest_fetched?: string;
};

export function SearchResults() {
  const { filters } = useSearchFlow();
  const [companies, setCompanies] = useState<PreviewCompany[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!filters) return;

    let cancelled = false;
    setLoading(true);
    setError(null);

    const params = filtersToQuery(filters);
    params.set("limit", "24");
    const url = `/api/public/preview?${params.toString()}`;

    fetch(url)
      .then((res) => {
        if (!res.ok) throw new Error("preview fetch failed");
        return res.json();
      })
      .then((payload) => {
        if (cancelled) return;
        const rows = (payload.companies || [])
          .filter((c: PreviewCompany) => c.job_count > 0)
          .slice(0, 12);
        setCompanies(rows);
      })
      .catch(() => {
        if (cancelled) return;
        setError("Could not load companies right now. Try again in a moment.");
        setCompanies([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [filters]);

  if (!filters) {
    return null;
  }

  const summary = [
    filters.q ? filters.q : null,
    filters.country !== "all" ? filters.country : null,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <section
      id="search-results"
      className="section-compact scroll-mt-6"
      aria-labelledby="search-results-heading"
      aria-live="polite"
    >
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 id="search-results-heading" className="text-section-title text-text-primary">
            {loading ? "Searching catalog…" : "Companies hiring abroad"}
          </h2>
          <p className="mt-1 text-sm font-normal text-text-secondary">
            {summary
              ? `Preview for ${summary} — sign in to see open roles.`
              : "Preview from the shared catalog — sign in to see open roles."}
          </p>
        </div>
        <a href={panelHref(filters)} className="pill-control text-sm font-semibold">
          Sign in for full board →
        </a>
      </div>

      {error ? (
        <div className="card rounded-app px-4 py-6 text-sm text-text-muted">{error}</div>
      ) : null}

      {!error && loading ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {[0, 1, 2].map((key) => (
            <div
              key={key}
            className="card h-40 animate-pulse rounded-app"
              aria-hidden="true"
            />
          ))}
        </div>
      ) : null}

      {!error && !loading && companies.length === 0 ? (
        <div className="card rounded-app px-4 py-8 text-center">
          <p className="text-sm font-medium text-text-primary">No matching companies in the preview.</p>
          <p className="mt-2 text-sm font-normal text-text-secondary">
            Try a broader search or country, or sign in to browse the full board.
          </p>
          <a
            href={panelHref(filters)}
            className="btn-primary mt-4 inline-flex rounded-app px-4 py-2 text-sm font-semibold text-text-on-accent"
          >
            Sign in
          </a>
        </div>
      ) : null}

      {!error && !loading && companies.length > 0 ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {companies.map((company) => (
            <Card key={`${company.country}-${company.name}`} accentBar className="flex h-full flex-col p-4 pl-5">
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <h3 className="font-display text-xl font-bold tracking-[-0.02em] text-text-primary">
                  {company.name}
                </h3>
                <Pill variant="country">{company.country_label || company.country}</Pill>
                {company.visa_job_count > 0 ? (
                  <Pill variant="visa">Visa-friendly</Pill>
                ) : null}
              </div>
              <p className="text-xs font-medium tracking-[0.02em] text-text-muted">
                {company.job_count} open role{company.job_count !== 1 ? "s" : ""}
                {company.city ? ` · ${company.city}` : ""}
              </p>
              <p className="mt-3 border-t border-border-subtle pt-3 text-sm font-normal text-text-secondary">
                Sign in to see positions and track applications.
              </p>
              <a
                href={panelHref(filters)}
                className="mt-3 inline-flex text-sm font-medium text-accent-primary hover:text-accent-primary-hover"
              >
                Sign in to see roles →
              </a>
            </Card>
          ))}
        </div>
      ) : null}
    </section>
  );
}
