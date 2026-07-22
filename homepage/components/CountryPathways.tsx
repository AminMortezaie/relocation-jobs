import { countryLinks } from "@/lib/countries";
import { countrySnapshot } from "@/lib/country-snapshots";

const COUNTRY_NOTES: Record<string, string> = {
  Germany: "EU Blue Card · employer declaration · Berlin / Munich",
  Ireland: "Critical Skills permit · Dublin tech hubs",
  Netherlands: "Highly Skilled Migrant · IND recognised sponsors",
  Portugal: "Tech Visa / D3 · Lisbon / Porto",
  "United Kingdom": "Skilled Worker · licensed sponsors · CoS",
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
            Each country page explains how sponsorship and visas usually work
            there — Blue Card, Highly Skilled Migrant, Skilled Worker, Critical
            Skills, Tech Visa / D3 — then links into the same Kuchup catalog.
          </p>
        </header>

        <nav className="country-index" aria-label="Browse relocation jobs by country">
          {countryLinks().map((country, index) => {
            const key = country.href.replace("/relocation-jobs-", "");
            const snap = countrySnapshot(key);
            const note =
              snap && snap.companies > 0
                ? `${snap.companies} companies · ${snap.visa_jobs} sponsorship-positive roles`
                : COUNTRY_NOTES[country.label] ??
                  "Browse current relocation-focused openings.";
            return (
              <a key={country.href} href={country.href} className="country-link">
                <span className="country-order">{String(index + 1).padStart(2, "0")}</span>
                <span className="country-name">{country.label}</span>
                <span className="country-note">{note}</span>
                <span className="country-arrow" aria-hidden="true">↗</span>
              </a>
            );
          })}
        </nav>
      </div>
    </section>
  );
}
