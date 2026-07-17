"use client";

import { BrandMark } from "@/components/BrandMark";
import { SearchBar } from "@/components/SearchBar";
import { useSearchFlow } from "@/components/SearchFlowContext";
import { Button } from "@/components/ui/Button";

export function Hero() {
  const { filters, onSearch } = useSearchFlow();

  return (
    <section className="section-major-first" aria-labelledby="hero-heading">
      <div className="grid items-center gap-10 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)] lg:gap-12">
        <div className="min-w-0">
          <p className="hero-enter text-xs font-medium uppercase tracking-[0.14em] text-accent-primary">
            Relocation-friendly engineering roles
          </p>

          <h1
            id="hero-heading"
            className="hero-enter hero-enter-delay-1 mt-3 text-fluid-hero text-text-primary"
          >
            All your opportunities, in one place
          </h1>

          <p className="hero-enter hero-enter-delay-2 mt-4 max-w-xl text-base font-normal leading-relaxed text-text-secondary sm:text-lg">
            Find visa-sponsored engineering roles in Europe — track applications
            and tailor your CV before openings disappear.
          </p>

          <div className="hero-enter hero-enter-delay-2 mt-8 flex flex-wrap gap-3">
            <Button as="a" href="/panel" variant="primary">
              Get started
            </Button>
            <Button as="a" href="/#board" variant="secondary">
              See the board
            </Button>
          </div>

          <div className="hero-enter hero-enter-delay-3 mt-8">
            <div className="hero-search-glow">
              <SearchBar
                id="hero-search"
                key={`hero-${filters?.country ?? "all"}-${filters?.q ?? ""}`}
                onSearch={onSearch}
                defaultFilters={filters ?? undefined}
              />
            </div>
            <p className="mt-3 text-sm font-normal leading-relaxed text-text-muted">
              Search previews live catalog results — no sign-in required. Updated
              every 6 hours from company career pages.
            </p>
          </div>
        </div>

        <div className="hero-enter hero-enter-delay-2 relative flex justify-center lg:justify-end">
          <BrandMark size="hero" />
        </div>
      </div>
    </section>
  );
}
