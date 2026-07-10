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
  preview_jobs: { title?: string }[];
};

function companyHasPositions(company: PreviewCompany) {
  return (company.preview_jobs || []).some((job) => (job.title || "").trim());
}

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
        const rows = (payload.companies || []).filter(companyHasPositions).slice(0, 12);
        setCompanies(rows);
      })
      .catch(() => {
        if (cancelled) return;
        setError("Could not load roles right now. Try again in a moment.");
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
          <h2 id="search-results-heading" className="text-section-title text-text">
            {loading ? "Searching catalog…" : "Matching roles"}
          </h2>
          <p className="mt-1 text-sm font-normal text-muted">
            {summary
              ? `Preview for ${summary} — live from the shared catalog.`
              : "Preview from the shared catalog."}
          </p>
        </div>
        <a href={panelHref(filters)} className="pill-control text-sm font-semibold">
          Track in panel →
        </a>
      </div>

      {error ? (
        <div className="surface-card rounded-app px-4 py-6 text-sm text-muted">{error}</div>
      ) : null}

      {!error && loading ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {[0, 1, 2].map((key) => (
            <div
              key={key}
              className="surface-card h-40 animate-pulse rounded-app"
              aria-hidden="true"
            />
          ))}
        </div>
      ) : null}

      {!error && !loading && companies.length === 0 ? (
        <div className="surface-card rounded-app px-4 py-8 text-center">
          <p className="text-sm font-medium text-text">No matching roles in the preview.</p>
          <p className="mt-2 text-sm font-normal text-muted">
            Try a broader role or country, or sign in to search the full board.
          </p>
          <a
            href={panelHref(filters)}
            className="btn-primary mt-4 inline-flex rounded-full px-4 py-2 text-sm font-semibold text-white"
          >
            Open full board
          </a>
        </div>
      ) : null}

      {!error && !loading && companies.length > 0 ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {companies.map((company) => (
            <Card key={`${company.country}-${company.name}`} accentBar className="flex h-full flex-col p-4 pl-5">
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <h3 className="text-base font-semibold tracking-[-0.02em] text-text">
                  {company.name}
                </h3>
                <Pill variant="country">{company.country_label || company.country}</Pill>
                {company.visa_job_count > 0 ? (
                  <Pill variant="visa">Visa-friendly</Pill>
                ) : null}
              </div>
              <p className="text-xs font-normal text-muted">
                {company.job_count} open roles
                {company.city ? ` · ${company.city}` : ""}
              </p>
              {company.preview_jobs.length > 0 ? (
                <ul className="mt-3 space-y-2 border-t border-white/[0.07] pt-3">
                  {company.preview_jobs.map((job) => (
                    <li key={job.title} className="text-sm font-normal text-text/90">
                      {job.title}
                    </li>
                  ))}
                </ul>
              ) : null}
              <a
                href={panelHref(filters)}
                className="mt-4 inline-flex text-sm font-medium text-accent-hover hover:text-text"
              >
                Track applications →
              </a>
            </Card>
          ))}
        </div>
      ) : null}
    </section>
  );
}
