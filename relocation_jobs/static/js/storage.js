/** localStorage persistence for UI preferences. */

import { state } from "./state.js";
import { $ } from "./utils.js";

export function loadCollapsedCompanies() {
  try {
    const saved = JSON.parse(localStorage.getItem("panel_collapsed") || "[]");
    state.collapsedCompanies = new Set(Array.isArray(saved) ? saved : []);
  } catch {
    state.collapsedCompanies = new Set();
  }
}

export function saveCollapsedCompanies() {
  localStorage.setItem(
    "panel_collapsed",
    JSON.stringify([...state.collapsedCompanies])
  );
}

export function loadShowNotForMeCompanies() {
  try {
    const saved = JSON.parse(
      localStorage.getItem("panel_show_not_for_me")
        || localStorage.getItem("panel_show_hidden")
        || "[]"
    );
    state.showNotForMeCompanies = new Set(Array.isArray(saved) ? saved : []);
  } catch {
    state.showNotForMeCompanies = new Set();
  }
}

export function saveShowNotForMeCompanies() {
  localStorage.setItem(
    "panel_show_not_for_me",
    JSON.stringify([...state.showNotForMeCompanies])
  );
}

export function loadShowRejectedCompanies() {
  try {
    const saved = JSON.parse(localStorage.getItem("panel_show_rejected") || "[]");
    state.showRejectedCompanies = new Set(Array.isArray(saved) ? saved : []);
  } catch {
    state.showRejectedCompanies = new Set();
  }
}

export function saveShowRejectedCompanies() {
  localStorage.setItem(
    "panel_show_rejected",
    JSON.stringify([...state.showRejectedCompanies])
  );
}

export function migrateCompanyKeyInState(country, oldName, newName) {
  const oldKey = `${country}:${oldName}`;
  const newKey = `${country}:${newName}`;
  if (oldKey === newKey) return;

  for (const set of [
    state.collapsedCompanies,
    state.showNotForMeCompanies,
    state.showRejectedCompanies,
  ]) {
    if (set.has(oldKey)) {
      set.delete(oldKey);
      set.add(newKey);
    }
  }

  if (state.fetchingCompanyKey === oldKey) {
    state.fetchingCompanyKey = newKey;
  }

  saveCollapsedCompanies();
  saveShowNotForMeCompanies();
  saveShowRejectedCompanies();
}

export function loadSortPreference() {
  const sortSaved = localStorage.getItem("panel_sort_newest");
  if (sortSaved !== null) {
    $("sortNewestFetch").checked = sortSaved === "1";
    if ($("sortSelect")) {
      $("sortSelect").value = sortSaved === "1" ? "newest" : "name";
    }
  }
}

export function saveSortPreference() {
  localStorage.setItem(
    "panel_sort_newest",
    $("sortNewestFetch").checked ? "1" : "0"
  );
}

const FILTER_STORAGE_IDS = [
  "hidePositionApplied",
  "positionAppliedOnly",
  "positionRejectedOnly",
  "positionLookingToApplyOnly",
  "hideApplied",
  "hideEmpty",
  "hideCollapsedCompanies",
  "notAppliedOnly",
  "fetchOkOnly",
  "fetchProblemOnly",
  "visaOnly",
];

export function loadFilterPreferences() {
  try {
    const saved = JSON.parse(localStorage.getItem("panel_filters") || "{}");
    if (!saved || typeof saved !== "object") return;
    if (saved.hideFullyHidden && saved.hideCollapsedCompanies === undefined) {
      saved.hideCollapsedCompanies = saved.hideFullyHidden;
    }
    for (const id of FILTER_STORAGE_IDS) {
      const el = $(id);
      if (!el || saved[id] === undefined) continue;
      el.checked = Boolean(saved[id]);
    }
    if ($("hideEmpty") && saved.hideEmpty === undefined) {
      $("hideEmpty").checked = true;
    }
  } catch {
    /* ignore */
  }
}

export function saveFilterPreferences() {
  const values = {};
  for (const id of FILTER_STORAGE_IDS) {
    const el = $(id);
    if (el) values[id] = el.checked;
  }
  localStorage.setItem("panel_filters", JSON.stringify(values));
}
