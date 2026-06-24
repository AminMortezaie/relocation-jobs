/** Load config, countries, and job listings from the API. */

import { state } from "./state.js";
import { $, escapeAttr, escapeHtml, setLoadingProgress, finishLoadingProgress } from "./utils.js";
import { fetchConfig, fetchCountries, fetchAtsTypes, fetchLocations } from "./api.js";
import { loadBoard, showJobsLoading } from "./board.js";

export { setLoadingProgress, finishLoadingProgress, showJobsLoading };

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

export async function loadAtsTypes() {
  const sel = $("ats");
  if (!sel) return;

  const types = await fetchAtsTypes();
  sel.innerHTML = [
    `<option value="all">All ATS</option>`,
    `<option value="generic">Generic / unknown</option>`,
    ...types.map((t) =>
      `<option value="${escapeAttr(t.id)}">${escapeHtml(t.label)}</option>`
    ),
  ].join("");
  const saved = localStorage.getItem("panel_ats");
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
  return loadBoard(options);
}

export { refreshJobBoard } from "./job-board.js";
