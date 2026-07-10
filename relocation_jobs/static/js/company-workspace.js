/** URL helpers for the company application workspace page. */

export function companySlug(name) {
  return String(name || "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

export function companyWorkspacePath(country, companyName) {
  const countryKey = String(country || "").trim().toLowerCase();
  const slug = companySlug(companyName);
  if (!countryKey || !slug) return "/panel";
  return `/company/${encodeURIComponent(countryKey)}/${encodeURIComponent(slug)}`;
}
