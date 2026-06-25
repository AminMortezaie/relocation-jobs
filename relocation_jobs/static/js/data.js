/** Load config, countries, and job listings from the API. */

import { state } from "./state.js";
import { $, escapeAttr, escapeHtml, setLoadingProgress, finishLoadingProgress } from "./utils.js";
import { fetchConfig, fetchCountries, fetchAtsTypes, fetchLocations } from "./api.js";
import { loadBoard, showJobsLoading } from "./board.js";

export { setLoadingProgress, finishLoadingProgress, showJobsLoading };

let locationsLoaded = false;

function savedLocationKey() {
  return localStorage.getItem("panel_location")
    || localStorage.getItem("panel_city")
    || "all";
}

export function needsLocationsBeforeBoard() {
  return savedLocationKey() !== "all";
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
  if (saved && countries.some((c) => c.id === saved)) {
    sel.value = saved;
  } else {
    const first = countries.find((c) => c.id !== "all");
    if (first) sel.value = first.id;
  }
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

export async function loadCities({ deferred = false } = {}) {
  const sel = $("location");
  if (!sel) return;

  const country = $("country")?.value || "all";
  const saved = savedLocationKey();

  if (deferred && country === "all" && saved === "all") {
    sel.innerHTML = `<option value="all">All locations</option>`;
    locationsLoaded = false;
    return;
  }

  const locations = await fetchLocations(country);
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
  locationsLoaded = true;
}

export async function ensureLocationsLoaded() {
  if (locationsLoaded) return;
  await loadCities();
}

export async function loadJobs(options = {}) {
  return loadBoard(options);
}

export async function loadBoardWithLocations(options = {}) {
  if (needsLocationsBeforeBoard()) {
    await loadCities();
    return loadBoard(options);
  }
  await loadBoard(options);
  void loadCities({ deferred: true });
}

export { refreshJobBoard } from "./job-board.js";
