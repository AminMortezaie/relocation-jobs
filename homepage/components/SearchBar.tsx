"use client";

import { FormEvent, useId } from "react";
import type { SearchFilters } from "@/lib/search";

const ROLES = [
  { value: "", label: "All roles" },
  { value: "backend", label: "Backend" },
  { value: "python", label: "Python" },
  { value: "go", label: "Go" },
  { value: "java", label: "Java" },
  { value: "react", label: "React / Frontend" },
  { value: "devops", label: "DevOps / Platform" },
] as const;

const COUNTRIES = [
  { value: "all", label: "All countries" },
  { value: "germany", label: "Germany" },
  { value: "netherlands", label: "Netherlands" },
  { value: "uk", label: "UK" },
  { value: "portugal", label: "Portugal" },
  { value: "ireland", label: "Ireland" },
] as const;

type SearchBarProps = {
  id?: string;
  defaultFilters?: SearchFilters;
  onSearch: (filters: SearchFilters) => void;
};

export function SearchBar({
  id,
  defaultFilters,
  onSearch,
}: SearchBarProps) {
  const roleId = useId();
  const countryId = useId();

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    onSearch({
      country: String(data.get("country") || "all"),
      q: String(data.get("q") || ""),
    });
  }

  return (
    <form
      id={id}
      onSubmit={handleSubmit}
      className="hero-search-form"
    >
      <div className="hero-search-fields">
        <div className="hero-search-field">
          <label className="hero-search-label" htmlFor={roleId}>
            Role or stack
          </label>
          <div className="hero-search-control">
            <StackIcon />
            <select
              id={roleId}
              name="q"
              defaultValue={defaultFilters?.q ?? ""}
              className="hero-search-select"
            >
              {ROLES.map((option) => (
                <option key={option.value || "all"} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <Chevron />
          </div>
        </div>

        <div className="hero-search-field">
          <label className="hero-search-label" htmlFor={countryId}>
            Destination
          </label>
          <div className="hero-search-control">
            <GlobeIcon />
            <select
              id={countryId}
              name="country"
              defaultValue={defaultFilters?.country ?? "all"}
              className="hero-search-select"
            >
              {COUNTRIES.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <Chevron />
          </div>
        </div>
      </div>

      <button
        type="submit"
        className="btn-primary hero-search-submit"
      >
        <span>Find roles</span>
        <ArrowIcon />
      </button>
    </form>
  );
}

function StackIcon() {
  return (
    <svg
      className="hero-search-icon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      aria-hidden="true"
    >
      <rect x="3" y="3" width="7" height="7" rx="1" />
      <rect x="14" y="3" width="7" height="7" rx="1" />
      <rect x="3" y="14" width="7" height="7" rx="1" />
      <rect x="14" y="14" width="7" height="7" rx="1" />
    </svg>
  );
}

function GlobeIcon() {
  return (
    <svg
      className="hero-search-icon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="9" />
      <path d="M2 12h20M12 2a15 15 0 0 1 0 20M12 2a15 15 0 0 0 0 20" />
    </svg>
  );
}

function Chevron() {
  return (
    <svg
      className="hero-search-chevron"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      aria-hidden="true"
    >
      <path d="M6 9l6 6 6-6" />
    </svg>
  );
}

function ArrowIcon() {
  return (
    <svg
      className="hero-search-arrow"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      aria-hidden="true"
    >
      <path d="M5 12h14M13 6l6 6-6 6" />
    </svg>
  );
}
