/** Load config, countries, and job listings from the API. */

import { state } from "./state.js";
import { $, escapeAttr, escapeHtml, setLoadingProgress, finishLoadingProgress } from "./utils.js";
import { fetchConfig, fetchCountries, fetchAtsTypes, fetchLocations, fetchJobs } from "./api.js";
import { renderStats, renderCompanies } from "./render.js";

function skeletonCard() {
  return `
    <div class="skeleton-card">
      <div class="skeleton-card-header">
        <div class="skeleton-block skeleton-name"></div>
        <div class="skeleton-badges">
          <div class="skeleton-block skeleton-badge"></div>
          <div class="skeleton-block skeleton-badge"></div>
        </div>
      </div>
      <hr class="skeleton-divider" />
      <div class="skeleton-jobs">
        <div class="skeleton-block skeleton-job"></div>
        <div class="skeleton-block skeleton-job skeleton-job--short"></div>
      </div>
    </div>`;
}

export { setLoadingProgress, finishLoadingProgress };

export function showJobsLoading() {
  const list = $("jobs");
  if (list) {
    list.innerHTML = Array(4).fill(0).map(skeletonCard).join("");
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
  const country = $("country").value;
  localStorage.setItem("panel_country", country);
  if ($("ats")) {
    localStorage.setItem("panel_ats", $("ats").value);
  }
  if ($("location")) {
    localStorage.setItem("panel_location", $("location").value);
  }
  if (!options.silent) {
    showJobsLoading();
  }
  const data = await fetchJobs(options);
  state.allCompanies = data.companies || [];
  state.boardStats = data.stats || null;
  if (data.stats) renderStats(data.stats);
  renderCompanies();
}

export { refreshJobBoard } from "./job-board.js";
