"use client";

import { useEffect, useState } from "react";
import { useSearchFlow } from "@/components/SearchFlowContext";
import { filtersToQuery, panelHref } from "@/lib/search";

type FeaturedCompany = {
  name: string;
  country: string;
  country_label: string;
  city?: string;
  careers_url?: string;
  visa_role_count: number;
};

const FILTER_LABELS: Record<string, string> = {
  backend: "Backend",
  python: "Python",
  go: "Go",
  java: "Java",
  react: "React / Frontend",
  devops: "DevOps / Platform",
  germany: "Germany",
  netherlands: "Netherlands",
  uk: "UK",
  portugal: "Portugal",
  ireland: "Ireland",
};

export function SearchResults() {
  const { filters, onSearch } = useSearchFlow();
  const [featuredCompanies, setFeaturedCompanies] = useState<FeaturedCompany[]>([]);
  const [featuredScope, setFeaturedScope] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!filters) return;

    let cancelled = false;
    setLoading(true);
    setError(null);

    const params = filtersToQuery(filters);
    params.set("limit", "8");
    const url = `/api/public/preview?${params.toString()}`;

    fetch(url)
      .then((res) => {
        if (!res.ok) throw new Error("preview fetch failed");
        return res.json();
      })
      .then((payload) => {
        if (cancelled) return;
        setFeaturedCompanies((payload.featured_companies || []).slice(0, 3));
        setFeaturedScope(payload.meta?.featured_scope || "");
      })
      .catch(() => {
        if (cancelled) return;
        setError("We could not load companies right now.");
        setFeaturedCompanies([]);
        setFeaturedScope("");
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

  const countryLabel =
    filters.country !== "all"
      ? FILTER_LABELS[filters.country] || filters.country
      : null;

  const subtitle = loading
    ? "Checking companies with positive visa or relocation language."
    : featuredScope === "global" && countryLabel
      ? `No visa-positive companies in ${countryLabel} yet. Showing sponsors from other locations.`
      : countryLabel
        ? `Visa-positive companies in ${countryLabel}.`
        : "Companies currently showing positive visa or relocation signals.";

  return (
    <section
      id="search-results"
      className="visa-results section-compact scroll-mt-6"
      aria-labelledby="search-results-heading"
      aria-live="polite"
    >
      <div className="visa-results-head">
        <div className="visa-results-title">
          <span className="visa-results-status" aria-hidden="true">
            <ShieldCheckIcon />
          </span>
          <div>
            <h2 id="search-results-heading" className="text-section-title text-text-primary">
              {loading ? "Finding companies…" : "Companies worth exploring"}
            </h2>
            <p>{subtitle}</p>
          </div>
        </div>
        <a href={panelHref(filters)} className="visa-results-board-link">
          Browse all
          <ArrowIcon />
        </a>
      </div>

      {!loading && !error ? (
        <p className="visa-results-note">
          <InfoIcon />
          Based on positive visa or relocation language in current job descriptions.
        </p>
      ) : null}

      {error ? (
        <div className="visa-results-state" role="alert">
          <span className="visa-results-state-icon">
            <AlertIcon />
          </span>
          <div>
            <h3>Results are temporarily unavailable</h3>
            <p>{error} Your search is saved, so it is safe to try again.</p>
          </div>
          <button
            type="button"
            className="btn-secondary visa-results-state-action"
            onClick={() => onSearch({ ...filters })}
          >
            Try again
          </button>
        </div>
      ) : null}

      {!error && loading ? (
        <div className="visa-featured-list" aria-hidden="true">
          {[0, 1, 2].map((key) => (
            <div key={key} className="visa-featured-card visa-featured-skeleton">
              <span />
              <span />
              <span />
              <span />
            </div>
          ))}
        </div>
      ) : null}

      {!error && !loading && featuredCompanies.length > 0 ? (
        <div className="visa-featured-list">
          {featuredCompanies.map((company) => {
            const location =
              company.city || company.country_label || company.country;
            const openingsHref = panelHref({
              country: company.country,
              q: company.name,
            });
            const roleLabel = `${company.visa_role_count} visa-positive role${
              company.visa_role_count === 1 ? "" : "s"
            }`;

            return (
              <article
                key={`${company.country}-${company.name}`}
                className="visa-featured-card"
              >
                <div className="visa-featured-card-top">
                  <span className="visa-featured-mark" aria-hidden="true">
                    {company.name.slice(0, 1).toUpperCase()}
                  </span>
                  <span className="visa-featured-signal">
                    <ShieldCheckIcon />
                    Visa signal
                  </span>
                </div>

                <div className="visa-featured-copy">
                  <h3>{company.name}</h3>
                  <p className="visa-featured-location">
                    <LocationIcon />
                    <span>{location}</span>
                  </p>
                </div>

                <p className="visa-featured-count">
                  <strong>{company.visa_role_count}</strong>
                  <span>
                    visa-positive role
                    {company.visa_role_count === 1 ? "" : "s"}
                  </span>
                </p>

                <div className="visa-featured-actions">
                  <a
                    href={openingsHref}
                    className="visa-featured-primary"
                    aria-label={`View openings at ${company.name}`}
                  >
                    View openings
                    <ArrowIcon />
                  </a>
                  {company.careers_url ? (
                    <a
                      href={company.careers_url}
                      className="visa-featured-secondary"
                      target="_blank"
                      rel="noreferrer"
                      aria-label={`Open ${company.name} careers page`}
                    >
                      Careers page
                      <ExternalIcon />
                    </a>
                  ) : null}
                </div>

                <span className="sr-only">{roleLabel}</span>
              </article>
            );
          })}
        </div>
      ) : null}

      {!error && !loading && featuredCompanies.length === 0 ? (
        <div className="visa-results-minimal-empty">
          <span>No visa-positive companies are available right now.</span>
          <a href={panelHref(filters)}>Browse the full board</a>
        </div>
      ) : null}
    </section>
  );
}

function ShieldCheckIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
      <path d="M12 3 5 6v5c0 4.6 2.8 8.1 7 10 4.2-1.9 7-5.4 7-10V6l-7-3Z" />
      <path d="m8.7 12 2.1 2.1 4.6-4.7" />
    </svg>
  );
}

function InfoIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
      <circle cx="12" cy="12" r="9" />
      <path d="M12 11v5M12 8h.01" />
    </svg>
  );
}

function LocationIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
      <path d="M20 10c0 5-8 11-8 11S4 15 4 10a8 8 0 1 1 16 0Z" />
      <circle cx="12" cy="10" r="2.5" />
    </svg>
  );
}

function AlertIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
      <path d="M12 4 3 20h18L12 4Z" />
      <path d="M12 9v5M12 17h.01" />
    </svg>
  );
}

function ArrowIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
      <path d="M5 12h14M13 6l6 6-6 6" />
    </svg>
  );
}

function ExternalIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
      <path d="M14 5h5v5" />
      <path d="M10 14 19 5" />
      <path d="M19 13v6a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h6" />
    </svg>
  );
}
