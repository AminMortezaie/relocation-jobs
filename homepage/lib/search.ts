export type SearchFilters = {
  country: string;
  q: string;
};

export function filtersToQuery(filters: SearchFilters) {
  const params = new URLSearchParams();
  if (filters.country !== "all") params.set("country", filters.country);
  if (filters.q.trim()) params.set("q", filters.q.trim());
  return params;
}

export function panelHref(filters: SearchFilters) {
  const params = filtersToQuery(filters);
  const query = params.toString();
  return query ? `/panel?${query}` : "/panel";
}
