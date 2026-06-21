/** Load config, countries, and job listings from the API. */

import { state } from "./state.js";
import { $, escapeAttr, escapeHtml } from "./utils.js";
import { fetchConfig, fetchCountries, fetchLocations, fetchJobs } from "./api.js";
import { renderStats, renderCompanies } from "./render.js";

export function showJobsLoading(message = "Loading companies…") {
  const list = $("jobs");
  if (list) {
    list.innerHTML = `<div class="empty">${escapeHtml(message)}</div>`;
  }
}

export async function loadConfig() {
  state.scrapeConfig = await fetchConfig();
}

export async function loadCountries() {
  const countries = await fetchCountries();
  const sel = $("country");
  sel.innerHTML = countries.map((c) =>
    `<option value="${c.id}">${c.label}</option>`
  ).join("");
  const saved = localStorage.getItem("panel_country");
  if (saved) sel.value = saved;
}

export async function loadCities() {
  const sel = $("location");
  if (!sel) return;

  const country = $("country")?.value || "all";
  const locations = await fetchLocations(country);
  const saved = localStorage.getItem("panel_location")
    || localStorage.getItem("panel_city")
    || "all";
  const keys = new Set(locations.map((loc) => loc.key));
  sel.innerHTML = [
    `<option value="all">All locations</option>`,
    ...locations.map((loc) =>
      `<option value="${escapeAttr(loc.key)}">${escapeHtml(loc.label || loc.city)}</option>`
    ),
  ].join("");
  if (saved !== "all" && keys.has(saved)) {
    sel.value = saved;
  } else {
    sel.value = "all";
    localStorage.setItem("panel_location", "all");
  }
}

export async function loadJobs(options = {}) {
  const country = $("country").value;
  localStorage.setItem("panel_country", country);
  if ($("location")) {
    localStorage.setItem("panel_location", $("location").value);
  }
  showJobsLoading();
  const data = await fetchJobs(options);
  state.allCompanies = data.companies || [];
  if (data.stats) renderStats(data.stats);
  renderCompanies();
}
