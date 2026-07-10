"use client";

import { SearchBar } from "@/components/SearchBar";
import { useSearchFlow } from "@/components/SearchFlowContext";

export function Hero() {
  const { filters, onSearch } = useSearchFlow();

  return (
    <section className="section-major-first" aria-labelledby="hero-heading">
      <div className="max-w-3xl">
        <p className="hero-enter text-xs font-medium uppercase tracking-[0.14em] text-accent-hover">
          Relocation-friendly engineering roles
        </p>

        <h1
          id="hero-heading"
          className="hero-enter hero-enter-delay-1 mt-3 text-fluid-hero text-text"
        >
          Find visa-sponsored engineering roles in Europe — before they&apos;re
          gone.
        </h1>

        <div className="hero-enter hero-enter-delay-2 mt-8">
          <div className="surface-card hero-search-glow rounded-app p-4 sm:p-5">
            <SearchBar
              id="hero-search"
              key={`hero-${filters?.country ?? "all"}-${filters?.q ?? ""}`}
              onSearch={onSearch}
              defaultFilters={filters ?? undefined}
            />
          </div>
        </div>

        <p className="hero-enter hero-enter-delay-3 mt-4 text-sm font-normal leading-relaxed text-muted sm:text-base">
          Search previews live catalog results — no sign-in required. Updated every
          6 hours directly from company career pages.
        </p>
      </div>
    </section>
  );
}
