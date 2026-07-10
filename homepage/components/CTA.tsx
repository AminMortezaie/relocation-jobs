"use client";

import { SearchBar } from "@/components/SearchBar";
import { useSearchFlow } from "@/components/SearchFlowContext";
import { Card } from "@/components/ui/Card";

export function CTA() {
  const { filters, onSearch } = useSearchFlow();

  return (
    <section className="section-compact" aria-labelledby="cta-heading">
      <Card className="px-5 py-7 sm:px-7">
        <h2 id="cta-heading" className="text-section-title text-text">
          Ready to search?
        </h2>
        <p className="mt-2 text-sm font-normal text-muted">
          Results appear above. Sign in when you want to track applications and
          tailor your CV per role.
        </p>
        <div className="hero-search-glow mt-6 max-w-2xl">
          <SearchBar
            compact
            key={`cta-${filters?.country ?? "all"}-${filters?.q ?? ""}`}
            onSearch={onSearch}
            defaultFilters={filters ?? undefined}
          />
        </div>
      </Card>
    </section>
  );
}
