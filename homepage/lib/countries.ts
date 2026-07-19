import countriesJson from "@/data/countries.json";

export type CountryLabels = Record<string, string>;

export const COUNTRY_LABELS: CountryLabels = countriesJson;

export function countryLabel(key: string): string | undefined {
  return COUNTRY_LABELS[key];
}

export function countryLinks(): { href: string; label: string }[] {
  return Object.entries(COUNTRY_LABELS)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([key, label]) => ({
      href: `/relocation-jobs-${key}`,
      label,
    }));
}
