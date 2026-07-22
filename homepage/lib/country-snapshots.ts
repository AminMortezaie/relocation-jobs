import snapshotsJson from "@/data/country-snapshots.json";

export type CountrySampleCompany = {
  name: string;
  city: string;
  careers_url: string;
  job_count: number;
  visa_job_count: number;
};

export type CountrySamplePosition = {
  title: string;
  company_name: string;
  location: string;
  url: string;
};

export type CountrySnapshot = {
  country: string;
  label: string;
  companies: number;
  jobs: number;
  visa_jobs: number;
  last_fetch: string;
  cities: string[];
  sample_companies: CountrySampleCompany[];
  sample_positions: CountrySamplePosition[];
};

type SnapshotsFile = {
  countries: Record<string, CountrySnapshot>;
};

const DATA = snapshotsJson as SnapshotsFile;

export function countrySnapshot(key: string): CountrySnapshot | null {
  return DATA.countries[key] ?? null;
}
