import { countryLinks } from "@/lib/countries";

const COUNTRY_NOTES: Record<string, string> = {
  Germany: "Engineering depth across established and growing companies.",
  Ireland: "International teams around a concentrated technology market.",
  Netherlands: "Product, platform, and infrastructure roles in global teams.",
  Portugal: "A growing base for distributed and international engineering.",
  "United Kingdom": "A broad software market across finance, product, and platforms.",
};

export function CountryPathways() {
  return (
    <section id="countries" className="landing-band landing-band-sky" aria-labelledby="countries-heading">
      <div className="landing-shell section-major countries-layout">
        <header className="countries-intro">
          <p className="section-kicker">Choose a direction</p>
          <h2 id="countries-heading" className="text-section-display text-text-primary">
            Explore the market country by country.
          </h2>
          <p className="section-lede">
            Each country page opens into the same catalog and workflow. Start
            where relocation is most realistic for you, then compare without
            rebuilding your search.
          </p>
        </header>

        <nav className="country-index" aria-label="Browse relocation jobs by country">
          {countryLinks().map((country, index) => (
            <a key={country.href} href={country.href} className="country-link">
              <span className="country-order">{String(index + 1).padStart(2, "0")}</span>
              <span className="country-name">{country.label}</span>
              <span className="country-note">
                {COUNTRY_NOTES[country.label] ?? "Browse current relocation-focused openings."}
              </span>
              <span className="country-arrow" aria-hidden="true">↗</span>
            </a>
          ))}
        </nav>
      </div>
    </section>
  );
}
