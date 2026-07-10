"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import type { SearchFilters } from "@/lib/search";
import { filtersToQuery } from "@/lib/search";

type SearchFlowContextValue = {
  filters: SearchFilters | null;
  onSearch: (filters: SearchFilters) => void;
};

const SearchFlowContext = createContext<SearchFlowContextValue | null>(null);

function parseFiltersFromUrl(): SearchFilters | null {
  if (typeof window === "undefined") return null;
  const params = new URLSearchParams(window.location.search);
  if (!params.has("country") && !params.has("q")) return null;
  return {
    country: params.get("country") || "all",
    q: params.get("q") || "",
  };
}

export function SearchFlowProvider({ children }: { children: ReactNode }) {
  const [filters, setFilters] = useState<SearchFilters | null>(null);

  useEffect(() => {
    const initial = parseFiltersFromUrl();
    if (initial) setFilters(initial);
  }, []);

  const onSearch = useCallback((next: SearchFilters) => {
    setFilters(next);
    const params = filtersToQuery(next);
    const query = params.toString();
    const nextUrl = query ? `${window.location.pathname}?${query}` : window.location.pathname;
    window.history.replaceState(null, "", nextUrl);
    window.requestAnimationFrame(() => {
      document.getElementById("search-results")?.scrollIntoView({
        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
          ? "auto"
          : "smooth",
        block: "start",
      });
    });
  }, []);

  const value = useMemo(() => ({ filters, onSearch }), [filters, onSearch]);

  return (
    <SearchFlowContext.Provider value={value}>{children}</SearchFlowContext.Provider>
  );
}

export function useSearchFlow() {
  const context = useContext(SearchFlowContext);
  if (!context) {
    throw new Error("useSearchFlow must be used within SearchFlowProvider");
  }
  return context;
}
