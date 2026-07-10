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
  compact?: boolean;
  defaultFilters?: SearchFilters;
  onSearch: (filters: SearchFilters) => void;
};

export function SearchBar({
  id,
  compact = false,
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
      className={`flex flex-col gap-2 sm:flex-row sm:items-stretch ${compact ? "" : "sm:gap-3"}`}
    >
      <label className="sr-only" htmlFor={roleId}>
        Role or stack
      </label>
      <div className="relative min-w-0 flex-1">
        <StackIcon />
        <select
          id={roleId}
          name="q"
          defaultValue={defaultFilters?.q ?? ""}
          className="select-pill"
        >
          {ROLES.map((option) => (
            <option key={option.value || "all"} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <Chevron />
      </div>

      <label className="sr-only" htmlFor={countryId}>
        Country
      </label>
      <div className="relative min-w-0 flex-1 sm:max-w-[11rem]">
        <GlobeIcon />
        <select
          id={countryId}
          name="country"
          defaultValue={defaultFilters?.country ?? "all"}
          className="select-pill"
        >
          {COUNTRIES.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <Chevron />
      </div>

      <button
        type="submit"
        className="btn-primary inline-flex shrink-0 items-center justify-center rounded-full px-5 py-3 text-sm font-semibold text-white"
      >
        Search roles
      </button>
    </form>
  );
}

function StackIcon() {
  return (
    <svg
      className="select-icon pointer-events-none absolute left-3.5 h-[15px] w-[15px] text-muted"
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
      className="select-icon pointer-events-none absolute left-3.5 h-[15px] w-[15px] text-muted"
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
      className="select-icon pointer-events-none absolute right-3.5 h-3.5 w-3.5 text-muted"
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
