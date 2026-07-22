"use client";

import { BrandMark } from "@/components/BrandMark";
import { SearchBar } from "@/components/SearchBar";
import { useSearchFlow } from "@/components/SearchFlowContext";

export function Hero() {
  const { filters, onSearch } = useSearchFlow();

  return (
    <section id="search" className="landing-hero" aria-labelledby="hero-heading">
      <div className="landing-shell hero-layout">
        <div className="hero-copy min-w-0">
          <p className="hero-enter section-kicker">
            Relocation job search, held together
          </p>

          <h1
            id="hero-heading"
            className="hero-enter hero-enter-delay-1 mt-3 text-fluid-hero text-text-primary"
          >
            All your opportunities, in one place
          </h1>

          <p className="hero-enter hero-enter-delay-2 hero-lede">
            Kuchup helps international software engineers discover
            relocation-focused roles, keep every decision organized, and
            tailor applications with Claude or Cursor via MCP — without losing
            the thread.
          </p>

          <div className="hero-enter hero-enter-delay-3 hero-search">
            <div className="hero-search-glow">
              <SearchBar
                id="hero-search"
                key={`hero-${filters?.country ?? "all"}-${filters?.q ?? ""}`}
                onSearch={onSearch}
                defaultFilters={filters ?? undefined}
              />
            </div>
            <div className="hero-search-note">
              <p>
                Public preview. No sign-in required. Updated every six hours
                from company career pages.
              </p>
              <div className="hero-search-links">
                <a href="/panel">
                  Open the full board <span aria-hidden="true">→</span>
                </a>
                <a href="/mcp">
                  Claude &amp; Cursor MCP <span aria-hidden="true">→</span>
                </a>
              </div>
            </div>
          </div>
        </div>

        <div className="hero-bird" aria-hidden="true">
          <span className="hero-bird-flight-path" />
          <BrandMark size="hero" className="hero-bird-mark" />
        </div>
      </div>
    </section>
  );
}
